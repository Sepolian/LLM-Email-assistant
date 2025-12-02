const { useState, useEffect } = React;

const SettingsView = ({ user, onAutomationActivity }) => {
  const { t } = useTranslation();
  const [automationEnabled, setAutomationEnabled] = useState(false);
  const [autoAddEvents, setAutoAddEvents] = useState(false);
  const [rules, setRules] = useState([]);
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ label: '', reason: '' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [runningNow, setRunningNow] = useState(false);

  const loadAutomationState = async () => {
    try {
      setLoading(true);
      const [rulesResp, statusResp, extraSettingsResp] = await Promise.all([
        fetch('/automation/rules'),
        fetch('/automation/status'),
        fetch('/automation/extra-settings'),
      ]);

      if (!rulesResp.ok) {
        throw new Error(t('settings.loadingRules'));
      }
      const rulesData = await rulesResp.json();
      setRules(rulesData.rules || []);
      setAutomationEnabled(!!rulesData.automation_enabled);

      if (statusResp.ok) {
        const statusData = await statusResp.json();
        setStatus(statusData);
      } else {
        setStatus(null);
      }

      if (extraSettingsResp.ok) {
        const extraData = await extraSettingsResp.json();
        setAutoAddEvents(!!extraData.auto_add_events);
      }

      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAutomationState();
  }, []);

  const notifyAutomationActivity = async () => {
    if (typeof onAutomationActivity !== 'function') {
      return;
    }
    try {
      await onAutomationActivity({ resetPage: true });
    } catch (err) {
      console.warn('Automation refresh failed', err);
    }
  };

  const toggleAutomation = async () => {
    const nextValue = !automationEnabled;
    setAutomationEnabled(nextValue);
    try {
      const resp = await fetch('/automation/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ automation_enabled: nextValue }),
      });
      if (!resp.ok) {
        throw new Error('Server update failed');
      }
      await loadAutomationState();
      await notifyAutomationActivity();
    } catch (err) {
      setAutomationEnabled(!nextValue);
      setError(err.message);
    }
  };

  const toggleAutoAddEvents = async () => {
    const nextValue = !autoAddEvents;
    setAutoAddEvents(nextValue);
    try {
      const resp = await fetch('/automation/extra-settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_add_events: nextValue }),
      });
      if (!resp.ok) {
        throw new Error('Server update failed');
      }
      setError(null);
    } catch (err) {
      setAutoAddEvents(!nextValue);
      setError(err.message);
    }
  };

  const handleAddRule = async (event) => {
    event.preventDefault();
    if (!form.label.trim() || !form.reason.trim()) {
      setError(t('settings.enterLabelAndReason'));
      return;
    }
    setSaving(true);
    try {
      const resp = await fetch('/automation/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: form.label.trim(), reason: form.reason.trim() }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: 'Failed to create rule' }));
        throw new Error(detail.detail || 'Failed to create rule');
      }
      await resp.json();
      setForm({ label: '', reason: '' });
      setError(null);
      await loadAutomationState();
      await notifyAutomationActivity();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRule = async (ruleId) => {
    if (!ruleId) return;
    try {
      const resp = await fetch(`/automation/rules/${ruleId}`, { method: 'DELETE' });
      if (!resp.ok) {
        throw new Error('Failed to delete rule');
      }
      await loadAutomationState();
      await notifyAutomationActivity();
    } catch (err) {
      setError(err.message);
    }
  };

  const formatTimestamp = (value) => {
    if (!value) {
      return t('settings.notExecuted');
    }
    try {
      return new Date(value).toLocaleString(i18n.currentLang === 'zh' ? 'zh-CN' : 'en-US');
    } catch (err) {
      return value;
    }
  };

  const logs = status?.logs || [];

  const handleRunAutomation = async () => {
    setRunningNow(true);
    try {
      const resp = await fetch('/automation/run', { method: 'POST' });
      if (!resp.ok) {
        throw new Error('Failed to run automation');
      }
      await resp.json();
      await loadAutomationState();
      setError(null);
      await notifyAutomationActivity();
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningNow(false);
    }
  };

  return (
    <div style={{ background: '#fff', borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #f1f5f9' }}>
        <h2 style={{ margin: 0 }}>{t('settings.title')}</h2>
        <p style={{ color: '#6b7280' }}>{t('settings.subtitle')}</p>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <section>
          <h3 style={{ fontSize: 12, letterSpacing: 1 }}>{t('settings.account')}</h3>
          {user && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 8 }}>
              {user.picture && <img src={user.picture} alt={user.name} style={{ width: 64, height: 64, borderRadius: 64 }} />}
              {!user.picture && <div style={{ width: 64, height: 64, borderRadius: 64, background: '#e2e8f0' }}></div>}
              <div>
                <div style={{ fontWeight: 600 }}>{user.name}</div>
                <div style={{ color: '#6b7280' }}>{user.email}</div>
              </div>
            </div>
          )}
        </section>

        <section style={{ borderTop: '1px solid #f1f5f9', paddingTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <h3 style={{ margin: '0 0 4px 0' }}>{t('settings.autoLabel')}</h3>
              <p style={{ color: '#6b7280', margin: 0 }}>{t('settings.autoLabelDesc')}</p>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                onClick={toggleAutomation}
                disabled={loading}
                style={{
                  padding: '8px 16px',
                  borderRadius: 999,
                  border: 'none',
                  background: automationEnabled ? '#22c55e' : '#cbd5f5',
                  color: automationEnabled ? '#fff' : '#0f172a',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  minWidth: 120,
                }}
              >
                {automationEnabled ? t('settings.on') : t('settings.off')}
              </button>
              <button
                onClick={handleRunAutomation}
                disabled={loading || runningNow}
                style={{
                  padding: '8px 16px',
                  borderRadius: 999,
                  border: '1px solid #cbd5f5',
                  background: runningNow ? '#e0e7ff' : '#fff',
                  color: '#0f172a',
                  cursor: loading || runningNow ? 'not-allowed' : 'pointer',
                  minWidth: 120,
                }}
              >
                {runningNow ? t('settings.running') : t('settings.runNow')}
              </button>
            </div>
          </div>
          <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <StatusCard label={t('settings.lastRun')} value={formatTimestamp(status?.last_run_at)} />
            <StatusCard label={t('settings.lastProcessed')} value={`${status?.last_labeled || 0}`} />
            <StatusCard label={t('settings.cacheSync')} value={formatTimestamp(status?.last_refresh_at)} />
            <StatusCard label={t('settings.errors')} value={status?.last_error || t('settings.noErrors')} highlight={!!status?.last_error} />
          </div>

          <div style={{ marginTop: 16, background: '#f8fafc', borderRadius: 10, padding: 12 }}>
            <h4 style={{ margin: '0 0 8px 0' }}>{t('settings.activityLogs')}</h4>
            {logs.length === 0 ? (
              <p style={{ color: '#94a3b8', margin: 0 }}>{t('settings.noLogs')}</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {logs.map((log) => (
                  <div
                    key={log.id}
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 8,
                      alignItems: 'center',
                      padding: '6px 10px',
                      borderRadius: 8,
                      background: '#fff',
                      border: '1px solid #e2e8f0',
                      fontSize: 13,
                    }}
                  >
                    <span style={{ color: '#0f172a', flex: '1 1 200px' }}>{log.message}</span>
                    <span style={{ color: '#94a3b8', fontSize: 12 }}>{formatTimestamp(log.timestamp)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <form onSubmit={handleAddRule} style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <input
                type="text"
                placeholder={t('settings.labelName')}
                value={form.label}
                onChange={(e) => setForm((prev) => ({ ...prev, label: e.target.value }))}
                style={{ flex: 1, minWidth: 200, padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
              <input
                type="text"
                placeholder={t('settings.matchReason')}
                value={form.reason}
                onChange={(e) => setForm((prev) => ({ ...prev, reason: e.target.value }))}
                style={{ flex: 2, minWidth: 260, padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
              <button
                type="submit"
                disabled={saving}
                style={{ padding: '10px 18px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', cursor: saving ? 'not-allowed' : 'pointer' }}
              >
                {saving ? t('settings.saving') : t('settings.addRule')}
              </button>
            </div>
          </form>

          <div style={{ marginTop: 16 }}>
            <h4 style={{ marginBottom: 8 }}>{t('settings.rulesList')}</h4>
            {loading ? (
              <p>{t('settings.loadingRules')}</p>
            ) : rules.length === 0 ? (
              <p style={{ color: '#6b7280' }}>{t('settings.noRules')}</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ textAlign: 'left', borderBottom: '1px solid #f1f5f9' }}>
                    <th style={{ padding: '8px 4px' }}>{t('settings.label')}</th>
                    <th style={{ padding: '8px 4px' }}>{t('settings.reason')}</th>
                    <th style={{ padding: '8px 4px', width: 80 }}>{t('settings.action')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr key={rule.id} style={{ borderBottom: '1px solid #f8fafc' }}>
                      <td style={{ padding: '8px 4px', fontWeight: 600 }}>{rule.label}</td>
                      <td style={{ padding: '8px 4px', color: '#475569' }}>{rule.reason}</td>
                      <td style={{ padding: '8px 4px' }}>
                        <button
                          type="button"
                          onClick={() => handleDeleteRule(rule.id)}
                          style={{ border: 'none', background: 'transparent', color: '#ef4444', cursor: 'pointer' }}
                        >
                          {t('settings.deleteRule')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        {/* Auto Add Events Section */}
        <section style={{ borderTop: '1px solid #f1f5f9', paddingTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <h3 style={{ margin: '0 0 4px 0' }}>{t('settings.autoAddEvents')}</h3>
              <p style={{ color: '#6b7280', margin: 0 }}>
                {t('settings.autoAddEventsDesc')}
              </p>
            </div>
            <button
              onClick={toggleAutoAddEvents}
              disabled={loading}
              style={{
                padding: '8px 16px',
                borderRadius: 999,
                border: 'none',
                background: autoAddEvents ? '#22c55e' : '#cbd5f5',
                color: autoAddEvents ? '#fff' : '#0f172a',
                cursor: loading ? 'not-allowed' : 'pointer',
                minWidth: 120,
              }}
            >
              {autoAddEvents ? t('settings.on') : t('settings.off')}
            </button>
          </div>
          <div style={{ marginTop: 12, padding: 12, background: autoAddEvents ? '#dcfce7' : '#fef3c7', borderRadius: 8, border: autoAddEvents ? '1px solid #86efac' : '1px solid #fde68a' }}>
            <div style={{ fontSize: 13, color: autoAddEvents ? '#166534' : '#92400e' }}>
              {autoAddEvents 
                ? t('settings.autoAddOn')
                : t('settings.autoAddOff')
              }
            </div>
          </div>
        </section>

        {error && (
          <div style={{ background: '#fee2e2', color: '#b91c1c', padding: 12, borderRadius: 8 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
};

const StatusCard = ({ label, value, highlight }) => (
  <div style={{ padding: 12, borderRadius: 10, background: highlight ? '#fee2e2' : '#f8fafc', border: highlight ? '1px solid #fecaca' : '1px solid #e2e8f0' }}>
    <div style={{ fontSize: 12, color: '#94a3b8', textTransform: 'uppercase' }}>{label}</div>
    <div style={{ fontWeight: 600, marginTop: 4 }}>{value}</div>
  </div>
);
