const { useState, useEffect } = React;

const HomeView = () => {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [logsInfo, setLogsInfo] = useState({ total: 0, retention_days: 7 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const [statusResp, logsResp] = await Promise.all([
          fetch('/automation/status'),
          fetch('/automation/logs?days=7&limit=50'),
        ]);

        if (statusResp.ok) {
          const statusData = await statusResp.json();
          setStatus(statusData);
        }

        if (logsResp.ok) {
          const logsData = await logsResp.json();
          setLogs(logsData.logs || []);
          setLogsInfo({
            total: logsData.total || 0,
            retention_days: logsData.retention_days || 7,
          });
        }
      } catch (err) {
        console.error('Failed to fetch status:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    // Refresh every 30 seconds
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const formatTimestamp = (ts) => {
    if (!ts) return t('home.noData');
    const date = new Date(ts);
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    
    if (diffMin < 1) return t('home.justNow');
    if (diffMin < 60) return `${diffMin} ${t('home.minutesAgo')}`;
    if (diffMin < 1440) return `${Math.floor(diffMin / 60)} ${t('home.hoursAgo')}`;
    return date.toLocaleDateString(i18n.currentLang === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const getLogStatus = (level) => {
    switch (level) {
      case 'error': return 'error';
      case 'warning': return 'warning';
      default: return 'success';
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'success': return '#10b981';
      case 'warning': return '#f59e0b';
      case 'error': return '#ef4444';
      default: return '#94a3b8';
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <p>{t('home.loading')}</p>
      </div>
    );
  }

  return (
    <div>
      <header style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 22 }}>{t('home.title')}</h1>
        <p style={{ color: '#6b7280' }}>{t('home.subtitle')}</p>
      </header>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
        <div style={{ background: '#fff', padding: 16, borderRadius: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{t('home.automationStatus')}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: status?.automation_enabled ? '#10b981' : '#94a3b8' }}>
            {status?.automation_enabled ? t('home.enabled') : t('home.disabled')}
          </div>
        </div>
        <div style={{ background: '#fff', padding: 16, borderRadius: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{t('home.activeRules')}</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{status?.rule_count || 0} {t('home.rulesCount')}</div>
        </div>
        <div style={{ background: '#fff', padding: 16, borderRadius: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{t('home.recentEmails')}</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{status?.last_labeled || 0} {t('home.emailsCount')}</div>
        </div>
        <div style={{ background: '#fff', padding: 16, borderRadius: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{t('home.lastRun')}</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{formatTimestamp(status?.last_run_at)}</div>
        </div>
        <div style={{ background: '#fff', padding: 16, borderRadius: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{t('home.cacheSync')}</div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{formatTimestamp(status?.last_refresh_at)}</div>
        </div>
      </div>

      {/* Running Status */}
      {status?.running_now && (
        <div style={{ background: '#dbeafe', padding: 12, borderRadius: 8, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#2563eb', animation: 'pulse 1.5s infinite' }} />
          <span style={{ color: '#1e40af', fontWeight: 500 }}>{t('home.automationRunning')}</span>
        </div>
      )}

      {/* Error Alert */}
      {status?.last_error && (
        <div style={{ background: '#fef2f2', padding: 12, borderRadius: 8, marginBottom: 16, border: '1px solid #fecaca' }}>
          <div style={{ color: '#dc2626', fontWeight: 600, marginBottom: 4 }}>{t('home.recentError')}</div>
          <div style={{ color: '#7f1d1d', fontSize: 14 }}>{status.last_error}</div>
        </div>
      )}

      {/* Activity Logs */}
      <div style={{ background: '#fff', borderRadius: 12, boxShadow: '0 1px 2px rgba(0,0,0,0.03)' }}>
        <div style={{ padding: 16, borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>{t('home.activityLogs')}</h3>
          <span style={{ fontSize: 12, color: '#94a3b8' }}>
            {t('home.logsTotal')} {logsInfo.total} · {t('home.logsRetention')} {logsInfo.retention_days} {t('home.days')}
          </span>
        </div>
        <div>
          {logs.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#94a3b8' }}>
              {t('home.noLogs')}
            </div>
          ) : (
            logs.slice(0, 20).map((log) => (
              <div key={log.id} style={{ padding: 16, borderBottom: '1px solid #f8fafc', display: 'flex', gap: 12 }}>
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 8,
                    marginTop: 6,
                    background: getStatusColor(getLogStatus(log.level)),
                  }}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <h4 style={{ margin: 0 }}>{log.message}</h4>
                    <span style={{ fontSize: 12, color: '#94a3b8' }}>{formatTimestamp(log.timestamp)}</span>
                  </div>
                  {log.level === 'error' && (
                    <p style={{ margin: '4px 0 0 0', color: '#ef4444', fontSize: 13 }}>{t('home.error')}</p>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <style>
        {`
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
          }
        `}
      </style>
    </div>
  );
};

window.HomeView = HomeView;
