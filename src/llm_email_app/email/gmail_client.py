"""Gmail client skeleton.

Replace stubs with real Gmail API calls using googleapiclient.discovery or the Gmail REST endpoints with authorized credentials.
"""
from typing import List, Dict, Optional
import base64
import email as py_email
from email.utils import parseaddr
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except Exception:
    build = None  # type: ignore
    HttpError = Exception  # type: ignore

from llm_email_app.config import settings


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

    def _parse_message(self, msg: dict) -> Dict[str, str]:
        """Parse a Gmail API message resource into a simple dict with id, from, subject, body."""
        headers = {h['name']: h.get('value') for h in msg.get('payload', {}).get('headers', [])}
        from_hdr = headers.get('From') or headers.get('From:') or ''
        subject = headers.get('Subject') or ''

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

        return {'id': msg.get('id'), 'from': from_hdr, 'subject': subject, 'body': body, 'received': received}

    def fetch_recent_emails(self, page: int = 1, per_page: int = 20, days: int = 7) -> List[Dict]:
        """Return a list of recent emails in simplified dict form.

        Each item: {'id': str, 'from': str, 'subject': str, 'body': str}
        """
        # If service missing (libs or config), return stubs for dev
        if self.service is None:
            return [
                {
                    'id': 'stub-1',
                    'from': 'alice@example.com',
                    'subject': 'Meeting request: Q4 roadmap',
                    'body': 'Hi, can we meet next Tuesday at 10am to go over the Q4 roadmap? Regards, Alice'
                },
                {
                    'id': 'stub-2',
                    'from': 'bob@example.com',
                    'subject': 'Quick sync',
                    'body': "Can we do a quick sync tomorrow afternoon?"
                }
            ][:per_page]

        try:
            q = f'newer_than:{days}d'
            
            # Get the list of messages
            request = self.service.users().messages().list(userId='me', q=q, maxResults=per_page)
            
            # Handle pagination
            if page > 1:
                # To get to a specific page, we need to traverse the pages
                # This is not efficient, but it's the way the API works
                for _ in range(page - 1):
                    response = request.execute()
                    page_token = response.get('nextPageToken')
                    if not page_token:
                        return [] # Page number is out of range
                    request = self.service.users().messages().list_next(request, response)

            resp = request.execute()

            msgs = resp.get('messages', [])
            results = []
            for m in msgs:
                mid = m.get('id')
                full = self.service.users().messages().get(userId='me', id=mid, format='full').execute()
                parsed = self._parse_message(full)
                results.append(parsed)
            return results
        except HttpError as e:
            logger.exception('Gmail API error: %s', e)
            # fallback to stubs on API error
            return [
                {
                    'id': 'stub-1',
                    'from': 'alice@example.com',
                    'subject': 'Meeting request: Q4 roadmap',
                    'body': 'Hi, can we meet next Tuesday at 10am to go over the Q4 roadmap? Regards, Alice'
                }
            ]

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
        """Delete an email.
        
        Args:
            message_id: The ID of the email to delete
        
        Returns:
            True if successful, False otherwise
        """
        if self.service is None:
            logger.warning('Gmail service not available; cannot delete email')
            return False
        
        try:
            self.service.users().messages().delete(userId='me', id=message_id).execute()
            logger.info('Email deleted successfully, id: %s', message_id)
            return True
        except HttpError as e:
            logger.exception('Failed to delete email: %s', e)
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
                    return label['id']
            
            # Create label if it doesn't exist
            label_body = {'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
            label = self.service.users().labels().create(userId='me', body=label_body).execute()
            return label['id']
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
