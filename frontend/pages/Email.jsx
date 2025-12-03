// Email.jsx

// NOTE: DOMPurify is loaded globally via <script src="https://unpkg.com/dompurify@3.3.0/dist/purify.min.js">
// so we just use window.DOMPurify here, with defensive fallbacks if unavailable.

const { useState, useMemo, useEffect, useRef } = React;

const getFolderDisplay = (t) => [
  { key: 'inbox', label: t('email.inbox') },
  { key: 'sent', label: t('email.sent') },
  { key: 'drafts', label: t('email.drafts') },
  { key: 'trash', label: t('email.trash') },
];

const Spinner = () => (
  <div
    style={{
      width: 16,
      height: 16,
      border: '2px solid #fff',
      borderTopColor: 'transparent',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite',
    }}
  >
    <style>
      {`@keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }`}
    </style>
  </div>
);

const EmailDetailView = ({ email, onBack }) => {
  const { useMemo } = React;
  const { t } = useTranslation();
  const domPurify = typeof window === 'undefined' ? null : window.DOMPurify;

  const bodyString = useMemo(() => String(email.body || ''), [email.body]);

  // Basic heuristic to determine if the body is HTML; avoids false positives when DOMPurify is missing.
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
    const closing = candidate.indexOf('</', lt + 1);
    const opening = candidate.indexOf('<', lt + 1);
    const hasSecondTag = opening !== -1 && opening + 1 < candidate.length && candidate[opening + 1] !== ' ';
    return closing !== -1 || hasSecondTag;
  }, [bodyString, domPurify]);

  const sanitizedHtml = useMemo(
    () => (looksLikeHtml && domPurify ? domPurify.sanitize(bodyString) : ''),
    [bodyString, looksLikeHtml, domPurify]
  );

  return (
    <div style={{ padding: 16, flex: 1 }}>
      <button
        onClick={onBack}
        style={{
          marginBottom: '16px',
          background: 'transparent',
          border: '1px solid #ccc',
          padding: '8px 12px',
          borderRadius: '6px',
          cursor: 'pointer',
        }}
      >
        {t('email.backToList')}
      </button>

      <div style={{ borderBottom: '1px solid #eee', paddingBottom: '8px', marginBottom: '16px' }}>
        <h2 style={{ margin: 0 }}>{email.subject}</h2>
        <p style={{ margin: '4px 0', color: '#6b7280' }}>From: {email.from}</p>
      </div>

      {looksLikeHtml ? (
        <div
          className="email-body"
          dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
          style={{
            overflowY: 'auto',
            maxHeight: '60vh',
            minWidth: '620px',
            maxWidth: '620px',
            margin: '0 auto',
          }}
        />
      ) : (
        <div
          style={{
            whiteSpace: 'pre-wrap',
            marginBottom: 16,
            overflowY: 'auto',
            maxHeight: '60vh',
            minWidth: '620px',
            maxWidth: '620px',
            margin: '0 auto',
          }}
        >
          {bodyString}
        </div>
      )}
    </div>
  );
};

function EmailView({
  mailbox,
  loading,
  fetching = false,
  error,
  onDeleteEmail,
  selectedEmail,
  onSelectEmail,
  page,
  onPageChange,
  activeFolder,
  onFolderChange,
  onRefresh,
}) {
  const { t } = useTranslation();
  const FOLDER_DISPLAY = getFolderDisplay(t);
  const folders = mailbox?.folders || {};
  const folderData = folders[activeFolder] || { items: [], page: 1, has_next_page: false };
  const emails = folderData.items || [];
  const perPage = mailbox?.per_page || 20;

  const allEmails = useMemo(() => {
    return Object.values(mailbox?.folders || {}).reduce((acc, entry) => {
      if (entry?.items) {
        acc.push(...entry.items);
      }
      return acc;
    }, []);
  }, [mailbox]);

  // Gmail system labels to exclude from custom labels section
  const SYSTEM_LABELS = new Set([
    'INBOX', 'SENT', 'DRAFT', 'DRAFTS', 'TRASH', 'SPAM', 'STARRED', 'UNREAD', 'IMPORTANT',
    'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS', 'CATEGORY_UPDATES', 'CATEGORY_FORUMS',
    'CHAT', 'OPENED', 'ARCHIVED',
  ]);

  const availableLabels = useMemo(() => {
    const set = new Set();
    allEmails.forEach((item) => (item.labels || []).forEach((lbl) => {
      // Only add non-system labels (user-created custom labels)
      if (!SYSTEM_LABELS.has(lbl.toUpperCase())) {
        set.add(lbl);
      }
    }));
    return Array.from(set);
  }, [allEmails]);

  const labelFolders = useMemo(
    () => availableLabels.map((lbl) => ({ key: `label:${lbl}`, label: lbl, isLabel: true })),
    [availableLabels]
  );

  const folderCounts = useMemo(() => {
    const counts = {};
    Object.entries(mailbox?.folders || {}).forEach(([key, data]) => {
      counts[key] = data?.items?.length || 0;
    });
    return counts;
  }, [mailbox]);

  const labelCounts = useMemo(() => {
    const counts = {};
    allEmails.forEach((item) => {
      (item.labels || []).forEach((lbl) => {
        counts[lbl] = (counts[lbl] || 0) + 1;
      });
    });
    return counts;
  }, [allEmails]);

  const derivedEmails = useMemo(() => {
    if (activeFolder && activeFolder.startsWith('label:')) {
      const labelName = activeFolder.replace('label:', '');
      return allEmails.filter((item) => (item.labels || []).includes(labelName));
    }
    return emails;
  }, [activeFolder, emails, allEmails]);

  const activeFolderLabel = useMemo(() => {
    if (!activeFolder) {
      return t('nav.email');
    }
    if (activeFolder.startsWith('label:')) {
      return activeFolder.replace('label:', '');
    }
    const entry = FOLDER_DISPLAY.find((item) => item.key === activeFolder);
    return entry?.label || activeFolder;
  }, [activeFolder, t]);

  const displayEmails = derivedEmails.slice(0, perPage);
  const isEmpty = !loading && displayEmails.length === 0;

  const [viewingEmail, setViewingEmail] = useState(selectedEmail || null);
  const latestViewingIdRef = useRef(viewingEmail?.id || null);
  useEffect(() => {
    latestViewingIdRef.current = viewingEmail?.id || null;
  }, [viewingEmail]);

  const [summary, setSummary] = useState(null);
  const [summarizing, setSummarizing] = useState(false);
  const [proposals, setProposals] = useState([]);
  const [proposalStatuses, setProposalStatuses] = useState({});
  const [draftReply, setDraftReply] = useState(null);
  const [draftReplyStatus, setDraftReplyStatus] = useState(null);
  const [editedDraftBody, setEditedDraftBody] = useState('');

  useEffect(() => {
    setViewingEmail(selectedEmail || null);
    setSummary(null);
    setSummarizing(false);
    setProposals([]);
    setDraftReply(null);
    setDraftReplyStatus(null);
    setEditedDraftBody('');
  }, [selectedEmail]);

  const handleSummarize = async () => {
    if (!viewingEmail) return;
    const currentEmailId = viewingEmail.id;
    setSummarizing(true);
    setSummary(null);
    setProposals([]);
    setDraftReply(null);
    setDraftReplyStatus(null);
    setEditedDraftBody('');
    try {
      const res = await fetch(`/api/emails/${encodeURIComponent(currentEmailId)}/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (latestViewingIdRef.current === currentEmailId) {
        setSummary(data.summary || "");
        setProposals(data.proposals || []);
        if (data.draft_reply) {
          setDraftReply(data.draft_reply);
          setEditedDraftBody(data.draft_reply.body || '');
        }
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

const handleAddToCalendar = async (proposal, idx) => {
  // mark as pending
  setProposalStatuses((prev) => ({ ...prev, [idx]: "Adding..." }));
  try {
    const res = await fetch("/calendar/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(proposal),
    });
    if (res.ok) {
      setProposalStatuses((prev) => ({ ...prev, [idx]: "Added ✓" }));
    } else {
      setProposalStatuses((prev) => ({ ...prev, [idx]: "Failed ✗" }));
    }
  } catch (err) {
    setProposalStatuses((prev) => ({ ...prev, [idx]: "Error ✗" }));
  }
};

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '180px 360px 1fr', gap: 12, minHeight: '70vh' }}>
      {/* Folder column */}
      <div style={{ background: '#fff', borderRadius: 8, padding: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.05)', height: 'fit-content' }}>
        <h4 style={{ margin: '0 0 8px 0', fontSize: 14 }}>{t('email.folders')}</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {FOLDER_DISPLAY.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => onFolderChange && onFolderChange(key)}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 10px',
                borderRadius: 8,
                border: '1px solid',
                borderColor: activeFolder === key ? '#2563eb' : '#e2e8f0',
                background: activeFolder === key ? '#dbeafe' : '#fff',
                cursor: 'pointer',
                fontWeight: activeFolder === key ? 600 : 500,
              }}
            >
              <span>{label}</span>
              <span style={{ fontSize: 12, color: '#64748b' }}>{folderCounts[key] ?? 0}</span>
            </button>
          ))}
        </div>
        {labelFolders.length > 0 && (
          <>
            <h4 style={{ margin: '16px 0 8px 0', fontSize: 14 }}>{t('email.customLabels')}</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {labelFolders.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => onFolderChange && onFolderChange(key)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 10px',
                    borderRadius: 8,
                    border: '1px solid',
                    borderColor: activeFolder === key ? '#2563eb' : '#e2e8f0',
                    background: activeFolder === key ? '#dbeafe' : '#fff',
                    cursor: 'pointer',
                    fontWeight: activeFolder === key ? 600 : 500,
                  }}
                >
                  <span>{label}</span>
                  <span style={{ fontSize: 12, color: '#64748b' }}>{labelCounts[label] || 0}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Email list column */}
      <div style={{ display: 'flex', flexDirection: 'column', background: '#fff', borderRadius: 8, padding: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontWeight: 600 }}>{activeFolderLabel}</span>
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              style={{
                padding: '4px 10px',
                borderRadius: 6,
                border: '1px solid #cbd5f5',
                background: '#fff',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {t('email.refresh')}
            </button>
          )}
        </div>
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            borderTop: '1px solid #f1f5f9',
            opacity: fetching ? 0.6 : 1,
            transition: 'opacity 0.2s ease',
          }}
        >
          {loading ? (
            <p>Loading...</p>
          ) : isEmpty ? (
            <p>{t('email.noEmails')}</p>
          ) : (
            displayEmails.map((e) => (
              <div
                key={e.id || e.message_id || e.mid}
                style={{ padding: 10, borderBottom: '1px solid #f1f5f9', cursor: 'pointer' }}
                onClick={() => {
                  onSelectEmail && onSelectEmail(e);
                  setViewingEmail(e);
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: 14 }}>{e.subject || t('email.noSubject')}</strong>
                  <span style={{ fontSize: 12, color: '#94a3b8' }}>
                    {new Date(e.received || Date.now()).toLocaleDateString()}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: '#666' }}>{e.from}</div>
                <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {(e.labels || []).map((lbl) => (
                    <span
                      key={lbl}
                      style={{ fontSize: 11, padding: '2px 6px', borderRadius: 999, background: '#eef2ff', color: '#4338ca' }}
                    >
                      {lbl}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            marginTop: 12,
            gap: 12,
            padding: '8px 0',
          }}
        >
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            style={{
              padding: '8px 16px',
              borderRadius: 999,
              border: '1px solid #cbd5f5',
              background: page === 1 ? '#f1f5f9' : '#fff',
              cursor: page === 1 ? 'not-allowed' : 'pointer',
            }}
          >
            {t('email.prevPage')}
          </button>
          <div
            style={{
              padding: '6px 16px',
              borderRadius: 999,
              background: '#eef2ff',
              fontWeight: 600,
            }}
          >
            {t('email.page')} {folderData.page || page}
          </div>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={!folderData.has_next_page}
            style={{
              padding: '8px 16px',
              borderRadius: 999,
              border: '1px solid #cbd5f5',
              background: folderData.has_next_page ? '#fff' : '#f1f5f9',
              cursor: folderData.has_next_page ? 'pointer' : 'not-allowed',
            }}
          >
            {t('email.nextPage')}
          </button>
        </div>
      </div>

      {/* Detail column */}
      <div style={{ background: '#fff', borderRadius: 6, boxShadow: '0 0 0 1px #eee inset' }}>
        {viewingEmail ? (
          <>
            <EmailDetailView email={viewingEmail} onBack={() => setViewingEmail(null)} />
            <div style={{ marginTop: 16, maxWidth: '800px', margin: '0 auto', padding: 16 }}>
              <button
                onClick={handleSummarize}
                disabled={summarizing}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 12px',
                  background: '#1f6feb',
                  color: '#fff',
                  borderRadius: 4,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                {summarizing && <Spinner />}
                {summarizing ? 'Summarizing...' : 'Summarize'}
              </button>

              <div style={{ marginTop: 16 }}>
                <h3>Summary</h3>
                {summary === null ? (
                  <p style={{ color: '#6b7280' }}>No summary yet. Click "Summarize".</p>
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12, borderRadius: 6 }}>
                    {summary}
                  </div>
                )}
              </div>
              {proposals.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <h3>Proposals</h3>
                  {proposals.map((p, idx) => (
                    <div key={idx} style={{ border: '1px solid #ddd', padding: 12, borderRadius: 6, marginBottom: 8 }}>
                      <p><strong>{p.title}</strong></p>
                      <p>{new Date(p.start).toLocaleString()} - {new Date(p.end).toLocaleString()}</p>
                      {p.location && <p> {p.location}</p>}
                      {p.notes && <p> {p.notes}</p>}
                      <button
                        onClick={() => handleAddToCalendar(p, idx)}
                        style={{
                          disabled: proposalStatuses[idx] === "Added ✓", // Disable when added
                          marginTop: 8,
                          padding: '6px 10px',
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          background: proposalStatuses[idx] === "Added ✓" ? "#9ca3af" : "#1f6feb", // gray if added
                          color: "#fff",
                          border: "none",
                          borderRadius: 4,
                          cursor: proposalStatuses[idx] === "Added ✓" ? "not-allowed" : "pointer",
                        }}
                      >
                        {proposalStatuses[idx] === "Adding..." && <Spinner />}
                        {proposalStatuses[idx] || "Add to Calendar"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {draftReply && (
                <div style={{ marginTop: 16 }}>
                  <h3>{t('email.draftReply')}</h3>
                  <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 6 }}>
                    <div style={{ marginBottom: 8 }}>
                      <label style={{ fontWeight: 500, fontSize: 13, color: '#374151' }}>{t('email.subject')}:</label>
                      <div style={{ 
                        padding: '8px 12px', 
                        background: '#f3f4f6', 
                        borderRadius: 4, 
                        marginTop: 4,
                        fontSize: 14 
                      }}>
                        {draftReply.subject}
                      </div>
                    </div>
                    <div style={{ marginBottom: 12 }}>
                      <label style={{ fontWeight: 500, fontSize: 13, color: '#374151' }}>{t('email.body')}:</label>
                      <textarea
                        value={editedDraftBody}
                        onChange={(e) => setEditedDraftBody(e.target.value)}
                        style={{
                          width: '100%',
                          minHeight: 150,
                          padding: '8px 12px',
                          background: '#f3f4f6',
                          border: 'none',
                          borderRadius: 4,
                          marginTop: 4,
                          fontSize: 14,
                          fontFamily: 'inherit',
                          resize: 'vertical',
                          lineHeight: 1.5,
                          boxSizing: 'border-box',
                        }}
                      />
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={async () => {
                          if (draftReplyStatus === 'saving') return;
                          setDraftReplyStatus('saving');
                          try {
                            const res = await fetch('/emails/drafts', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({
                                to: viewingEmail?.from || '',
                                subject: draftReply.subject,
                                body: editedDraftBody,
                                reply_to_message_id: viewingEmail?.id,
                              }),
                            });
                            if (res.ok) {
                              setDraftReplyStatus('saved');
                              setTimeout(() => {
                                setDraftReply(null);
                                setEditedDraftBody('');
                                setDraftReplyStatus(null);
                              }, 1500);
                            } else {
                              setDraftReplyStatus('error');
                              setTimeout(() => setDraftReplyStatus(null), 2000);
                            }
                          } catch (err) {
                            setDraftReplyStatus('error');
                            setTimeout(() => setDraftReplyStatus(null), 2000);
                          }
                        }}
                        disabled={draftReplyStatus === 'saving' || draftReplyStatus === 'saved'}
                        style={{
                          padding: '6px 12px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          background: draftReplyStatus === 'saved' ? '#22c55e' : draftReplyStatus === 'error' ? '#ef4444' : '#1f6feb',
                          color: '#fff',
                          border: 'none',
                          borderRadius: 4,
                          cursor: draftReplyStatus === 'saving' || draftReplyStatus === 'saved' ? 'not-allowed' : 'pointer',
                          fontSize: 13,
                        }}
                      >
                        {draftReplyStatus === 'saving' && <Spinner />}
                        {draftReplyStatus === 'saved' ? t('email.draftSaved') : 
                         draftReplyStatus === 'error' ? t('email.draftError') : 
                         t('email.addToDraft')}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <div style={{ padding: 16 }}>{t('email.selectEmail')}</div>
        )}
      </div>
    </div>
  );
}

// Expose globally so ModernApp can use them
window.EmailView = EmailView;
window.EmailDetailView = EmailDetailView;
