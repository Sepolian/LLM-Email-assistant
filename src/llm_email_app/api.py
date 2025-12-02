import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

import asyncio
import logging
import calendar as cal
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from threading import Lock
import time
import uuid
from fastapi.staticfiles import StaticFiles

from fastapi import FastAPI, Depends, HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from llm_email_app.auth.session import login, auth_callback, get_credentials, load_persisted_credentials
from llm_email_app.config import settings, BASE_DIR
from llm_email_app.email.gmail_client import GmailClient, canonical_folder_key
from llm_email_app.calendar.gcal import GCalClient
from typing import Dict, Any, List, Optional, Tuple
from llm_email_app.auth.google_oauth import TOKEN_DIR
import json

from llm_email_app.llm.openai_client import OpenAIClient
from llm_email_app.email.rules import RuleManager, ProcessedEmailStore

logger = logging.getLogger(__name__)

TMP_DIR = (BASE_DIR / 'tmp')
TMP_DIR.mkdir(parents=True, exist_ok=True)
EMAIL_CACHE_PATH = TMP_DIR / 'emails_recent.json'
CALENDAR_CACHE_PATH = TMP_DIR / 'calendar_recent.json'
AUTOMATION_LOGS_PATH = TMP_DIR / 'automation_logs.json'
MESSAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,256}$")
LOG_RETENTION_DAYS = 7

RULE_MANAGER = RuleManager(settings.AUTO_LABEL_RULES_PATH, settings.AUTO_LABEL_ENABLED_DEFAULT)
PROCESSED_STORE = ProcessedEmailStore(settings.AUTO_LABEL_PROCESSED_PATH)
AUTOMATION_STATUS_LOCK = Lock()
AUTOMATION_LOG_MAX = 50
EMAIL_CACHE_MAX_AGE = timedelta(minutes=90)
AUTOMATION_STATUS: Dict[str, Any] = {
    'last_run_at': None,
    'last_error': None,
    'last_labeled': 0,
    'last_refresh_at': None,
    'logs': [],
}
LLM_CLIENT = OpenAIClient()


def _coerce_datetime(value: Optional[str]) -> Optional[datetime]:
    """Best-effort conversion of loose datetime strings into aware datetime objects."""
    if not value:
        return None
    try:
        # Support both Z suffix and explicit offsets
        if value.endswith('Z'):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        if 'T' in value and '+' not in value and value.count('-') <= 2:
            return datetime.fromisoformat(value + '+00:00')
        if 'T' not in value:
            return datetime.fromisoformat(f"{value}T00:00:00+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _write_temp_json(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        logger.warning('Unable to persist snapshot at %s: %s', path, exc)


def _read_cached_payload(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.warning('Unable to read cached payload at %s: %s', path, exc)
        return None


def _load_cached_recent_emails(lookback_days: int, limit: int) -> List[Dict[str, Any]]:
    snapshot = _read_cached_payload(EMAIL_CACHE_PATH)
    if not snapshot:
        return []

    generated_at = _coerce_datetime(snapshot.get('generated_at'))
    if not generated_at:
        return []
    if datetime.now(timezone.utc) - generated_at > EMAIL_CACHE_MAX_AGE:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))
    ordered: List[Tuple[Optional[datetime], Dict[str, Any]]] = []
    for item in snapshot.get('emails', []):
        received_dt = _coerce_datetime(item.get('received'))
        if received_dt and received_dt < cutoff:
            continue
        ordered.append((received_dt, dict(item)))

    if not ordered:
        return []

    ordered.sort(
        key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    sliced = [item for _, item in ordered[:max(1, limit)]]
    return sliced


def _persist_recent_emails(mailbox: Dict[str, Any], window_days: int = 14) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    flattened: List[Dict[str, Any]] = []
    for folder_key, payload in mailbox.get('folders', {}).items():
        for item in payload.get('items', []):
            received = _coerce_datetime(item.get('received'))
            if received is None or received >= cutoff:
                enriched = dict(item)
                enriched['folder'] = folder_key
                flattened.append(enriched)

    snapshot = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'window_days': window_days,
        'count': len(flattened),
        'emails': flattened,
    }
    _write_temp_json(EMAIL_CACHE_PATH, snapshot)


def _persist_calendar(events: List[Dict[str, Any]], window_days: int = 365) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    filtered: List[Dict[str, Any]] = []
    todos: List[Dict[str, Any]] = []
    for event in events:
        start = event.get('start', {}) or {}
        start_raw = start.get('dateTime') or start.get('date')
        start_dt = _coerce_datetime(start_raw)
        if start_dt is None or start_dt >= cutoff:
            filtered.append(event)
            summary = (event.get('summary') or '').lower()
            if event.get('eventType') == 'task' or 'todo' in summary:
                todos.append(event)

    snapshot = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'window_days': window_days,
        'events': filtered,
        'todos': todos,
    }
    _write_temp_json(CALENDAR_CACHE_PATH, snapshot)


def _calendar_snapshot_is_stale(max_age: timedelta = timedelta(minutes=30)) -> bool:
    """Return True when the cached ±1 year snapshot should be refreshed."""
    try:
        if not CALENDAR_CACHE_PATH.exists():
            return True
        payload = json.loads(CALENDAR_CACHE_PATH.read_text(encoding='utf-8'))
        generated_at = payload.get('generated_at')
        generated_dt = _coerce_datetime(generated_at)
        if not generated_dt:
            return True
        return datetime.now(timezone.utc) - generated_dt > max_age
    except Exception as exc:
        logger.warning('Unable to determine calendar snapshot freshness: %s', exc)
        return True


def _month_bounds(month_str: str) -> Tuple[datetime, datetime]:
    try:
        year, month = map(int, month_str.split('-'))
        first = datetime(year, month, 1, tzinfo=timezone.utc)
        last_day = cal.monthrange(year, month)[1]
        last = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
        return first, last
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid month format, expected YYYY-MM") from exc


def _validate_message_id_or_400(message_id: str) -> str:
    candidate = (message_id or '').strip()
    if not candidate or not MESSAGE_ID_PATTERN.fullmatch(candidate):
        raise HTTPException(status_code=400, detail="Invalid message_id format")
    return candidate


def _update_automation_status(**fields: Any) -> None:
    with AUTOMATION_STATUS_LOCK:
        AUTOMATION_STATUS.update(fields)


def _automation_status_snapshot() -> Dict[str, Any]:
    with AUTOMATION_STATUS_LOCK:
        snapshot = dict(AUTOMATION_STATUS)
        snapshot['logs'] = list(AUTOMATION_STATUS.get('logs', []))
        return snapshot


def _load_persisted_logs() -> List[Dict[str, Any]]:
    """Load logs from persistent storage, filtering out entries older than LOG_RETENTION_DAYS."""
    try:
        if not AUTOMATION_LOGS_PATH.exists():
            return []
        payload = json.loads(AUTOMATION_LOGS_PATH.read_text(encoding='utf-8'))
        logs = payload.get('logs', [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)
        filtered = []
        for log in logs:
            ts = _coerce_datetime(log.get('timestamp'))
            if ts and ts >= cutoff:
                filtered.append(log)
        return filtered
    except Exception as exc:
        logger.warning('Unable to load persisted logs: %s', exc)
        return []


def _persist_logs(logs: List[Dict[str, Any]]) -> None:
    """Save logs to persistent storage, keeping only last LOG_RETENTION_DAYS."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)
        filtered = []
        for log in logs:
            ts = _coerce_datetime(log.get('timestamp'))
            if ts and ts >= cutoff:
                filtered.append(log)
        payload = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'retention_days': LOG_RETENTION_DAYS,
            'count': len(filtered),
            'logs': filtered,
        }
        _write_temp_json(AUTOMATION_LOGS_PATH, payload)
    except Exception as exc:
        logger.warning('Unable to persist logs: %s', exc)


def _append_automation_log(message: str, level: str = 'info') -> None:
    entry = {
        'id': uuid.uuid4().hex,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'level': level,
        'message': message,
    }
    with AUTOMATION_STATUS_LOCK:
        # Load existing persisted logs and append new entry
        logs = _load_persisted_logs()
        logs.append(entry)
        # Keep in-memory copy for status snapshot
        AUTOMATION_STATUS['logs'] = logs[-AUTOMATION_LOG_MAX:]
        # Persist all logs (within retention period)
        _persist_logs(logs)


def _reset_processed_email_cache(reason: str) -> None:
    """Clear processed-email markers so new/updated rules can reprocess existing threads."""
    PROCESSED_STORE.reset()
    _append_automation_log(f"{reason}：已清空已处理邮件缓存")


def _require_credentials(request: Request) -> Dict[str, Any]:
    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return creds_json


def _auto_label_recent_emails(gmail_client: GmailClient) -> int:
    rules_state = RULE_MANAGER.get_state()
    rules = rules_state.get('rules', [])
    if not rules:
        return 0

    lookback_days = max(1, settings.AUTO_LABEL_LOOKBACK_DAYS)
    batch_target = max(1, settings.AUTO_LABEL_MAX_PER_CYCLE)
    delay_seconds = max(0.0, settings.AUTO_LABEL_REQUEST_INTERVAL_SECONDS)
    candidate_limit = batch_target * 3

    # Prefer cache snapshot to avoid extra Gmail API usage
    candidates = _load_cached_recent_emails(lookback_days, candidate_limit)
    used_cache = bool(candidates)
    if used_cache:
        _append_automation_log(f"自动化使用本地缓存，共 {len(candidates)} 封候选邮件。")
    else:
        # fetch extra to account for already-processed entries
        candidates = gmail_client.fetch_emails_since(days=lookback_days, max_results=candidate_limit)

    if not candidates:
        _append_automation_log('自动化跳过：没有可用的缓存邮件，也无法从远程获取。', level='warning')
        return 0

    labeled_count = 0
    for email_payload in candidates:
        message_id = email_payload.get('id')
        if not message_id or PROCESSED_STORE.is_processed(message_id):
            continue

        detail = email_payload
        if not (detail.get('body') or detail.get('html')):
            detail = gmail_client.get_message(message_id) or email_payload
        body = detail.get('html') or detail.get('body') or detail.get('snippet') or ''
        subject = detail.get('subject') or email_payload.get('subject') or ''
        sender = detail.get('from') or email_payload.get('from') or ''
        snippet = detail.get('snippet') or email_payload.get('snippet') or ''

        if not body and not subject:
            continue

        display_name = (subject or snippet or sender or message_id or '')[:80]
        if display_name:
            _append_automation_log(f"开始处理邮件「{display_name}」")

        try:
            evaluation = LLM_CLIENT.evaluate_label_rules(
                email_body=body,
                subject=subject,
                sender=sender,
                rules=rules,
            )
        except Exception as exc:
            logger.warning('LLM label evaluation failed for %s: %s', message_id, exc)
            _append_automation_log(f"LLM 失败（{message_id}）：{exc}", level='error')
            if delay_seconds:
                time.sleep(delay_seconds)
            continue

        matches = evaluation.get('matches') or []
        if not matches:
            if delay_seconds:
                time.sleep(delay_seconds)
            continue

        applied_any = False
        for match in matches:
            rule_id = match.get('rule_id')
            if not rule_id:
                continue
            rule = next((r for r in rules if r.get('id') == rule_id), None)
            if not rule:
                continue
            label_name = (rule.get('label') or '').strip()
            if not label_name:
                continue
            try:
                label_id = gmail_client.check_or_create_label(label_name)
            except Exception as exc:
                logger.warning('Unable to ensure label %s: %s', label_name, exc)
                continue

            if label_id and label_id != rule.get('label_id'):
                RULE_MANAGER.update_rule(rule_id, label_id=label_id)

            try:
                success = gmail_client.apply_labels_to_message(
                    message_id,
                    [label_id] if label_id else [label_name],
                )
            except Exception as exc:
                logger.warning('Failed to apply label %s to %s: %s', label_name, message_id, exc)
                success = False

            if success:
                applied_any = True

        if applied_any:
            PROCESSED_STORE.mark_processed(message_id)
            labeled_count += 1
            _append_automation_log(
                f"完成邮件「{subject or message_id}」的标签：{len(matches)} 条规则匹配"
            )
            if labeled_count >= batch_target:
                break

        if delay_seconds:
            time.sleep(delay_seconds)

    return labeled_count


def _run_auto_label_pipeline(gmail_client: GmailClient, context: str = 'scheduled') -> None:
    if not RULE_MANAGER.automation_enabled():
        _append_automation_log(f"自动化（{context}）跳过：功能已关闭。", level='warning')
        return
    try:
        labeled = _auto_label_recent_emails(gmail_client)
        _update_automation_status(
            last_run_at=datetime.now(timezone.utc).isoformat(),
            last_labeled=labeled,
            last_error=None,
        )
        _append_automation_log(f"自动化运行（{context}）完成，处理 {labeled} 封邮件。")
    except Exception as exc:
        logger.exception('Auto-label pipeline failed: %s', exc)
        _update_automation_status(
            last_run_at=datetime.now(timezone.utc).isoformat(),
            last_error=str(exc),
        )
        _append_automation_log(f"自动化运行（{context}）失败：{exc}", level='error')


def _trigger_automation_run(gmail_client: Optional[GmailClient], context: str) -> None:
    if gmail_client is None or gmail_client.service is None:
        _append_automation_log(f"自动化（{context}）跳过：Gmail 凭据不可用。", level='warning')
        return
    _run_auto_label_pipeline(gmail_client, context=context)


def _run_background_cycle() -> None:
    creds_json = load_persisted_credentials()
    if not creds_json:
        logger.debug('Skipping background refresh: no stored credentials yet')
        return

    creds = Credentials.from_authorized_user_info(creds_json)
    gmail_client = GmailClient(creds=creds)
    gcal_client = GCalClient(creds=creds)

    try:
        mailbox = gmail_client.fetch_mailbox_overview(active_folder='inbox', page=1, per_page=20, days=14)
        _persist_recent_emails(mailbox, window_days=14)
    except Exception as exc:
        logger.warning('Background email refresh failed: %s', exc)

    try:
        events = gcal_client.list_events(max_results=500)
        _persist_calendar(events, window_days=365)
    except Exception as exc:
        logger.warning('Background calendar refresh failed: %s', exc)

    _update_automation_status(last_refresh_at=datetime.now(timezone.utc).isoformat())

    if gmail_client.service is not None:
        _run_auto_label_pipeline(gmail_client, context='background')


async def _background_refresh_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = max(1, settings.BACKGROUND_REFRESH_INTERVAL_MINUTES)
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(_run_background_cycle)
        except Exception as exc:
            logger.exception('Background refresh loop iteration failed: %s', exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_minutes * 60)
        except asyncio.TimeoutError:
            continue


app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)


@app.on_event('startup')
async def _startup_background_workers() -> None:
    # Initialize in-memory logs from persisted file
    with AUTOMATION_STATUS_LOCK:
        persisted = _load_persisted_logs()
        AUTOMATION_STATUS['logs'] = persisted[-AUTOMATION_LOG_MAX:]
    
    stop_event = asyncio.Event()
    app.state.refresh_stop_event = stop_event
    app.state.refresh_task = asyncio.create_task(_background_refresh_loop(stop_event))


@app.on_event('shutdown')
async def _shutdown_background_workers() -> None:
    stop_event = getattr(app.state, 'refresh_stop_event', None)
    task = getattr(app.state, 'refresh_task', None)
    if stop_event:
        stop_event.set()
    if task:
        await task

# Serve frontend from project root (not src/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # -> project root
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    # mount at /frontend so requests like /frontend/pages/Email.jsx succeed
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend_static")

# use absolute path when returning index.html
INDEX_HTML = FRONTEND_DIR / "index.html"

SPA_ROUTES = {"calendar", "email", "settings"}

app.add_route("/login", route=login, methods=["GET"])
app.add_route("/auth/callback", route=auth_callback, methods=["GET"])

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    token_file = TOKEN_DIR / "google_token.json"
    if token_file.exists():
        token_file.unlink()
    return RedirectResponse(url="/")

@app.get("/user", response_model=Dict[str, Any])
async def get_user(request: Request):
    user = request.session.get("user")
    if user:
        return JSONResponse(user)

    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if 'id_token' in creds_json:
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_requests
            from llm_email_app.auth.google_oauth import get_web_flow

            flow = get_web_flow()
            id_info = id_token.verify_oauth2_token(
                creds_json['id_token'], google_requests.Request(), flow.client_config["client_id"]
            )
            user = {
                "name": id_info.get("name"),
                "email": id_info.get("email"),
                "picture": id_info.get("picture"),
            }
            request.session["user"] = user
            return JSONResponse(user)
        except Exception as e:
            print(e) # log error
            raise HTTPException(status_code=401, detail="Could not verify user.")

    raise HTTPException(status_code=401, detail="User information not available.")


def get_gmail_client(request: Request) -> GmailClient:
    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")
    creds = Credentials.from_authorized_user_info(creds_json)
    return GmailClient(creds=creds)

def get_gcal_client(request: Request) -> GCalClient:
    creds_json = get_credentials(request)
    if not creds_json:
        raise HTTPException(status_code=401, detail="Not authenticated")
    creds = Credentials.from_authorized_user_info(creds_json)
    return GCalClient(creds=creds)


@app.get('/automation/status', response_model=Dict[str, Any])
def get_automation_status(request: Request):
    _require_credentials(request)
    status = _automation_status_snapshot()
    rules_state = RULE_MANAGER.get_state()
    status.update({
        'automation_enabled': rules_state['automation_enabled'],
        'rule_count': len(rules_state['rules']),
    })
    return status


@app.get('/automation/logs', response_model=Dict[str, Any])
def get_automation_logs(request: Request, days: int = 7, limit: int = 100):
    """Get automation logs from the last N days (default 7, max LOG_RETENTION_DAYS)."""
    _require_credentials(request)
    days = min(max(1, days), LOG_RETENTION_DAYS)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    all_logs = _load_persisted_logs()
    filtered = [
        log for log in all_logs
        if _coerce_datetime(log.get('timestamp')) and _coerce_datetime(log.get('timestamp')) >= cutoff
    ]
    # Sort by timestamp descending (most recent first)
    filtered.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    capped = filtered[:max(1, min(limit, 500))]
    return {
        'logs': capped,
        'total': len(filtered),
        'retention_days': LOG_RETENTION_DAYS,
        'query_days': days,
    }


@app.get('/automation/rules', response_model=Dict[str, Any])
def list_automation_rules(request: Request):
    _require_credentials(request)
    return RULE_MANAGER.get_state()


@app.post('/automation/run', response_model=Dict[str, Any])
def run_automation_now(
    request: Request,
    gmail_client: GmailClient = Depends(get_gmail_client),
):
    _require_credentials(request)
    _append_automation_log('用户手动触发自动化')
    _trigger_automation_run(gmail_client, context='manual')
    return _automation_status_snapshot()


@app.post('/automation/rules', response_model=Dict[str, Any])
def add_automation_rule(
    payload: Dict[str, str],
    request: Request,
    gmail_client: GmailClient = Depends(get_gmail_client),
):
    _require_credentials(request)
    label = (payload.get('label') or '').strip()
    reason = (payload.get('reason') or '').strip()
    if not label or not reason:
        raise HTTPException(status_code=400, detail='Both label and reason are required')

    label_id = None
    if gmail_client.service is not None:
        try:
            label_id = gmail_client.check_or_create_label(label)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f'Unable to ensure label: {exc}') from exc

    rule = RULE_MANAGER.add_rule(label=label, reason=reason, label_id=label_id)
    _append_automation_log(f"新增规则「{label}」：{reason}")
    _reset_processed_email_cache('新增规则')
    _trigger_automation_run(gmail_client, context='rule_added')
    return rule


@app.delete('/automation/rules/{rule_id}', response_model=Dict[str, bool])
def delete_automation_rule(
    rule_id: str,
    request: Request,
    gmail_client: GmailClient = Depends(get_gmail_client),
):
    _require_credentials(request)
    target = RULE_MANAGER.get_rule(rule_id)
    removed = RULE_MANAGER.delete_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail='Rule not found')
    label_name = target.get('label') if isinstance(target, dict) else rule_id
    _append_automation_log(f"删除规则「{label_name or rule_id}」")
    _reset_processed_email_cache('删除规则')
    _trigger_automation_run(gmail_client, context='rule_deleted')
    return {'success': True}


@app.put('/automation/settings', response_model=Dict[str, Any])
def update_automation_settings(
    payload: Dict[str, Any],
    request: Request,
    gmail_client: GmailClient = Depends(get_gmail_client),
):
    _require_credentials(request)
    enabled = bool(payload.get('automation_enabled'))
    was_enabled = RULE_MANAGER.automation_enabled()
    state = RULE_MANAGER.set_automation_enabled(enabled)
    _append_automation_log(f"自动化现已{'开启' if enabled else '关闭'}")
    if enabled:
        if not was_enabled:
            _reset_processed_email_cache('自动化开启')
        _trigger_automation_run(gmail_client, context='automation_enabled')
    return state

@app.get("/")
def read_root():
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    raise HTTPException(status_code=404, detail="index.html not found")

@app.get("/emails", response_model=Dict[str, Any])
def get_emails(
    gmail_client: GmailClient = Depends(get_gmail_client), 
    page: int = 1, 
    per_page: int = 20,
    days: int = 7,
    folder: str = 'inbox'
):
    capped_per_page = min(per_page, 20)
    normalized_folder = canonical_folder_key(folder)
    mailbox = gmail_client.fetch_mailbox_overview(
        active_folder=normalized_folder,
        page=page,
        per_page=capped_per_page,
        days=days
    )
    _persist_recent_emails(mailbox, window_days=14)
    return mailbox


@app.get('/emails/cache', response_model=Dict[str, Any])
def get_cached_emails(request: Request):
    _require_credentials(request)
    payload = _read_cached_payload(EMAIL_CACHE_PATH)
    if payload is None:
        raise HTTPException(status_code=404, detail='No cached emails available')
    return payload

@app.get("/emails/search", response_model=List[Dict[str, Any]])
def search_emails(q: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    # This is a placeholder, as the original gmail_client did not have a generic search function.
    # We will implement this later.
    return []

@app.post("/emails/send")
def send_email(email_data: Dict[str, Any], gmail_client: GmailClient = Depends(get_gmail_client)):
    return gmail_client.send_email(
        to=email_data["to"],
        subject=email_data["subject"],
        body=email_data["body"],
        cc=email_data.get("cc"),
        bcc=email_data.get("bcc"),
    )

@app.post("/emails/{message_id}/reply")
def reply_to_email(message_id: str, body: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    return gmail_client.reply_to_email(message_id=message_id, body=body)

@app.delete("/emails/{message_id}")
def delete_email(message_id: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    return gmail_client.delete_email(message_id=message_id)

@app.post("/emails/{message_id}/read")
def mark_email_as_read(message_id: str, read: bool = True, gmail_client: GmailClient = Depends(get_gmail_client)):
    return {"success": gmail_client.mark_as_read(message_id=message_id, read=read)}

@app.post("/emails/{message_id}/archive")
def archive_email(message_id: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    return {"success": gmail_client.archive_email(message_id=message_id)}

@app.get("/calendar/events", response_model=List[Dict[str, Any]])
def get_calendar_events(
    gcal_client: GCalClient = Depends(get_gcal_client),
    max_results: int = 200,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    month: Optional[str] = None,
):
    now = datetime.now(timezone.utc)

    if month:
        start, end = _month_bounds(month)
        time_min = start.isoformat()
        time_max = end.isoformat()
    else:
        if not time_min:
            time_min = now.isoformat()
        if not time_max:
            time_max = (now + timedelta(days=365)).isoformat()

    events = gcal_client.list_events(max_results=max_results, time_min=time_min, time_max=time_max)

    if gcal_client.service is not None:
        if _calendar_snapshot_is_stale():
            snapshot_events = gcal_client.list_events(
                max_results=max(max_results, 500),
                time_min=(now - timedelta(days=365)).isoformat(),
                time_max=(now + timedelta(days=365)).isoformat(),
            )
            _persist_calendar(snapshot_events, window_days=365)
    else:
        _persist_calendar(events, window_days=365)
    return events


@app.get('/calendar/cache', response_model=Dict[str, Any])
def get_cached_calendar(request: Request):
    _require_credentials(request)
    payload = _read_cached_payload(CALENDAR_CACHE_PATH)
    if payload is None:
        raise HTTPException(status_code=404, detail='No cached calendar snapshot available')
    return payload

@app.post("/calendar/events", response_model=Dict[str, str])
def create_calendar_event(proposal: Dict[str, Any], gcal_client: GCalClient = Depends(get_gcal_client)):
    event_id = gcal_client.create_event(proposal)
    return {"event_id": event_id}

@app.get("/calendar/events/{event_id}", response_model=Optional[Dict[str, Any]])
def get_calendar_event(event_id: str, gcal_client: GCalClient = Depends(get_gcal_client)):
    event = gcal_client.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@app.put("/calendar/events/{event_id}", response_model=Dict[str, str])
def update_calendar_event(event_id: str, updates: Dict[str, Any], gcal_client: GCalClient = Depends(get_gcal_client)):
    updated_event_id = gcal_client.update_event(event_id, updates)
    if not updated_event_id:
        raise HTTPException(status_code=404, detail="Event not found or update failed")
    return {"event_id": updated_event_id}

@app.delete("/calendar/events/{event_id}", response_model=Dict[str, bool])
def delete_calendar_event(event_id: str, gcal_client: GCalClient = Depends(get_gcal_client)):
    if not gcal_client.delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found or delete failed")
    return {"success": True}


@app.get("/{spa_path}", include_in_schema=False)
def serve_spa_routes(spa_path: str):
    """Serve the single-page app for direct deep links like /calendar."""
    if spa_path in SPA_ROUTES:
        return FileResponse(str(INDEX_HTML))
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/{spa_path}/", include_in_schema=False)
def serve_spa_routes_with_slash(spa_path: str):
    return serve_spa_routes(spa_path)

@app.post("/api/emails/{message_id}/summarize")
def summarize_email(message_id: str, gmail_client: GmailClient = Depends(get_gmail_client)):
    safe_message_id = _validate_message_id_or_400(message_id)
    # Fetch the message content
    msg = gmail_client.get_message(safe_message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Email not found")

    # Extract sender and body
    email_from = msg.get("from") if isinstance(msg, dict) else None
    content = None
    if isinstance(msg, dict):
        content = msg.get("html") or msg.get("body") or msg.get("snippet") or msg.get("raw")
    else:
        content = str(msg)

    if not content:
        raise HTTPException(status_code=404, detail="Email content not found")

    # Call the shared OpenAI client directly
    client = LLM_CLIENT
    try:
        result = client.summarize_email(
            email_body=content,
            email_sender=email_from,
        )
        return JSONResponse({
            "summary": result.get("text", ""),
            "proposals": result.get("proposals", [])
        })
    except Exception as exc:
        logger.exception("Summarization failed: %s", exc)
        raise HTTPException(status_code=500, detail="Summarization failed")