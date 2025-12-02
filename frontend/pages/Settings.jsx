const { useState, useEffect } = React;

const SettingsView = ({ user, onAutomationActivity }) => {
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
        throw new Error('无法获取规则');
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
      setError(err.message || '加载自动化配置失败');
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
        throw new Error('服务端更新失败');
      }
      await loadAutomationState();
      await notifyAutomationActivity();
    } catch (err) {
      setAutomationEnabled(!nextValue);
      setError(err.message || '更新自动化开关失败');
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
        throw new Error('服务端更新失败');
      }
      setError(null);
    } catch (err) {
      setAutoAddEvents(!nextValue);
      setError(err.message || '更新自动添加日程设置失败');
    }
  };

  const handleAddRule = async (event) => {
    event.preventDefault();
    if (!form.label.trim() || !form.reason.trim()) {
      setError('请输入标签名称和匹配理由');
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
        const detail = await resp.json().catch(() => ({ detail: '创建规则失败' }));
        throw new Error(detail.detail || '创建规则失败');
      }
      await resp.json();
      setForm({ label: '', reason: '' });
      setError(null);
      await loadAutomationState();
      await notifyAutomationActivity();
    } catch (err) {
      setError(err.message || '创建规则失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRule = async (ruleId) => {
    if (!ruleId) return;
    try {
      const resp = await fetch(`/automation/rules/${ruleId}`, { method: 'DELETE' });
      if (!resp.ok) {
        throw new Error('删除失败');
      }
      await loadAutomationState();
      await notifyAutomationActivity();
    } catch (err) {
      setError(err.message || '删除规则失败');
    }
  };

  const formatTimestamp = (value) => {
    if (!value) {
      return '尚未执行';
    }
    try {
      return new Date(value).toLocaleString();
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
        throw new Error('手动运行失败');
      }
      await resp.json();
      await loadAutomationState();
      setError(null);
      await notifyAutomationActivity();
    } catch (err) {
      setError(err.message || '手动运行失败');
    } finally {
      setRunningNow(false);
    }
  };

  return (
    <div style={{ background: '#fff', borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ padding: 16, borderBottom: '1px solid #f1f5f9' }}>
        <h2 style={{ margin: 0 }}>系统设置</h2>
        <p style={{ color: '#6b7280' }}>管理您的账户信息与自动化标签</p>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <section>
          <h3 style={{ fontSize: 12, letterSpacing: 1 }}>账户</h3>
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
              <h3 style={{ margin: '0 0 4px 0' }}>自动标签</h3>
              <p style={{ color: '#6b7280', margin: 0 }}>根据自定义规则定期为邮件添加标签</p>
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
                {automationEnabled ? '已开启' : '已关闭'}
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
                {runningNow ? '运行中…' : '立即运行'}
              </button>
            </div>
          </div>
          <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <StatusCard label="最近运行" value={formatTimestamp(status?.last_run_at)} />
            <StatusCard label="最近处理" value={`${status?.last_labeled || 0} 封`} />
            <StatusCard label="缓存同步" value={formatTimestamp(status?.last_refresh_at)} />
            <StatusCard label="错误" value={status?.last_error || '暂无'} highlight={!!status?.last_error} />
          </div>

          <div style={{ marginTop: 16, background: '#f8fafc', borderRadius: 10, padding: 12 }}>
            <h4 style={{ margin: '0 0 8px 0' }}>操作日志</h4>
            {logs.length === 0 ? (
              <p style={{ color: '#94a3b8', margin: 0 }}>暂无日志</p>
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
                placeholder="标签名称"
                value={form.label}
                onChange={(e) => setForm((prev) => ({ ...prev, label: e.target.value }))}
                style={{ flex: 1, minWidth: 200, padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
              <input
                type="text"
                placeholder="匹配理由，如“来自财务部的对账邮件”"
                value={form.reason}
                onChange={(e) => setForm((prev) => ({ ...prev, reason: e.target.value }))}
                style={{ flex: 2, minWidth: 260, padding: 10, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
              <button
                type="submit"
                disabled={saving}
                style={{ padding: '10px 18px', borderRadius: 8, border: 'none', background: '#2563eb', color: '#fff', cursor: saving ? 'not-allowed' : 'pointer' }}
              >
                {saving ? '保存中...' : '添加规则'}
              </button>
            </div>
          </form>

          <div style={{ marginTop: 16 }}>
            <h4 style={{ marginBottom: 8 }}>规则列表</h4>
            {loading ? (
              <p>加载中...</p>
            ) : rules.length === 0 ? (
              <p style={{ color: '#6b7280' }}>暂无规则，添加第一个规则以启用自动标签。</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ textAlign: 'left', borderBottom: '1px solid #f1f5f9' }}>
                    <th style={{ padding: '8px 4px' }}>标签</th>
                    <th style={{ padding: '8px 4px' }}>理由</th>
                    <th style={{ padding: '8px 4px', width: 80 }}>操作</th>
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
                          删除
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
              <h3 style={{ margin: '0 0 4px 0' }}>📅 自动添加日程</h3>
              <p style={{ color: '#6b7280', margin: 0 }}>
                自动从邮件中提取日程并添加到日历。关闭时，提取的日程会显示在日历页面等待您确认。
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
              {autoAddEvents ? '已开启' : '已关闭'}
            </button>
          </div>
          <div style={{ marginTop: 12, padding: 12, background: autoAddEvents ? '#dcfce7' : '#fef3c7', borderRadius: 8, border: autoAddEvents ? '1px solid #86efac' : '1px solid #fde68a' }}>
            <div style={{ fontSize: 13, color: autoAddEvents ? '#166534' : '#92400e' }}>
              {autoAddEvents 
                ? '✅ 系统会自动将邮件中识别出的日程事件添加到您的日历中。'
                : '⏸️ 系统会将邮件中识别出的日程事件保存为提案，您可以在日历页面手动确认添加。'
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
