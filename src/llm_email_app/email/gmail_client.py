"""Gmail client skeleton.

Replace stubs with real Gmail API calls using googleapiclient.discovery or the Gmail REST endpoints with authorized credentials.
"""
from typing import List, Dict, Optional, Any
import base64
import email as py_email
from email.utils import parseaddr
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None  # type: ignore
    HttpError = Exception  # type: ignore

from llm_email_app.config import settings

FOLDER_LABELS: Dict[str, str] = {
    'inbox': 'INBOX',
    'sent': 'SENT',
    'drafts': 'DRAFT',
    'trash': 'TRASH',
}

FOLDER_ALIASES: Dict[str, str] = {
    'junk': 'trash',  # backward compatibility for legacy front-end routes
}


def canonical_folder_key(folder: Optional[str]) -> str:
    key = (folder or 'inbox').lower()
    return FOLDER_ALIASES.get(key, key)


class GmailClient:
    """Gmail client that uses Google APIs when configured, otherwise falls back to stubs.

    Behavior:
    - If `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are present in env/.env, try to run OAuth flow
      and build a Gmail service.
    - If google API libs are not installed or env vars missing, return stubbed emails (for local dev).
    """

    def __init__(self, creds: object = None):
        self.creds = creds
        self.service = None
        self._label_cache: Dict[str, str] = {}
        if build is None:
            logger.info('googleapiclient not installed; GmailClient will return stubbed emails')
            return

        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            logger.info('Google client id/secret not configured; GmailClient will return stubbed emails')
            return

        try:
            # 只有在提供了 creds 时才构建服务
            # 不自动触发 OAuth flow，应该由调用者（如 GUI）统一处理
            if creds:
                self.creds = creds
                self.service = build('gmail', 'v1', credentials=creds)
            else:
                # 如果没有提供 creds，不自动触发 OAuth，返回 None service（使用 stubs）
                logger.info('No credentials provided; GmailClient will return stubbed emails')
                self.creds = None
                self.service = None
        except Exception as e:
            logger.exception('Failed to initialize Gmail service; falling back to stubs: %s', e)
            self.service = None

    def _refresh_label_cache(self) -> Dict[str, str]:
        """Fetch Gmail labels and memoize id->name lookups."""
        if self.service is None:
            return self._label_cache
        try:
            labels = self.service.users().labels().list(userId='me').execute().get('labels', [])
            self._label_cache = {
                label['id']: label.get('name', label['id'])
                for label in labels
                if label.get('id')
            }
        except HttpError as exc:
            logger.warning('Unable to refresh Gmail label cache: %s', exc)
        return self._label_cache

    def _label_names_from_ids(self, label_ids: List[str]) -> List[str]:
        if not label_ids:
            return []
        cache = self._label_cache or self._refresh_label_cache()
        return [cache.get(label_id, label_id) for label_id in label_ids]

    def _parse_message(self, msg: dict) -> Dict[str, str]:
        """Parse a Gmail API message resource into a simple dict with id, from, subject, body."""
        headers = {h['name']: h.get('value') for h in msg.get('payload', {}).get('headers', [])}
        from_hdr = headers.get('From') or headers.get('From:') or ''
        subject = headers.get('Subject') or ''
        snippet = msg.get('snippet', '')

        body = ''
        payload = msg.get('payload', {})
        if 'parts' in payload:
            # walk parts to find text/plain
            for part in payload.get('parts', []):
                mime = part.get('mimeType', '')
                if mime == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')
                        break
                # fallback to first part
            if not body:
                # try first part payload
                first = payload.get('parts', [])[0]
                data = first.get('body', {}).get('data')
                if data:
                    body = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')
        else:
            data = payload.get('body', {}).get('data')
            if data:
                body = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='replace')

        # simple cleanup: if body seems to be raw email, parse and extract payload
        if body and '\n\n' in body and 'From:' in body[:200]:
            try:
                parsed = py_email.message_from_string(body)
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == 'text/plain':
                            body = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                            break
                else:
                    body = parsed.get_payload(decode=True).decode(parsed.get_content_charset() or 'utf-8', errors='replace')
            except Exception:
                pass

        # try to extract receive/internal date (milliseconds since epoch)
        received = None
        try:
            internal = msg.get('internalDate') or msg.get('internal_date')
            if internal:
                # internalDate is milliseconds since epoch
                ts = int(internal) / 1000.0
                received = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            received = None

        label_ids = msg.get('labelIds') or []
        return {
            'id': msg.get('id'),
            'from': from_hdr,
            'subject': subject,
            'body': body,
            'snippet': snippet,
            'received': received,
            'label_ids': label_ids,
            'labels': self._label_names_from_ids(label_ids),
        }

    def _generate_stub_emails(self, label_key: str, limit: int) -> List[Dict[str, Any]]:
        """Return deterministic stub data per mailbox for local development."""
        now = datetime.now(timezone.utc)
        fixtures = {
            'inbox': [
                {
                    'id': 'stub-inbox-1',
                    'from': 'alice@example.com',
                    'subject': 'Meeting request: Q4 roadmap',
                    'body': 'Hi, can we meet next Tuesday at 10am to go over the Q4 roadmap? Regards, Alice'
                },
                {
                    'id': 'stub-inbox-2',
                    'from': 'bob@example.com',
                    'subject': 'Quick sync',
                    'body': 'Can we do a quick sync tomorrow afternoon?'
                },
            ],
            'sent': [
                {
                    'id': 'stub-sent-1',
                    'from': 'you@example.com',
                    'subject': 'Weekly status recap',
                    'body': 'Sent over the highlights for this week—let me know if questions.'
                }
            ],
            'drafts': [
                {
                    'id': 'stub-draft-1',
                    'from': 'you@example.com',
                    'subject': 'Draft: Contract follow-up',
                    'body': 'Need to confirm pricing section before sending.'
                }
            ],
            'trash': [
                {
                    'id': 'stub-trash-1',
                    'from': 'promo@example.net',
                    'subject': 'Limited time winnings!!!',
                    'body': 'Click now to claim your prize.'
                }
            ],
        }
        data = fixtures.get(label_key, fixtures['inbox'])
        stub_label = FOLDER_LABELS.get(label_key, label_key.upper())
        enriched: List[Dict[str, Any]] = []
        for idx, item in enumerate(data):
            enriched_item = dict(item)
            if 'received' not in enriched_item:
                enriched_item['received'] = (now - timedelta(hours=idx * 3)).isoformat()
            enriched_item.setdefault('labels', [stub_label])
            enriched_item.setdefault('label_ids', [stub_label])
            enriched.append(enriched_item)
        return enriched[:limit]

    def _fetch_label_snapshot(self, label_key: str, page: int, per_page: int, days: int) -> Dict[str, Any]:
        label_id = FOLDER_LABELS[label_key]
        per_page = max(1, min(per_page, 50))

        if self.service is None:
            return {
                'label': label_id,
                'page': 1,
                'has_next_page': False,
                'items': self._generate_stub_emails(label_key, per_page)
            }

        try:
            q = f'newer_than:{days}d'
            kwargs = {
                'userId': 'me',
                'labelIds': [label_id],
                'maxResults': per_page,
                'q': q
            }
            request = self.service.users().messages().list(**kwargs)
            current_page = 1
            response = request.execute()
            while current_page < page and response.get('nextPageToken'):
                current_page += 1
                request = self.service.users().messages().list(
                    userId='me',
                    labelIds=[label_id],
                    maxResults=per_page,
                    q=q,
                    pageToken=response['nextPageToken']
                )
                response = request.execute()

            if current_page < page:
                return {
                    'label': label_id,
                    'page': current_page,
                    'has_next_page': False,
                    'items': []
                }

            msgs = response.get('messages', [])
            results: List[Dict[str, Any]] = []
            for m in msgs:
                mid = m.get('id')
                if not mid:
                    continue
                full = self.service.users().messages().get(userId='me', id=mid, format='full').execute()
                parsed = self._parse_message(full)
                results.append(parsed)

            return {
                'label': label_id,
                'page': current_page,
                'has_next_page': bool(response.get('nextPageToken')),
                'items': results
            }
        except HttpError as e:
            logger.exception('Gmail API error while fetching label %s: %s', label_id, e)
            return {
                'label': label_id,
                'page': 1,
                'has_next_page': False,
                'items': self._generate_stub_emails(label_key, per_page)
            }

    def fetch_mailbox_overview(
        self,
        active_folder: str = 'inbox',
        page: int = 1,
        per_page: int = 20,
        days: int = 7
    ) -> Dict[str, Any]:
        """Fetch a multi-folder snapshot including inbox, sent, drafts, and trash."""
        normalized_key = canonical_folder_key(active_folder)
        normalized = normalized_key if normalized_key in FOLDER_LABELS else 'inbox'
        per_page = max(1, min(per_page, 50))
        overview: Dict[str, Any] = {}
        for folder_key in FOLDER_LABELS.keys():
            folder_page = page if folder_key == normalized else 1
            overview[folder_key] = self._fetch_label_snapshot(folder_key, folder_page, per_page, days)

        return {
            'active_folder': normalized,
            'page': page,
            'per_page': per_page,
            'days': days,
            'folders': overview
        }

    def fetch_recent_emails(self, page: int = 1, per_page: int = 20, days: int = 7) -> List[Dict]:
        """Backward-compatible helper returning inbox items only."""
        overview = self.fetch_mailbox_overview(active_folder='inbox', page=page, per_page=per_page, days=days)
        return overview.get('folders', {}).get('inbox', {}).get('items', [])

    def fetch_emails_since(self, days: int = 7, max_results: Optional[int] = None) -> List[Dict]:
        """Fetch emails from the authenticated user's mailbox from the past `days` days.

        If not authenticated, returns the same stubbed emails as `fetch_recent_emails`.
        """
        # If service missing, return stubs
        if self.service is None:
            return self.fetch_recent_emails(max_results=max_results or 5)

        # Gmail search operator 'newer_than:Xd' is convenient
        q = f'newer_than:{days}d'
        try:
            req = self.service.users().messages().list(userId='me', q=q)
            if max_results:
                req = self.service.users().messages().list(userId='me', q=q, maxResults=max_results)
            resp = req.execute()
            msgs = resp.get('messages', [])
            results = []
            for m in msgs:
                mid = m.get('id')
                full = self.service.users().messages().get(userId='me', id=mid, format='full').execute()
                parsed = self._parse_message(full)
                results.append(parsed)
            return results
        except HttpError as e:
            logger.exception('Gmail API error while fetching by time: %s', e)
            return self.fetch_recent_emails(max_results=max_results or 5)

    def fetch_emails_by_label(self, label: str = 'INBOX', max_results: Optional[int] = None) -> List[Dict]:
        """Fetch emails from a specific label (folder).
        
        Args:
            label: The label name, e.g., 'INBOX' (Inbox), 'SENT' (Sent), 'TRASH' (Trash), 'ARCHIVE' (Archive)
            max_results: The maximum number of results to return
        
        Returns:
            The list of emails
        """
        if self.service is None:
            return self.fetch_recent_emails(max_results=max_results or 5)
        
        try:
            req = self.service.users().messages().list(userId='me', labelIds=[label])
            if max_results:
                req = req.maxResults(max_results)
            resp = req.execute()
            msgs = resp.get('messages', [])
            results = []
            for m in msgs:
                mid = m.get('id')
                full = self.service.users().messages().get(userId='me', id=mid, format='full').execute()
                parsed = self._parse_message(full)
                results.append(parsed)
            return results
        except HttpError as e:
            logger.exception('Gmail API error while fetching by label: %s', e)
            return []

    def send_email(self, to: str, subject: str, body: str, cc: Optional[str] = None, bcc: Optional[str] = None) -> str:
        """Send an email.
        
        Args:
            to: The recipient email address (multiple addresses separated by commas)
            subject: The subject of the email
            body: The body of the email
            cc: The carbon copy email addresses (optional, multiple addresses separated by commas)
            bcc: The blind carbon copy email addresses (optional, multiple addresses separated by commas)
        
        Returns:
            The ID of the sent email
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot send email')
            return 'stub-sent-id'
        
        try:
            # 构建邮件消息
            message = py_email.message.EmailMessage()
            message['To'] = to
            message['Subject'] = subject
            if cc:
                message['Cc'] = cc
            if bcc:
                message['Bcc'] = bcc
            message.set_content(body)
            
            # 编码为 base64url
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # 发送邮件
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info('Email sent successfully, id: %s', result.get('id'))
            return result.get('id')
        except HttpError as e:
            logger.exception('Failed to send email: %s', e)
            raise

    def reply_to_email(self, message_id: str, body: str) -> str:
        """Reply to an email.
        
        Args:
            message_id: The ID of the email to reply to
            body: The body of the reply
        
        Returns:
            The ID of the sent email
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot reply to email')
            return 'stub-reply-id'
        
        try:
            # 获取原始邮件
            original = self.service.users().messages().get(userId='me', id=message_id, format='full').execute()
            headers = {h['name']: h.get('value') for h in original.get('payload', {}).get('headers', [])}
            
            # 正确解析发件人邮箱地址
            from_header = headers.get('From', '')
            # 使用 parseaddr 来正确提取邮箱地址（处理 "Name <email@example.com>" 格式）
            _, from_email = parseaddr(from_header)
            if not from_email:
                # 如果没有找到邮箱地址，尝试直接使用原始值
                from_email = from_header.strip()
            
            # 构建回复消息
            message = py_email.message.EmailMessage()
            message['To'] = from_email
            message['Subject'] = 'Re: ' + headers.get('Subject', '')
            message['In-Reply-To'] = headers.get('Message-ID', '')
            message['References'] = headers.get('Message-ID', '')
            message.set_content(body)
            
            # 编码为 base64url
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # 发送回复
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message, 'threadId': original.get('threadId')}
            ).execute()
            
            logger.info('Reply sent successfully, id: %s', result.get('id'))
            return result.get('id')
        except HttpError as e:
            logger.exception('Failed to reply to email: %s', e)
            raise

    def delete_email(self, message_id: str) -> bool:
        """Move an email to Gmail Trash."""
        if self.service is None:
            logger.warning('Gmail service not available; cannot move email to trash')
            return False

        try:
            self.service.users().messages().trash(userId='me', id=message_id).execute()
            logger.info('Email moved to trash, id: %s', message_id)
            return True
        except HttpError as e:
            logger.exception('Failed to move email to trash: %s', e)
            return False

    def mark_as_read(self, message_id: str, read: bool = True) -> bool:
        """Mark an email as read or unread.
        
        Args:
            message_id: The ID of the email
            read: True if read, False if unread
        
        Returns:
            True if successful, False otherwise
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot mark email')
            return False
        
        try:
            if read:
                # 移除 UNREAD 标签
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
            else:
                # 添加 UNREAD 标签
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body={'addLabelIds': ['UNREAD']}
                ).execute()
            logger.info('Email marked as %s, id: %s', 'read' if read else 'unread', message_id)
            return True
        except HttpError as e:
            logger.exception('Failed to mark email: %s', e)
            return False

    def archive_email(self, message_id: str) -> bool:
        """Archive an email.
        
        Args:
            message_id: The ID of the email
        
        Returns:
            True if successful, False otherwise
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot archive email')
            return False
        
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['INBOX']}
            ).execute()
            logger.info('Email archived successfully, id: %s', message_id)
            return True
        except HttpError as e:
            logger.exception('Failed to archive email: %s', e)
            return False

    def check_or_create_label(self, label_name: str) -> str:
        """Check if a label exists, and create it if it doesn't.
        
        Args:
            label_name: The name of the label
        
        Returns:
            The ID of the label
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot check or create label')
            return 'stub-label-id'
        
        try:
            # Check if label exists
            labels = self.service.users().labels().list(userId='me').execute().get('labels', [])
            for label in labels:
                if label['name'] == label_name:
                    label_id = label['id']
                    self._label_cache[label_id] = label_name
                    return label_id
            
            # Create label if it doesn't exist
            label_body = {'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
            label = self.service.users().labels().create(userId='me', body=label_body).execute()
            label_id = label['id']
            self._label_cache[label_id] = label_name
            return label_id
        except HttpError as e:
            logger.exception('Failed to check or create label: %s', e)
            raise

    def apply_labels_to_message(self, message_id: str, label_ids: List[str]) -> bool:
        """Apply labels to a message.
        
        Args:
            message_id: The ID of the message
            label_ids: The IDs of the labels to apply
        
        Returns:
            True if successful, False otherwise
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot apply labels to message')
            return False
        
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': label_ids}
            ).execute()
            return True
        except HttpError as e:
            logger.exception('Failed to apply labels to message: %s', e)
            return False

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single Gmail message by ID and parse it into a dict with id, from, subject, body, received."""
        if self.service is None:
            # Stub fallback: return a fake message for local dev
            return {
                "id": message_id,
                "from": "stub@example.com",
                "subject": "Stub email",
                "body": "This is a stubbed email body for testing.",
                "received": datetime.now(timezone.utc).isoformat(),
            }
        try:
            full = self.service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()

            # Use your existing parser
            parsed = self._parse_message(full)

            # Add fallbacks if body is empty
            if not parsed.get("body"):
                parsed["body"] = full.get("snippet") or ""
                # Sometimes raw payload exists
                if not parsed["body"]:
                    payload = full.get("payload", {})
                    data = payload.get("body", {}).get("data")
                    if data:
                        try:
                            parsed["body"] = base64.urlsafe_b64decode(data.encode("utf-8")).decode(
                                "utf-8", errors="replace"
                            )
                        except Exception:
                            parsed["body"] = ""

            return parsed
        except HttpError as e:
            logger.exception("Failed to fetch Gmail message %s: %s", message_id, e)
            return None
