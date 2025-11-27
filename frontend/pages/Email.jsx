// Email.jsx

// NOTE: DOMPurify is loaded globally via <script src="https://unpkg.com/dompurify@3.0.6/dist/purify.min.js">
// so we just use window.DOMPurify here.

const { useState, useMemo, useEffect } = React;

const FOLDER_DISPLAY = [
  { key: 'inbox', label: '收件箱' },
  { key: 'sent', label: '已发送' },
  { key: 'drafts', label: '草稿' },
  { key: 'trash', label: '回收站' },
];

const EmailDetailView = ({ email, onBack }) => {
  const { useMemo } = React;

  // Detect if the body looks like HTML
  const looksLikeHtml = useMemo(
    () => /<\/?[a-z][\s\S]*>/i.test(String(email.body || "")),
    [email.body]
  );

  // Sanitize if HTML
  const sanitizedHtml = useMemo(
    () => (looksLikeHtml ? DOMPurify.sanitize(String(email.body)) : ""),
    [email.body, looksLikeHtml]
  );

  return (
    <div style={{ padding: 16, flex: 1 }}>
      <button
        onClick={onBack}
        style={{
          marginBottom: "16px",
          background: "transparent",
          border: "1px solid #ccc",
          padding: "8px 12px",
          borderRadius: "6px",
          cursor: "pointer",
        }}
      >
        &larr; 返回列表
      </button>

      <div style={{ borderBottom: "1px solid #eee", paddingBottom: "8px", marginBottom: "16px" }}>
        <h2 style={{ margin: 0 }}>{email.subject}</h2>
        <p style={{ margin: "4px 0", color: "#6b7280" }}>From: {email.from}</p>
      </div>

      {looksLikeHtml ? (
        <div
          className="email-body"
          dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
          style={{
            overflowY: "auto",
            minHeight: "60vh",
            maxHeight: "60vh",
            minWidth: "620px",
            maxWidth: "620px",
            margin: "0 auto"
          }}
        />
      ) : (
        <div
          style={{
            whiteSpace: "pre-wrap",
            marginBottom: 16,
            overflowY: "auto",
            minHeight: "60vh",
            maxHeight: "60vh",
            minWidth: "620px",
            maxWidth: "620px",
            margin: "0 auto"
          }}
        >
          {email.body}
        </div>
      )}
    </div>
  );
};

function EmailView({ mailbox, loading, error, onDeleteEmail, selectedEmail, onSelectEmail, page, onPageChange, activeFolder, onFolderChange }) {
  const folderData = mailbox?.folders?.[activeFolder] || { items: [], page, has_next_page: false };
  const emails = folderData.items || [];
  const perPage = mailbox?.per_page || 20;
  const displayEmails = emails.slice(0, perPage);
  const isEmpty = !loading && displayEmails.length === 0;

  const [viewing, setViewing] = useState(selectedEmail || null);

  // summary state lifted here
  const [summary, setSummary] = useState(null);
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    setViewing(selectedEmail || null);
    setSummary(null);       // reset summary when switching emails
    setSummarizing(false);
  }, [selectedEmail]);

  const handleSummarize = async () => {
    if (!viewing) return;
    setSummarizing(true);
    setSummary(null);
    try {
      const res = await fetch(`/api/emails/${encodeURIComponent(viewing.id)}/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      setSummary(data.summary || JSON.stringify(data));
    } catch (err) {
      setSummary(`Request failed: ${err.message}`);
    } finally {
      setSummarizing(false);
    }
  };

  return (
    <div style={{ display: 'flex', gap: 12 }}>
      {/* Left-hand column */}
      <div style={{ display: 'flex', flexDirection: 'column', width: 320, maxHeight: '70vh' }}>
        
        {/* Email list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading ? (
            <p>Loading...</p>
          ) : isEmpty ? (
            <p>没有邮件</p>
          ) : (
            displayEmails.map(e => (
              <div
                key={e.id || e.message_id || e.mid}
                style={{ padding: 8, borderBottom: '1px solid #eee', cursor: 'pointer' }}
                onClick={() => { onSelectEmail && onSelectEmail(e); setViewing(e); }}
              >
                <strong>{e.subject}</strong>
                <div style={{ fontSize: 12, color: '#666' }}>{e.from}</div>
              </div>
            ))
          )}
        </div>

        {/* Pagination controls directly under the list */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          marginTop: 12,
          gap: 12,
          padding: '8px 0'
        }}>
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            style={{
              padding: '8px 16px',
              borderRadius: 999,
              border: '1px solid #cbd5f5',
              background: page === 1 ? '#f1f5f9' : '#fff',
              cursor: page === 1 ? 'not-allowed' : 'pointer'
            }}
          >
            上一页
          </button>
          <div style={{
            padding: '6px 16px',
            borderRadius: 999,
            background: '#eef2ff',
            fontWeight: 600
          }}>
            第 {folderData.page || page} 页
          </div>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={!folderData.has_next_page}
            style={{
              padding: '8px 16px',
              borderRadius: 999,
              border: '1px solid #cbd5f5',
              background: folderData.has_next_page ? '#fff' : '#f1f5f9',
              cursor: folderData.has_next_page ? 'pointer' : 'not-allowed'
            }}
          >
            下一页
          </button>
        </div>
      </div>

      {/* Right-hand detail view + summary block */}
      <div style={{ flex: 1, background: '#fff', borderRadius: 6, boxShadow: '0 0 0 1px #eee inset' }}>
        {viewing ? (
          <>
            <EmailDetailView email={viewing} onBack={() => setViewing(null)} />

            {/* Summary block OUTSIDE, right under the email content */}
            <div style={{ marginTop: 16, maxWidth: "800px", margin: "0 auto", padding: 16 }}>
              <button
                onClick={handleSummarize}
                disabled={summarizing}
                style={{
                  padding: "8px 12px",
                  background: "#1f6feb",
                  color: "#fff",
                  borderRadius: 4,
                  border: "none",
                  cursor: "pointer"
                }}
              >
                {summarizing ? "Summarizing..." : "Summarize"}
              </button>

              <div style={{ marginTop: 16 }}>
                <h3>Summary</h3>
                {summary === null ? (
                  <p style={{ color: "#6b7280" }}>No summary yet. Click "Summarize".</p>
                ) : (
                  <div style={{ whiteSpace: "pre-wrap", background: "#fafafa", padding: 12, borderRadius: 6 }}>
                    {summary}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div style={{ padding: 16 }}>Select an email to view</div>
        )}
      </div>
    </div>
  );
}

// Expose globally so ModernApp can use them
window.EmailView = EmailView;
window.EmailDetailView = EmailDetailView;