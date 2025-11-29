// Email.jsx

// NOTE: DOMPurify is loaded globally via <script src="https://unpkg.com/dompurify@3.3.0/dist/purify.min.js">
// so we just use window.DOMPurify here, with defensive fallbacks if unavailable.

const { useState, useMemo, useEffect, useRef } = React;

const FOLDER_DISPLAY = [
  { key: 'inbox', label: '收件箱' },
  { key: 'sent', label: '已发送' },
  { key: 'drafts', label: '草稿' },
  { key: 'trash', label: '回收站' },
];

const Spinner = () => (
  <div style={{
      width: '16px',
      height: '16px',
      border: '2px solid #ffffff',
      borderTop: '2px solid transparent',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite'
  }}>
      <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
  </div>
);

const EmailDetailView = ({ email, onBack }) => {
  const { useMemo } = React;
  const domPurify = typeof window === "undefined" ? null : window.DOMPurify;

  const bodyString = useMemo(() => String(email.body || ""), [email.body]);

  // Detect if the body looks like HTML only when DOMPurify is ready.
  const looksLikeHtml = useMemo(() => {
    if (!domPurify) {
      return false;
    }
    const candidate = bodyString;
    const lt = candidate.indexOf('<');
    const gt = candidate.indexOf('>');
    if (lt === -1 || gt === -1 || gt <= lt) {
      return false;
    }
    // Basic heuristic: check for balanced-looking tags without relying on regex literals
    const closing = candidate.indexOf('</', lt + 1);
    const opening = candidate.indexOf('<', lt + 1);
    const hasSecondTag = opening !== -1 && (opening + 1 < candidate.length) && candidate[opening + 1] !== ' ';
    return closing !== -1 || hasSecondTag;
  }, [bodyString, domPurify]);

  // Sanitize if HTML
  const sanitizedHtml = useMemo(
    () => (looksLikeHtml && domPurify ? domPurify.sanitize(bodyString) : ""),
    [bodyString, looksLikeHtml, domPurify]
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
          {bodyString}
        </div>
      )}
    </div>
  );
};

function EmailView({ mailbox, loading, fetching, error, onDeleteEmail, selectedEmail, onSelectEmail, page, onPageChange, activeFolder, onFolderChange, onRefresh }) {
  const folderData = mailbox?.folders?.[activeFolder] || { items: [], page, has_next_page: false };
  const emails = folderData.items || [];
  const perPage = mailbox?.per_page || 20;
  const displayEmails = emails.slice(0, perPage);
  const isEmpty = !loading && displayEmails.length === 0;

  const [viewingEmail, setViewingEmail] = useState(selectedEmail || null);
  const latestViewingIdRef = useRef(viewingEmail?.id || null);
  useEffect(() => {
    latestViewingIdRef.current = viewingEmail?.id || null;
  }, [viewingEmail]);

  // summary state lifted here
  const [summary, setSummary] = useState(null);
  const [summarizing, setSummarizing] = useState(false);

  useEffect(() => {
    setViewingEmail(selectedEmail || null);
    setSummary(null);       // reset summary when switching emails
    setSummarizing(false);
  }, [selectedEmail]);

  const handleSummarize = async () => {
    if (!viewingEmail) return;
    const currentEmailId = viewingEmail.id;
    setSummarizing(true);
    setSummary(null);
    try {
      const res = await fetch(`/api/emails/${encodeURIComponent(currentEmailId)}/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (latestViewingIdRef.current === currentEmailId) {
        setSummary(data.summary || JSON.stringify(data));
      }
    } catch (err) {
      if (latestViewingIdRef.current === currentEmailId) {
        setSummary(`Request failed: ${err.message}`);
      }
    } finally {
      if (latestViewingIdRef.current === currentEmailId) {
        setSummarizing(false);
      }
    }
  };

  return (
    <div style={{ display: 'flex', gap: 12 }}>
      {/* Left-hand column */}
      <div style={{ display: 'flex', flexDirection: 'column', width: 320, maxHeight: '70vh' }}>
        
        {/* Folder Header & Refresh */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px', borderBottom: '1px solid #eee' }}>
           <div style={{ fontWeight: 'bold', textTransform: 'capitalize' }}>
             {FOLDER_DISPLAY.find(f => f.key === activeFolder)?.label || activeFolder}
           </div>
           <button 
             onClick={onRefresh}
             style={{
               padding: '4px 8px',
               fontSize: '12px',
               cursor: 'pointer',
               background: '#fff',
               border: '1px solid #ccc',
               borderRadius: '4px'
             }}
           >
             Refresh
           </button>
        </div>

        {/* Email list */}
        <div style={{ flex: 1, overflowY: 'auto', opacity: fetching ? 0.6 : 1, transition: 'opacity 0.2s' }}>
          {loading ? (
            <p>Loading...</p>
          ) : isEmpty ? (
            <p>没有邮件</p>
          ) : (
            displayEmails.map(e => (
              <div
                key={e.id || e.message_id || e.mid}
                style={{ padding: 8, borderBottom: '1px solid #eee', cursor: 'pointer' }}
                onClick={() => { onSelectEmail && onSelectEmail(e); setViewingEmail(e); }}
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
        {viewingEmail ? (
          <>
            <EmailDetailView email={viewingEmail} onBack={() => setViewingEmail(null)} />

            {/* Summary block OUTSIDE, right under the email content */}
            <div style={{ marginTop: 16, maxWidth: "800px", margin: "0 auto", padding: 16 }}>
              <button
                onClick={handleSummarize}
                disabled={summarizing}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: "8px 12px",
                  background: "#1f6feb",
                  color: "#fff",
                  borderRadius: 4,
                  border: "none",
                  cursor: "pointer"
                }}
              >
                {summarizing && <Spinner />}
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