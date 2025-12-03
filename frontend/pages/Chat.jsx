const { useState, useRef, useEffect } = React;

const ChatView = () => {
  const { t } = useTranslation();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // Add welcome message on mount
    setMessages([{
      role: 'assistant',
      content: t('chat.welcomeMessage'),
      timestamp: new Date().toISOString()
    }]);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setError(null);

    // Add user message to UI
    setMessages(prev => [...prev, {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString()
    }]);

    setLoading(true);

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to send message');
      }

      const data = await response.json();

      // Add assistant response
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.message,
        toolCalls: data.tool_calls || [],
        timestamp: new Date().toISOString()
      }]);

    } catch (err) {
      setError(err.message);
      setMessages(prev => [...prev, {
        role: 'error',
        content: err.message,
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleReset = async () => {
    try {
      await fetch('/chat/reset', { method: 'POST' });
      setMessages([{
        role: 'assistant',
        content: t('chat.welcomeMessage'),
        timestamp: new Date().toISOString()
      }]);
      setError(null);
    } catch (err) {
      setError('Failed to reset conversation');
    }
  };

  const handleQuickAction = (action) => {
    setInput(action);
    inputRef.current?.focus();
  };

  const formatToolResult = (toolCall) => {
    const { tool_name, result } = toolCall;
    if (!result) return null;

    if (result.success) {
      const data = result.result;
      if (tool_name === 'add_calendar_event' && data.event) {
        return (
          <div style={styles.toolResult}>
            <div style={styles.toolResultIcon}>✅</div>
            <div>
              <div style={styles.toolResultTitle}>{t('chat.eventCreated')}</div>
              <div style={styles.toolResultDetail}>
                <strong>{data.event.title}</strong>
                <br />
                📅 {data.event.date} | ⏰ {data.event.start_time} - {data.event.end_time}
                {data.event.location && <><br />📍 {data.event.location}</>}
              </div>
            </div>
          </div>
        );
      } else if (tool_name === 'list_calendar_events' && data.events) {
        return (
          <div style={styles.toolResult}>
            <div style={styles.toolResultIcon}>📅</div>
            <div>
              <div style={styles.toolResultTitle}>{data.message}</div>
              {data.events.length > 0 ? (
                <div style={styles.eventsList}>
                  {data.events.slice(0, 5).map((event, idx) => (
                    <div key={idx} style={styles.eventItem}>
                      <strong>{event.title}</strong>
                      <br />
                      <span style={styles.eventTime}>{new Date(event.start).toLocaleString()}</span>
                      {event.location && <span style={styles.eventLocation}> | 📍 {event.location}</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={styles.noEvents}>{t('chat.noUpcomingEvents')}</div>
              )}
            </div>
          </div>
        );
      } else if (tool_name === 'delete_calendar_event') {
        return (
          <div style={styles.toolResult}>
            <div style={styles.toolResultIcon}>🗑️</div>
            <div style={styles.toolResultTitle}>{data.message}</div>
          </div>
        );
      }
    } else {
      return (
        <div style={{...styles.toolResult, ...styles.toolError}}>
          <div style={styles.toolResultIcon}>❌</div>
          <div style={styles.toolResultTitle}>{result.error}</div>
        </div>
      );
    }
    return null;
  };

  const styles = {
    container: {
      display: 'flex',
      flexDirection: 'column',
      height: 'calc(100vh - 120px)',
      maxWidth: 800,
      margin: '0 auto',
      background: '#fff',
      borderRadius: 12,
      overflow: 'hidden',
      boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
    },
    header: {
      padding: '16px 20px',
      borderBottom: '1px solid #e2e8f0',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      background: '#f8fafc'
    },
    headerTitle: {
      margin: 0,
      fontSize: 18,
      fontWeight: 600,
      color: '#0f172a'
    },
    resetButton: {
      padding: '6px 12px',
      borderRadius: 6,
      border: '1px solid #e2e8f0',
      background: '#fff',
      cursor: 'pointer',
      fontSize: 13,
      color: '#64748b'
    },
    messagesContainer: {
      flex: 1,
      overflowY: 'auto',
      padding: 20,
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    },
    message: {
      maxWidth: '80%',
      padding: '12px 16px',
      borderRadius: 12,
      lineHeight: 1.5,
      whiteSpace: 'pre-wrap'
    },
    userMessage: {
      alignSelf: 'flex-end',
      background: '#2563eb',
      color: '#fff',
      borderBottomRightRadius: 4
    },
    assistantMessage: {
      alignSelf: 'flex-start',
      background: '#f1f5f9',
      color: '#0f172a',
      borderBottomLeftRadius: 4
    },
    errorMessage: {
      alignSelf: 'center',
      background: '#fef2f2',
      color: '#dc2626',
      border: '1px solid #fecaca',
      fontSize: 13
    },
    toolResult: {
      display: 'flex',
      gap: 12,
      padding: 12,
      background: '#f0fdf4',
      borderRadius: 8,
      marginTop: 8,
      border: '1px solid #86efac'
    },
    toolError: {
      background: '#fef2f2',
      border: '1px solid #fecaca'
    },
    toolResultIcon: {
      fontSize: 20
    },
    toolResultTitle: {
      fontWeight: 500,
      marginBottom: 4
    },
    toolResultDetail: {
      fontSize: 13,
      color: '#475569',
      lineHeight: 1.6
    },
    eventsList: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      marginTop: 8
    },
    eventItem: {
      padding: 8,
      background: '#fff',
      borderRadius: 6,
      fontSize: 13,
      border: '1px solid #e2e8f0'
    },
    eventTime: {
      color: '#64748b',
      fontSize: 12
    },
    eventLocation: {
      color: '#64748b',
      fontSize: 12
    },
    noEvents: {
      color: '#64748b',
      fontStyle: 'italic'
    },
    inputContainer: {
      padding: 16,
      borderTop: '1px solid #e2e8f0',
      background: '#f8fafc'
    },
    quickActions: {
      display: 'flex',
      gap: 8,
      marginBottom: 12,
      flexWrap: 'wrap'
    },
    quickAction: {
      padding: '6px 12px',
      borderRadius: 16,
      border: '1px solid #e2e8f0',
      background: '#fff',
      cursor: 'pointer',
      fontSize: 12,
      color: '#475569',
      transition: 'all 0.2s'
    },
    form: {
      display: 'flex',
      gap: 8
    },
    input: {
      flex: 1,
      padding: '12px 16px',
      borderRadius: 8,
      border: '1px solid #e2e8f0',
      fontSize: 14,
      outline: 'none'
    },
    sendButton: {
      padding: '12px 20px',
      borderRadius: 8,
      border: 0,
      background: '#2563eb',
      color: '#fff',
      cursor: 'pointer',
      fontSize: 14,
      fontWeight: 500,
      display: 'flex',
      alignItems: 'center',
      gap: 6
    },
    sendButtonDisabled: {
      background: '#94a3b8',
      cursor: 'not-allowed'
    },
    loadingDots: {
      display: 'flex',
      gap: 4,
      padding: '12px 16px',
      alignSelf: 'flex-start'
    },
    dot: {
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: '#94a3b8',
      animation: 'bounce 1.4s ease-in-out infinite'
    }
  };

  const quickActions = [
    { label: t('chat.quickScheduleMeeting'), action: t('chat.quickScheduleMeetingAction') },
    { label: t('chat.quickShowSchedule'), action: t('chat.quickShowScheduleAction') },
    { label: t('chat.quickAddReminder'), action: t('chat.quickAddReminderAction') }
  ];

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.headerTitle}>🗓️ {t('chat.title')}</h2>
        <button onClick={handleReset} style={styles.resetButton}>
          {t('chat.newConversation')}
        </button>
      </div>

      <div style={styles.messagesContainer}>
        {messages.map((msg, idx) => (
          <div key={idx}>
            <div style={{
              ...styles.message,
              ...(msg.role === 'user' ? styles.userMessage : 
                  msg.role === 'error' ? styles.errorMessage : 
                  styles.assistantMessage)
            }}>
              {msg.content}
            </div>
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div style={{ marginLeft: 16 }}>
                {msg.toolCalls.map((tc, tcIdx) => (
                  <div key={tcIdx}>{formatToolResult(tc)}</div>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={styles.loadingDots}>
            <div style={{...styles.dot, animationDelay: '0s'}}></div>
            <div style={{...styles.dot, animationDelay: '0.2s'}}></div>
            <div style={{...styles.dot, animationDelay: '0.4s'}}></div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div style={styles.inputContainer}>
        <div style={styles.quickActions}>
          {quickActions.map((qa, idx) => (
            <button
              key={idx}
              onClick={() => handleQuickAction(qa.action)}
              style={styles.quickAction}
              onMouseOver={(e) => e.target.style.background = '#f1f5f9'}
              onMouseOut={(e) => e.target.style.background = '#fff'}
            >
              {qa.label}
            </button>
          ))}
        </div>
        <form onSubmit={handleSubmit} style={styles.form}>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t('chat.inputPlaceholder')}
            style={styles.input}
            disabled={loading}
          />
          <button
            type="submit"
            style={{
              ...styles.sendButton,
              ...(loading || !input.trim() ? styles.sendButtonDisabled : {})
            }}
            disabled={loading || !input.trim()}
          >
            {loading ? t('chat.sending') : t('chat.send')}
          </button>
        </form>
      </div>

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }
      `}</style>
    </div>
  );
};
