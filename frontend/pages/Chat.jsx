const { useEffect, useMemo, useState } = React;

const THREAD_STATUS_TONES = {
  ready: { background: '#f1f5f9', color: '#334155', border: '#cbd5e1' },
  in_progress: { background: '#dbeafe', color: '#1d4ed8', border: '#93c5fd' },
  needs_input: { background: '#fef3c7', color: '#92400e', border: '#fcd34d' },
  completed: { background: '#dcfce7', color: '#166534', border: '#86efac' },
};

const THREAD_KIND_TONES = {
  official: { background: '#ede9fe', color: '#6d28d9', border: '#c4b5fd' },
  free: { background: '#ecfeff', color: '#155e75', border: '#a5f3fc' },
};

const QUICK_PROMPTS = [
  { labelKey: 'chat.quickShowSchedule', valueKey: 'chat.quickShowScheduleAction' },
  { labelKey: 'chat.quickSearchEmails', valueKey: 'chat.quickSearchEmailsAction' },
  { labelKey: 'chat.quickListEmails', valueKey: 'chat.quickListEmailsAction' },
];

const asArray = (value) => (Array.isArray(value) ? value : []);

const formatDateTime = (value) => {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString();
};

const excerpt = (value, maxLength = 120) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}...` : text;
};

const threadTitle = (thread) => {
  if (!thread) return '';
  return thread.thread_title || thread.title || thread.thread_id || '';
};

const threadStatusLabel = (status, t) => {
  const key = `chat.status.${status || 'ready'}`;
  const translated = t(key);
  return translated === key ? (status || 'ready') : translated;
};

const threadKindLabel = (kind, t) => {
  const key = `chat.threadKind.${kind || 'free'}`;
  const translated = t(key);
  return translated === key ? (kind || 'free') : translated;
};

const roleLabel = (role, t) => {
  if (role === 'user') return t('chat.role.user');
  if (role === 'assistant') return t('chat.role.assistant');
  return t('chat.role.system');
};

const formatEventRange = (item) => {
  if (!item) return '';
  const start =
    item.start?.dateTime ||
    item.start?.date ||
    item.start ||
    item.start_time ||
    item.time_min ||
    '';
  const end =
    item.end?.dateTime ||
    item.end?.date ||
    item.end ||
    item.end_time ||
    item.time_max ||
    '';
  if (!start && !end) return '';
  if (!end) return formatDateTime(start);
  return `${formatDateTime(start)} - ${formatDateTime(end)}`;
};

const findPreferredThreadId = (threads, workItems, currentId) => {
  if (currentId && threads.some((item) => item.thread_id === currentId)) {
    return currentId;
  }
  const pending = workItems.find((item) => threads.some((thread) => thread.thread_id === item.thread_id));
  if (pending) return pending.thread_id;
  const active = threads.find((item) => item.status && item.status !== 'ready');
  if (active) return active.thread_id;
  const flagship = threads.find((item) => item.script_id === 'flagship_conflict');
  if (flagship) return flagship.thread_id;
  const free = threads.find((item) => item.thread_kind === 'free');
  if (free) return free.thread_id;
  return threads[0]?.thread_id || null;
};

const toneStyle = (tone) => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '4px 8px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
  background: tone.background,
  color: tone.color,
  border: `1px solid ${tone.border}`,
});

const panelStyle = {
  background: '#fff',
  border: '1px solid #e2e8f0',
  borderRadius: 8,
  padding: 16,
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail =
      (payload && typeof payload === 'object' && payload.detail) ||
      (typeof payload === 'string' ? payload : null) ||
      `Request failed: ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

const ChatView = () => {
  const { t } = useTranslation();
  const [threads, setThreads] = useState([]);
  const [workItems, setWorkItems] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [settings, setSettings] = useState({ agent_mode: 'semi_auto' });
  const [selectedThreadId, setSelectedThreadId] = useState(null);
  const [input, setInput] = useState('');
  const [openWorkItemId, setOpenWorkItemId] = useState(null);
  const [draftReview, setDraftReview] = useState({ subject: '', body: '' });
  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [busyKey, setBusyKey] = useState('');
  const [error, setError] = useState('');
  const [isNarrow, setIsNarrow] = useState(() => window.innerWidth < 1180);

  useEffect(() => {
    const onResize = () => setIsNarrow(window.innerWidth < 1180);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.thread_id === selectedThreadId) || null,
    [threads, selectedThreadId]
  );

  const selectedWorkItem = useMemo(() => {
    const preferredId = openWorkItemId || selectedThread?.active_work_item_id || null;
    if (preferredId) {
      const found = workItems.find((item) => item.id === preferredId);
      if (found) return found;
    }
    return workItems.find((item) => item.thread_id === selectedThreadId) || null;
  }, [openWorkItemId, selectedThread, selectedThreadId, workItems]);

  const officialThreads = useMemo(
    () => threads.filter((thread) => thread.thread_kind === 'official'),
    [threads]
  );
  const inboxCount = workItems.length;

  const loadTimeline = async (threadId) => {
    if (!threadId) {
      setTimeline([]);
      return [];
    }
    setThreadLoading(true);
    try {
      const data = await fetchJson(`/agent/threads/${encodeURIComponent(threadId)}/timeline`);
      const nextTimeline = asArray(data.timeline);
      setTimeline(nextTimeline);
      return nextTimeline;
    } finally {
      setThreadLoading(false);
    }
  };

  const refreshDashboard = async ({ preferredThreadId = null, preferredWorkItemId } = {}) => {
    const [threadsData, workItemsData, settingsData] = await Promise.all([
      fetchJson('/agent/threads?limit=50'),
      fetchJson('/agent/work-items?status=pending&limit=50'),
      fetchJson('/automation/extra-settings'),
    ]);

    const nextThreads = asArray(threadsData.threads);
    const nextWorkItems = asArray(workItemsData.work_items);
    const nextThreadId = findPreferredThreadId(nextThreads, nextWorkItems, preferredThreadId || selectedThreadId);

    setThreads(nextThreads);
    setWorkItems(nextWorkItems);
    setSettings(settingsData || { agent_mode: 'semi_auto' });
    setSelectedThreadId(nextThreadId);

    const nextOpenWorkItemId =
      preferredWorkItemId !== undefined
        ? preferredWorkItemId
        : nextWorkItems.find((item) => item.thread_id === nextThreadId)?.id || null;
    setOpenWorkItemId(nextOpenWorkItemId);

    await loadTimeline(nextThreadId);
  };

  useEffect(() => {
    let cancelled = false;

    const initialize = async () => {
      setLoading(true);
      setError('');
      try {
        await refreshDashboard();
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load agent workspace.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedWorkItem?.type === 'draft_review') {
      setDraftReview({
        subject: selectedWorkItem.context?.subject || '',
        body: selectedWorkItem.context?.body || '',
      });
    } else {
      setDraftReview({ subject: '', body: '' });
    }
  }, [selectedWorkItem?.id]);

  const selectThread = async (threadId, workItemId = null) => {
    setSelectedThreadId(threadId);
    setOpenWorkItemId(workItemId);
    setError('');
    try {
      await loadTimeline(threadId);
    } catch (err) {
      setError(err.message || 'Failed to load timeline.');
    }
  };

  const handleStartDemo = async (scriptId) => {
    setBusyKey(`start:${scriptId}`);
    setError('');
    try {
      const result = await fetchJson('/agent/demo/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_id: scriptId }),
      });
      await refreshDashboard({
        preferredThreadId: result.thread_id,
        preferredWorkItemId: result.pending_work_item ? result.work_item_id : null,
      });
    } catch (err) {
      setError(err.message || 'Failed to start the demo script.');
    } finally {
      setBusyKey('');
    }
  };

  const handleResetDemo = async () => {
    setBusyKey('reset');
    setError('');
    try {
      await fetchJson('/agent/demo/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope: 'full' }),
      });
      await refreshDashboard({ preferredThreadId: 'demo-flagship-conflict', preferredWorkItemId: null });
    } catch (err) {
      setError(err.message || 'Failed to reset the demo state.');
    } finally {
      setBusyKey('');
    }
  };

  const handleModeChange = async (mode) => {
    if (mode === settings.agent_mode) return;
    setBusyKey(`mode:${mode}`);
    setError('');
    try {
      const nextSettings = await fetchJson('/automation/extra-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_mode: mode }),
      });
      setSettings(nextSettings || {});
    } catch (err) {
      setError(err.message || 'Failed to update the agent mode.');
    } finally {
      setBusyKey('');
    }
  };

  const handleSend = async (event) => {
    event.preventDefault();
    if (!selectedThreadId || !input.trim()) return;
    setBusyKey('send');
    setError('');
    try {
      const result = await fetchJson('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input.trim(), thread_id: selectedThreadId }),
      });
      setInput('');
      await refreshDashboard({
        preferredThreadId: result.thread_id || selectedThreadId,
        preferredWorkItemId: result.pending_work_item ? result.work_item_id : null,
      });
    } catch (err) {
      setError(err.message || 'Failed to send the message.');
    } finally {
      setBusyKey('');
    }
  };

  const handleContinueFromHere = async () => {
    if (!selectedThreadId) return;
    setBusyKey('continue');
    setError('');
    try {
      const result = await fetchJson(`/agent/threads/${encodeURIComponent(selectedThreadId)}/continue`, {
        method: 'POST',
      });
      await refreshDashboard({
        preferredThreadId: result.thread?.thread_id,
        preferredWorkItemId: null,
      });
    } catch (err) {
      setError(err.message || 'Failed to create a branched thread.');
    } finally {
      setBusyKey('');
    }
  };

  const respondToWorkItem = async (action, payload = {}) => {
    if (!selectedWorkItem) return;
    setBusyKey(`work-item:${selectedWorkItem.id}:${action}`);
    setError('');
    try {
      const result = await fetchJson(`/agent/work-items/${encodeURIComponent(selectedWorkItem.id)}/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, payload }),
      });
      await refreshDashboard({
        preferredThreadId: result.thread?.thread_id || selectedWorkItem.thread_id,
        preferredWorkItemId: result.pending_work_item ? result.work_item_id : null,
      });
    } catch (err) {
      setError(err.message || 'Failed to respond to the work item.');
    } finally {
      setBusyKey('');
    }
  };

  const composerDisabled = !selectedThread || selectedThread.thread_kind !== 'free' || Boolean(selectedWorkItem) || Boolean(busyKey);
  const composerPlaceholder = !selectedThread
    ? t('chat.emptyState')
    : selectedWorkItem
      ? t('chat.inputLocked.needsInput')
      : selectedThread.thread_kind !== 'free'
        ? t('chat.inputLocked.official')
        : t('chat.inputPlaceholderFree');

  const renderThreadBadges = (thread) => (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <span style={toneStyle(THREAD_KIND_TONES[thread.thread_kind] || THREAD_KIND_TONES.free)}>
        {threadKindLabel(thread.thread_kind, t)}
      </span>
      <span style={toneStyle(THREAD_STATUS_TONES[thread.status] || THREAD_STATUS_TONES.ready)}>
        {threadStatusLabel(thread.status, t)}
      </span>
    </div>
  );

  const renderConflictDecision = () => {
    const context = selectedWorkItem?.context || {};
    return (
      <div style={{ display: 'grid', gap: 12 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
            {t('chat.newMeeting')}
          </div>
          <div style={{ marginTop: 6, ...panelStyle, padding: 12 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>{context.new_request?.title || t('chat.notAvailable')}</div>
            <div style={{ marginTop: 6, color: '#475569', fontSize: 13 }}>{formatEventRange(context.new_request)}</div>
            {context.new_request?.location && (
              <div style={{ marginTop: 6, color: '#475569', fontSize: 13 }}>{context.new_request.location}</div>
            )}
            {context.new_request?.notes && (
              <div style={{ marginTop: 8, color: '#334155', fontSize: 13, whiteSpace: 'pre-wrap' }}>{context.new_request.notes}</div>
            )}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
            {t('chat.currentConflict')}
          </div>
          <div style={{ marginTop: 6, ...panelStyle, padding: 12 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>
              {context.current_event?.summary || context.current_event?.title || t('chat.notAvailable')}
            </div>
            <div style={{ marginTop: 6, color: '#475569', fontSize: 13 }}>{formatEventRange(context.current_event)}</div>
            {context.current_event?.location && (
              <div style={{ marginTop: 6, color: '#475569', fontSize: 13 }}>{context.current_event.location}</div>
            )}
          </div>
        </div>

        {context.agent_recommendation?.reason && (
          <div style={{ ...panelStyle, padding: 12, background: '#f8fafc' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
              {t('chat.recommendation')}
            </div>
            <div style={{ marginTop: 6, color: '#0f172a', fontWeight: 600 }}>
              {t(`chat.choice.${context.agent_recommendation.choice}`)}
            </div>
            <div style={{ marginTop: 6, color: '#475569', fontSize: 13 }}>{context.agent_recommendation.reason}</div>
          </div>
        )}

        {context.why_input_is_needed && (
          <div style={{ color: '#475569', fontSize: 13, lineHeight: 1.5 }}>{context.why_input_is_needed}</div>
        )}

        <div style={{ display: 'grid', gap: 8 }}>
          {selectedWorkItem.allowed_responses.map((choice) => (
            <button
              key={choice}
              onClick={() => respondToWorkItem('choose', { choice })}
              disabled={Boolean(busyKey)}
              style={{
                textAlign: 'left',
                padding: '12px 14px',
                borderRadius: 8,
                border: '1px solid #cbd5e1',
                background: '#fff',
                color: '#0f172a',
                cursor: busyKey ? 'not-allowed' : 'pointer',
              }}
            >
              {t(`chat.choice.${choice}`)}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderDraftReview = () => (
    <div style={{ display: 'grid', gap: 12 }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
          {t('email.to')}
        </div>
        <div style={{ marginTop: 6, color: '#0f172a' }}>{selectedWorkItem?.context?.to || t('chat.notAvailable')}</div>
      </div>

      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
          {t('email.subject')}
        </span>
        <input
          value={draftReview.subject}
          onChange={(event) => setDraftReview((prev) => ({ ...prev, subject: event.target.value }))}
          style={{
            border: '1px solid #cbd5e1',
            borderRadius: 8,
            padding: '10px 12px',
            fontSize: 14,
          }}
        />
      </label>

      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
          {t('email.body')}
        </span>
        <textarea
          value={draftReview.body}
          onChange={(event) => setDraftReview((prev) => ({ ...prev, body: event.target.value }))}
          rows={12}
          style={{
            border: '1px solid #cbd5e1',
            borderRadius: 8,
            padding: '10px 12px',
            fontSize: 14,
            resize: 'vertical',
            fontFamily: 'inherit',
            lineHeight: 1.5,
          }}
        />
      </label>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          onClick={() => respondToWorkItem('approve', {})}
          disabled={Boolean(busyKey)}
          style={{
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid #16a34a',
            background: '#16a34a',
            color: '#fff',
            cursor: busyKey ? 'not-allowed' : 'pointer',
          }}
        >
          {t('chat.approveDraft')}
        </button>
        <button
          onClick={() => respondToWorkItem('edit', { subject: draftReview.subject, body: draftReview.body })}
          disabled={Boolean(busyKey)}
          style={{
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid #2563eb',
            background: '#2563eb',
            color: '#fff',
            cursor: busyKey ? 'not-allowed' : 'pointer',
          }}
        >
          {t('chat.saveEdits')}
        </button>
        <button
          onClick={() => respondToWorkItem('reject', {})}
          disabled={Boolean(busyKey)}
          style={{
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid #cbd5e1',
            background: '#fff',
            color: '#0f172a',
            cursor: busyKey ? 'not-allowed' : 'pointer',
          }}
        >
          {t('chat.rejectDraft')}
        </button>
      </div>
    </div>
  );

  const renderGenericWorkItem = () => (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ color: '#475569', fontSize: 13, lineHeight: 1.5 }}>{selectedWorkItem?.question}</div>
      <pre
        style={{
          margin: 0,
          padding: 12,
          background: '#f8fafc',
          borderRadius: 8,
          border: '1px solid #e2e8f0',
          overflowX: 'auto',
          fontSize: 12,
        }}
      >
        {JSON.stringify(selectedWorkItem?.context || {}, null, 2)}
      </pre>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {asArray(selectedWorkItem?.allowed_actions).map((action) => (
          <button
            key={action}
            onClick={() => respondToWorkItem(action, {})}
            disabled={Boolean(busyKey)}
            style={{
              padding: '10px 14px',
              borderRadius: 8,
              border: '1px solid #cbd5e1',
              background: '#fff',
              color: '#0f172a',
              cursor: busyKey ? 'not-allowed' : 'pointer',
            }}
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  );

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '48px 0', color: '#475569' }}>{t('common.loading')}</div>;
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0, color: '#0f172a' }}>{t('chat.workspaceTitle')}</h2>
          <div style={{ marginTop: 6, color: '#475569', maxWidth: 760 }}>{t('chat.workspaceSubtitle')}</div>
        </div>
        <button
          onClick={() => refreshDashboard({ preferredThreadId: selectedThreadId, preferredWorkItemId: openWorkItemId })}
          disabled={Boolean(busyKey)}
          style={{
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid #cbd5e1',
            background: '#fff',
            color: '#0f172a',
            cursor: busyKey ? 'not-allowed' : 'pointer',
          }}
        >
          {t('chat.refresh')}
        </button>
      </div>

      {error && (
        <div style={{ ...panelStyle, borderColor: '#fecaca', background: '#fef2f2', color: '#991b1b' }}>{error}</div>
      )}

      <div
        style={{
          display: 'grid',
          gap: 16,
          alignItems: 'start',
          gridTemplateColumns: isNarrow ? '1fr' : '280px minmax(0, 1fr) 320px',
        }}
      >
        <aside style={{ display: 'grid', gap: 16 }}>
          <section style={panelStyle}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>{t('chat.demoPanelTitle')}</div>
            <div style={{ marginTop: 6, color: '#475569', fontSize: 13, lineHeight: 1.5 }}>
              {t('chat.demoPanelDesc')}
            </div>

            <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
              {officialThreads.map((thread) => (
                <button
                  key={thread.thread_id}
                  onClick={() => handleStartDemo(thread.script_id)}
                  disabled={Boolean(busyKey)}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    borderRadius: 8,
                    border: '1px solid #cbd5e1',
                    background: '#fff',
                    cursor: busyKey ? 'not-allowed' : 'pointer',
                  }}
                >
                  <div style={{ fontWeight: 700, color: '#0f172a' }}>{threadTitle(thread)}</div>
                  <div style={{ marginTop: 4, color: '#475569', fontSize: 13 }}>{thread.title}</div>
                </button>
              ))}
            </div>

            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase' }}>
                {t('chat.modeLabel')}
              </div>
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {['semi_auto', 'auto'].map((mode) => {
                  const active = settings.agent_mode === mode;
                  return (
                    <button
                      key={mode}
                      onClick={() => handleModeChange(mode)}
                      disabled={Boolean(busyKey)}
                      style={{
                        padding: '10px 12px',
                        borderRadius: 8,
                        border: active ? '1px solid #2563eb' : '1px solid #cbd5e1',
                        background: active ? '#eff6ff' : '#fff',
                        color: active ? '#1d4ed8' : '#0f172a',
                        fontWeight: 600,
                        cursor: busyKey ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {mode === 'auto' ? t('settings.modeAuto') : t('settings.modeSemiAuto')}
                    </button>
                  );
                })}
              </div>
              <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>{t('chat.modeNote')}</div>
            </div>

            <button
              onClick={handleResetDemo}
              disabled={Boolean(busyKey)}
              style={{
                marginTop: 14,
                width: '100%',
                padding: '10px 14px',
                borderRadius: 8,
                border: '1px solid #cbd5e1',
                background: '#fff',
                color: '#0f172a',
                cursor: busyKey ? 'not-allowed' : 'pointer',
              }}
            >
              {t('chat.resetDemo')}
            </button>
          </section>

          <section style={panelStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ fontWeight: 700, color: '#0f172a' }}>{t('chat.threadListTitle')}</div>
              <span style={{ color: '#64748b', fontSize: 12 }}>{threads.length}</span>
            </div>
            <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
              {threads.map((thread) => {
                const active = thread.thread_id === selectedThreadId;
                return (
                  <button
                    key={thread.thread_id}
                    onClick={() => selectThread(thread.thread_id, thread.active_work_item_id || null)}
                    style={{
                      textAlign: 'left',
                      padding: '12px 14px',
                      borderRadius: 8,
                      border: active ? '1px solid #2563eb' : '1px solid #e2e8f0',
                      background: active ? '#eff6ff' : '#fff',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div style={{ fontWeight: 700, color: '#0f172a' }}>{threadTitle(thread)}</div>
                      {thread.active_work_item_id && (
                        <span style={{ ...toneStyle(THREAD_STATUS_TONES.needs_input), padding: '2px 6px' }}>!</span>
                      )}
                    </div>
                    <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {renderThreadBadges(thread)}
                    </div>
                    <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>
                      {formatDateTime(thread.updated_at)}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section style={panelStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ fontWeight: 700, color: '#0f172a' }}>{t('chat.agentInboxTitle')}</div>
              <span style={toneStyle(inboxCount ? THREAD_STATUS_TONES.needs_input : THREAD_STATUS_TONES.ready)}>{inboxCount}</span>
            </div>
            <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
              {inboxCount === 0 && <div style={{ color: '#64748b', fontSize: 13 }}>{t('chat.emptyInbox')}</div>}
              {workItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    setOpenWorkItemId(item.id);
                    selectThread(item.thread_id, item.id);
                  }}
                  style={{
                    textAlign: 'left',
                    padding: '12px 14px',
                    borderRadius: 8,
                    border: item.id === selectedWorkItem?.id ? '1px solid #2563eb' : '1px solid #e2e8f0',
                    background: item.id === selectedWorkItem?.id ? '#eff6ff' : '#fff',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontWeight: 700, color: '#0f172a' }}>{item.title}</div>
                  <div style={{ marginTop: 4, color: '#475569', fontSize: 13 }}>{threadTitle(threads.find((thread) => thread.thread_id === item.thread_id) || {})}</div>
                  <div style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>{formatDateTime(item.updated_at)}</div>
                </button>
              ))}
            </div>
          </section>
        </aside>

        <section style={{ ...panelStyle, display: 'grid', minHeight: 680, gridTemplateRows: 'auto 1fr auto', gap: 16 }}>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#0f172a' }}>
                  {selectedThread ? threadTitle(selectedThread) : t('chat.emptyState')}
                </div>
                {selectedThread && renderThreadBadges(selectedThread)}
                {selectedThread?.summary && (
                  <div style={{ color: '#475569', fontSize: 13, lineHeight: 1.5 }}>{selectedThread.summary}</div>
                )}
              </div>

              {selectedThread?.thread_kind === 'official' && selectedThread?.status === 'completed' && (
                <button
                  onClick={handleContinueFromHere}
                  disabled={Boolean(busyKey)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: '1px solid #2563eb',
                    background: '#2563eb',
                    color: '#fff',
                    cursor: busyKey ? 'not-allowed' : 'pointer',
                  }}
                >
                  {t('chat.continueFromHere')}
                </button>
              )}
            </div>

            {selectedThread?.thread_kind === 'official' && selectedThread?.status === 'ready' && (
              <div style={{ ...panelStyle, padding: 12, background: '#f8fafc' }}>
                <div style={{ color: '#475569', fontSize: 13, lineHeight: 1.5 }}>{selectedThread.starter_message}</div>
                <button
                  onClick={() => handleStartDemo(selectedThread.script_id)}
                  disabled={Boolean(busyKey)}
                  style={{
                    marginTop: 12,
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: '1px solid #2563eb',
                    background: '#2563eb',
                    color: '#fff',
                    cursor: busyKey ? 'not-allowed' : 'pointer',
                  }}
                >
                  {t('chat.startSelectedDemo')}
                </button>
              </div>
            )}
          </div>

          <div
            style={{
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 12,
              overflowY: 'auto',
              background: '#f8fafc',
              display: 'grid',
              alignContent: 'start',
              gap: 12,
            }}
          >
            {!selectedThread?.messages?.length && (
              <div style={{ color: '#64748b', fontSize: 14 }}>{t('chat.noMessages')}</div>
            )}

            {asArray(selectedThread?.messages).map((message, index) => {
              const isUser = message.role === 'user';
              return (
                <div
                  key={`${message.timestamp || 'message'}-${index}`}
                  style={{
                    justifySelf: isUser ? 'end' : 'start',
                    maxWidth: '90%',
                    padding: '12px 14px',
                    borderRadius: 8,
                    border: `1px solid ${isUser ? '#bfdbfe' : '#e2e8f0'}`,
                    background: isUser ? '#eff6ff' : '#fff',
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                    {roleLabel(message.role, t)}
                  </div>
                  <div style={{ marginTop: 6, color: '#0f172a', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                    {message.content}
                  </div>
                  {message.timestamp && (
                    <div style={{ marginTop: 8, color: '#94a3b8', fontSize: 12 }}>{formatDateTime(message.timestamp)}</div>
                  )}
                </div>
              );
            })}

            {selectedThread?.thread_kind === 'free' && !selectedThread?.messages?.length && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt.labelKey}
                    onClick={() => setInput(t(prompt.valueKey))}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 8,
                      border: '1px solid #cbd5e1',
                      background: '#fff',
                      color: '#0f172a',
                      cursor: 'pointer',
                    }}
                  >
                    {t(prompt.labelKey)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <form onSubmit={handleSend} style={{ display: 'grid', gap: 10 }}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={4}
              disabled={composerDisabled}
              placeholder={composerPlaceholder}
              style={{
                border: '1px solid #cbd5e1',
                borderRadius: 8,
                padding: '12px 14px',
                resize: 'vertical',
                fontFamily: 'inherit',
                fontSize: 14,
                lineHeight: 1.5,
                background: composerDisabled ? '#f8fafc' : '#fff',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ color: '#64748b', fontSize: 12 }}>
                {selectedWorkItem
                  ? t('chat.inputLocked.needsInput')
                  : selectedThread?.thread_kind !== 'free'
                    ? t('chat.inputLocked.official')
                    : t('chat.freeThreadHint')}
              </div>
              <button
                type="submit"
                disabled={composerDisabled || !input.trim()}
                style={{
                  padding: '10px 14px',
                  borderRadius: 8,
                  border: '1px solid #2563eb',
                  background: composerDisabled || !input.trim() ? '#bfdbfe' : '#2563eb',
                  color: '#fff',
                  cursor: composerDisabled || !input.trim() ? 'not-allowed' : 'pointer',
                }}
              >
                {busyKey === 'send' ? t('chat.sending') : t('chat.send')}
              </button>
            </div>
          </form>
        </section>

        <aside style={{ display: 'grid', gap: 16 }}>
          <section style={panelStyle}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>{t('chat.workItemTitle')}</div>
            {!selectedWorkItem && (
              <div style={{ marginTop: 10, color: '#64748b', fontSize: 13 }}>{t('chat.noOpenWorkItem')}</div>
            )}
            {selectedWorkItem && (
              <div style={{ marginTop: 12, display: 'grid', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>{selectedWorkItem.title}</div>
                  <div style={{ marginTop: 6, color: '#475569', fontSize: 13, lineHeight: 1.5 }}>{selectedWorkItem.question}</div>
                </div>
                {selectedWorkItem.type === 'conflict_decision' && renderConflictDecision()}
                {selectedWorkItem.type === 'draft_review' && renderDraftReview()}
                {selectedWorkItem.type !== 'conflict_decision' && selectedWorkItem.type !== 'draft_review' && renderGenericWorkItem()}
              </div>
            )}
          </section>

          <section style={panelStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ fontWeight: 700, color: '#0f172a' }}>{t('chat.timelineTitle')}</div>
              {threadLoading && <span style={{ color: '#64748b', fontSize: 12 }}>{t('chat.loadingTimeline')}</span>}
            </div>
            <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
              {timeline.length === 0 && <div style={{ color: '#64748b', fontSize: 13 }}>{t('chat.noTimeline')}</div>}
              {timeline.map((item, index) => (
                <div
                  key={item.id || `${item.type}-${index}`}
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    border: '1px solid #e2e8f0',
                    background: '#fff',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#2563eb', textTransform: 'uppercase' }}>
                      {item.type?.replace(/_/g, ' ')}
                    </div>
                    <div style={{ color: '#94a3b8', fontSize: 12 }}>{formatDateTime(item.timestamp)}</div>
                  </div>
                  <div style={{ marginTop: 6, color: '#0f172a', fontSize: 13, lineHeight: 1.5 }}>{item.message || excerpt(JSON.stringify(item.payload || {}), 180)}</div>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
};
