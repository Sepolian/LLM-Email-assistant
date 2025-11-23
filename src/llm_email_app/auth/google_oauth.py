"""Google OAuth helper (skeleton).

This module should handle OAuth flows to obtain credentials for Gmail and Google Calendar.
Use `google-auth-oauthlib` helpers for web or local flows.
"""
from typing import Any, Dict, Optional
import json
from pathlib import Path
import logging
import socket
import threading

logger = logging.getLogger(__name__)

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
except Exception:
    InstalledAppFlow = None  # type: ignore
    Credentials = None  # type: ignore

from llm_email_app.config import settings, BASE_DIR


TOKEN_DIR = Path(BASE_DIR) / 'tokens'
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

# 统一使用 'google' 作为 token 文件名，支持 Gmail 和 GCal
DEFAULT_TOKEN_NAME = 'google'

# OAuth flow 锁，防止同时运行多个 OAuth flow
_oauth_lock = threading.Lock()


def _token_path(name: str = DEFAULT_TOKEN_NAME) -> Path:
    return TOKEN_DIR / f"{name}_token.json"


def _find_free_port(start_port: int = 8080, max_attempts: int = 10) -> int:
    """查找可用的端口号。"""
    for i in range(max_attempts):
        port = start_port + i
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"unable to find available port between {start_port} and {start_port + max_attempts - 1}")


def delete_cached_token(name: str = DEFAULT_TOKEN_NAME) -> bool:
    """Delete a cached token file for the given name. Returns True if deleted."""
    p = _token_path(name)
    try:
        if p.exists():
            p.unlink()
            return True
    except Exception:
        logger.exception('Failed to delete token file %s', p)
    return False


def run_local_oauth_flow(scopes: list, client_id: Optional[str] = None, client_secret: Optional[str] = None, name: str = DEFAULT_TOKEN_NAME) -> Any:
    """Run an installed app local webserver OAuth flow and return credentials.

    - scopes: list of OAuth scopes
    - client_id / client_secret: optional (defaults to env values from `settings`)
    - name: token filename prefix (defaults to 'google' for unified token)

    This will cache tokens to `tokens/{name}_token.json` so subsequent runs are silent.
    If `google-auth-oauthlib` is not installed, raises ImportError.
    """
    if InstalledAppFlow is None:
        raise ImportError("google-auth-oauthlib is required for Google OAuth flow")

    client_id = client_id or settings.GOOGLE_CLIENT_ID
    client_secret = client_secret or settings.GOOGLE_CLIENT_SECRET
    redirect_uri = getattr(settings, 'GOOGLE_OAUTH_REDIRECT_URI', None)

    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment to run OAuth flow")

    token_file = _token_path(name)

    # try to load cached credentials
    if token_file.exists() and Credentials is not None:
        try:
            data = json.loads(token_file.read_text(encoding='utf-8'))
            # 检查已保存的 token 的 scopes
            saved_scopes = data.get('scopes', [])
            # 如果保存的 scopes 不包含所有请求的 scopes，需要重新授权
            required_scopes_set = set(scopes)
            saved_scopes_set = set(saved_scopes) if saved_scopes else set()
            
            if not required_scopes_set.issubset(saved_scopes_set):
                logger.info(f'Cached token scopes ({saved_scopes}) do not include required scopes ({scopes}), starting new flow')
                # 删除旧的 token 文件，然后继续执行新的 OAuth flow
                try:
                    token_file.unlink()
                    logger.info('Deleted old token file with insufficient scopes')
                except Exception:
                    pass
                # 继续执行到下面的新 OAuth flow
            else:
                # scopes 匹配，尝试加载 credentials
                creds = Credentials.from_authorized_user_info(data, scopes=scopes)
                # refresh if expired
                try:
                    from google.auth.transport.requests import Request as _Request  # type: ignore

                    if hasattr(creds, 'expired') and creds.expired and creds.refresh_token:
                        creds.refresh(_Request())
                except Exception:
                    logger.info('Failed to refresh cached credentials; will start new flow')
                    # 如果 refresh 失败，继续执行新的 OAuth flow
                else:
                    # 成功加载并刷新，返回 credentials
                    return creds
        except Exception as e:
            logger.info('Failed to load cached credentials; starting new flow: %s', e)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri] if redirect_uri else ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }
    }

    # 使用锁确保同一时间只有一个 OAuth flow 在运行
    with _oauth_lock:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
        # 查找可用端口以避免冲突
        port = _find_free_port(8080)
        logger.info(f'using port {port} for OAuth flow, requested scopes: {scopes}')
        # run local server; this will open a browser for user consent
        # 使用 prompt='consent' 确保每次都请求所有权限
        try:
            creds = flow.run_local_server(port=port, prompt='consent', open_browser=True)
        except Exception as e:
            logger.exception('OAuth flow failed: %s', e)
            # 如果是 state 不匹配错误，可能是之前的 flow 还在运行，等待一下再重试
            if 'mismatching_state' in str(e) or 'MismatchingState' in str(type(e).__name__):
                logger.warning('State mismatch detected, this may be due to a previous OAuth flow. Please try again.')
                raise RuntimeError('OAuth flow state mismatch. Please close any open browser windows and try again.')
            raise

    # cache token
    try:
        token_file.write_text(creds.to_json(), encoding='utf-8')
    except Exception:
        logger.warning('Unable to write token file; continuing without cache')

    return creds


def refresh_credentials(creds: Any) -> Any:
    """Refresh expired credentials and return updated object."""
    if Credentials is None:
        raise ImportError("google-auth package is required to refresh credentials")
    try:
        if hasattr(creds, 'refresh'):
            from google.auth.transport.requests import Request as _Request  # type: ignore

            creds.refresh(_Request())
        return creds
    except Exception as e:
        raise
