const { useState, useEffect } = React;

const ModernApp = ()=>{
  const [page, setPage] = useState(window.location.pathname);
  const [mailbox, setMailbox] = useState(null);
  const [emailPage, setEmailPage] = useState(1);
  const [activeFolder, setActiveFolder] = useState('inbox');
  const [calendarEvents, setCalendarEvents] = useState([]);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date());
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [calendarError, setCalendarError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [user, setUser] = useState(null);
  const [emailCache, setEmailCache] = useState({});
  const [prefetchQueue, setPrefetchQueue] = useState([]);
  const [isPrefetching, setIsPrefetching] = useState(false);
  const [isFetchingEmails, setIsFetchingEmails] = useState(false);

  const applyEmailCacheSnapshot = (snapshot) => {
    if (!snapshot || !Array.isArray(snapshot.emails) || !snapshot.emails.length) {
      return;
    }
    const pseudoMailbox = {
      active_folder: 'inbox',
      page: 1,
      per_page: snapshot.emails.length,
      days: snapshot.window_days || 14,
      folders: {
        inbox: {
          label: 'INBOX',
          page: 1,
          has_next_page: false,
          items: snapshot.emails,
        },
      },
    };
    setMailbox((prev) => prev || pseudoMailbox);
  };

  const applyCalendarCacheSnapshot = (snapshot) => {
    if (!snapshot || !Array.isArray(snapshot.events) || !snapshot.events.length) {
      return;
    }
    setCalendarEvents((prev) => (Array.isArray(prev) && prev.length ? prev : snapshot.events));
  };

  const hydrateFromSnapshots = async () => {
    try {
      const cacheResponse = await fetch('/emails/cache');
      if (cacheResponse.ok) {
        const snapshot = await cacheResponse.json();
        applyEmailCacheSnapshot(snapshot);
      }
    } catch (err) {
      console.warn('Emails cache hydration failed', err);
    }

    try {
      const calendarResponse = await fetch('/calendar/cache');
      if (calendarResponse.ok) {
        const snapshot = await calendarResponse.json();
        applyCalendarCacheSnapshot(snapshot);
      }
    } catch (err) {
      console.warn('Calendar cache hydration failed', err);
    }
  };

  useEffect(() => {
    const handlePopState = () => setPage(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const formatMonthParam = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
  };

  const fetchEmails = async ({ folder = activeFolder, page = emailPage, background = false, force = false } = {}) => {
    const folderKey = folder || activeFolder;
    if (!background) {
      setIsFetchingEmails(true);
    }

    if (!force && !background) {
      const cachedData = emailCache?.[folderKey]?.[page];
      if (cachedData) {
        setMailbox(cachedData);
        const requestedFolder = folderKey;
        const isCustomLabel = requestedFolder?.startsWith('label:');
        if (!isCustomLabel && cachedData?.active_folder && cachedData.active_folder !== activeFolder) {
          setActiveFolder(cachedData.active_folder);
        }
        setIsFetchingEmails(false);
        return cachedData;
      }
    }

    try {
      const params = new URLSearchParams({
        folder: folderKey,
        page: String(page),
        per_page: '20',
        days: '14'
      });
      const emailsResponse = await fetch(`/emails?${params.toString()}`);
      if (!emailsResponse.ok) {
        throw new Error('Email request failed');
      }
      const emailsData = await emailsResponse.json();
      setEmailCache((prev) => ({
        ...prev,
        [folderKey]: {
          ...(prev[folderKey] || {}),
          [page]: emailsData,
        },
      }));

      if (!background) {
        setMailbox(emailsData);
        const requestedFolder = folderKey;
        const isCustomLabel = requestedFolder?.startsWith('label:');
        if (!isCustomLabel && emailsData?.active_folder && emailsData.active_folder !== activeFolder) {
          setActiveFolder(emailsData.active_folder);
        }
      }
      return emailsData;
    } catch (err) {
      if (!background) {
        setError("Failed to fetch emails.");
      }
      return null;
    } finally {
      if (!background) {
        setIsFetchingEmails(false);
      }
    }
  };

  const fetchCalendarEvents = async (targetMonth = calendarMonth) => {
    if (!targetMonth) {
      return null;
    }

    setCalendarLoading(true);
    setCalendarError(null);
    try {
      const params = new URLSearchParams({
        month: formatMonthParam(targetMonth),
        max_results: '200'
      });
      const response = await fetch(`/calendar/events?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Calendar request failed');
      }
      const data = await response.json();
      setCalendarEvents(Array.isArray(data) ? data : []);
      return data;
    } catch (err) {
      setCalendarError('Failed to fetch calendar events.');
      return null;
    } finally {
      setCalendarLoading(false);
    }
  };

  useEffect(() => {
    const initialize = async () => {
        setLoading(true);
        try {
            const userResponse = await fetch('/user');
            if (userResponse.ok) {
                const userData = await userResponse.json();
                setUser(userData);
                setIsLoggedIn(true);

          await hydrateFromSnapshots();

                await fetchEmails({ folder: activeFolder, page: emailPage });

            } else {
                setIsLoggedIn(false);
                 setError("Please login to continue.");
            }
        } catch (err) {
            setError("Failed to fetch data.");
            setIsLoggedIn(false);
        } finally {
            setLoading(false);
        }
    };

    initialize();
  }, []);

  useEffect(() => {
    if(isLoggedIn) {
      fetchEmails({ folder: activeFolder, page: emailPage });
    }
  }, [emailPage, activeFolder, isLoggedIn]);

  useEffect(() => {
    if (!isLoggedIn) {
      return;
    }
    const pagesToPrefetch = [];
    for (let offset = 1; offset <= 5; offset += 1) {
      const targetPage = emailPage + offset;
      if (!emailCache[activeFolder]?.[targetPage]) {
        pagesToPrefetch.push({ folder: activeFolder, page: targetPage });
      }
    }
    if (pagesToPrefetch.length) {
      setPrefetchQueue((prev) => {
        const next = [...prev];
        pagesToPrefetch.forEach((item) => {
          const exists = next.some((queued) => queued.folder === item.folder && queued.page === item.page);
          if (!exists) {
            next.push(item);
          }
        });
        return next;
      });
    }
  }, [emailPage, activeFolder, isLoggedIn, emailCache]);

  useEffect(() => {
    if (!isLoggedIn || isPrefetching || prefetchQueue.length === 0) {
      return;
    }
    const nextItem = prefetchQueue[0];
    const runPrefetch = async () => {
      setIsPrefetching(true);
      if (!emailCache[nextItem.folder]?.[nextItem.page]) {
        await fetchEmails({ folder: nextItem.folder, page: nextItem.page, background: true });
      }
      setPrefetchQueue((prev) => prev.slice(1));
      setIsPrefetching(false);
    };
    runPrefetch();
  }, [prefetchQueue, isPrefetching, isLoggedIn, emailCache]);

  const handleRefresh = () => {
    setEmailCache((prev) => {
      if (!prev[activeFolder]) {
        return prev;
      }
      const next = { ...prev };
      delete next[activeFolder];
      return next;
    });
    setPrefetchQueue((prev) => prev.filter((entry) => entry.folder !== activeFolder));
    if (emailPage === 1) {
      fetchEmails({ folder: activeFolder, page: 1, force: true });
    } else {
      setEmailPage(1);
    }
  };

  useEffect(() => {
    if (isLoggedIn) {
      fetchCalendarEvents(calendarMonth);
    }
  }, [calendarMonth, isLoggedIn]);
  
  const handleEmailPageChange = (newPage) => {
    if (newPage > 0 && newPage !== emailPage) {
      setEmailPage(newPage);
    }
  };

  const handleFolderChange = (folderKey) => {
    if (folderKey !== activeFolder) {
      setActiveFolder(folderKey);
      setEmailPage(1);
      setSelectedEmail(null);
    }
  };

  const handleCalendarMonthChange = (direction) => {
    setCalendarMonth(prev => {
      const base = prev ? new Date(prev) : new Date();
      const next = new Date(base.getFullYear(), base.getMonth() + direction, 1);
      return next;
    });
  };

  const handleCalendarToday = () => {
    setCalendarMonth(new Date());
  };

  const navigate = (path) => {
    if (path !== window.location.pathname) {
      window.history.pushState({}, '', path);
      setPage(path);
    }
  };
  
  const handleLogout = async () => {
    await fetch('/logout');
    setIsLoggedIn(false);
    setUser(null);
    setMailbox(null);
    setCalendarEvents([]);
    setCalendarError(null);
    setCalendarMonth(new Date());
    setCalendarLoading(false);
    setError("You have been logged out.");
    navigate('/');
  }

  const handleDeleteEmail = async (emailId) => {
    try {
      const response = await fetch(`/emails/${emailId}`, { method: 'DELETE' });
      if (response.ok) {
        fetchEmails({ folder: activeFolder, page: emailPage });
      } else {
        const errorData = await response.json();
        setError(errorData.detail || "Failed to delete email.");
      }
    } catch (err) {
      setError("Failed to delete email.");
    }
  };
  
  const renderContent = ()=>{
    if(loading) {
        return <div style={{textAlign:'center', padding: '40px 0'}}>Loading...</div>;
    }

    if (!isLoggedIn) {
        return (
            <div style={{textAlign:'center', padding: '40px 0'}}>
                <h2>Please log in</h2>
                <p>{error || "Log in with your Google account to continue."}</p>
                <a href="/login">
                    <button style={{background:'#2563eb',color:'#fff',padding:'10px 20px',borderRadius:8,border:0,cursor:'pointer'}}>Login with Google</button>
                </a>
            </div>
        );
    }
    
    let activeTab;
    switch(page){
      case '/': activeTab = 'home'; break;
      case '/email': activeTab = 'email'; break;
      case '/calendar': activeTab = 'calendar'; break;
      case '/settings': activeTab = 'settings'; break;
      default: activeTab = 'home';
    }

    switch(activeTab){
      case 'home': return <HomeView />;
      case 'email': return (
        <EmailView 
          mailbox={mailbox} 
          loading={loading} 
          fetching={isFetchingEmails}
          error={error} 
          onDeleteEmail={handleDeleteEmail} 
          selectedEmail={selectedEmail} 
          onSelectEmail={setSelectedEmail} 
          page={emailPage} 
          onPageChange={handleEmailPageChange}
          activeFolder={activeFolder}
          onFolderChange={handleFolderChange}
          onRefresh={handleRefresh}
        />
      );
      case 'calendar': return (
        <CalendarView 
          events={calendarEvents} 
          loading={calendarLoading} 
          error={calendarError || error} 
          currentMonth={calendarMonth}
          onMonthChange={handleCalendarMonthChange}
          onResetMonth={handleCalendarToday}
        />
      );
      case 'settings': return <SettingsView user={user} />;
      default: return <HomeView />;
    }
  }

  return (
    <div style={{minHeight:'100vh',background:'#f8fafc',padding:12}}>
      <nav style={{display:'flex',justifyContent:'space-between',alignItems:'center',height:64,background:'#fff',padding:'0 12px',borderRadius:8,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
        <div style={{display:'flex',alignItems:'center',gap:8,cursor:'pointer'}} onClick={()=>navigate('/')}>
          <div style={{width:36,height:36,background:'#2563eb',borderRadius:8,color:'#fff,',display:'flex',alignItems:'center',justifyContent:'center',fontWeight:700}}>M</div>
          <div style={{fontWeight:700,color:'#0f172a'}}>MailFlow</div>
        </div>
        {isLoggedIn && (<div style={{display:'flex',gap:6}}>
          <a href="/" onClick={(e) => { e.preventDefault(); navigate('/'); }} style={{padding:'8px 12px',borderRadius:8,background: page ==='/' ? '#eef2ff':'transparent', textDecoration: 'none', color: 'inherit'}}>概览</a>
          <a href="/email" onClick={(e) => { e.preventDefault(); navigate('/email'); }} style={{padding:'8px 12px',borderRadius:8,background: page ==='/email' ? '#eef2ff':'transparent', textDecoration: 'none', color: 'inherit'}}>邮件</a>
          <a href="/calendar" onClick={(e) => { e.preventDefault(); navigate('/calendar'); }} style={{padding:'8px 12px',borderRadius:8,background: page ==='/calendar' ? '#eef2ff':'transparent', textDecoration: 'none', color: 'inherit'}}>日历</a>
        </div>)}
        <div style={{display:'flex',gap:8, alignItems: 'center'}}>
          {isLoggedIn ? (
            <>
              <a href="/settings" onClick={(e) => { e.preventDefault(); navigate('/settings'); }} style={{padding:8,borderRadius:8, textDecoration: 'none', color: 'inherit'}}>设置</a>
              {user && <div style={{fontWeight:600}}>{user.name}</div>}
              <button onClick={handleLogout} style={{padding:8,borderRadius:8}}>Logout</button>
            </>
          ) : (
            <a href="/login">
              <button style={{padding:'8px 12px',borderRadius:8, background:'#2563eb', color: '#fff', border:0}}>Login</button>
            </a>
          )}
        </div>
      </nav>

      <main style={{maxWidth:1100,margin:'20px auto'}}>
        {renderContent()}
      </main>
    </div>
  )
}

const container = document.getElementById('root');
const root = ReactDOM.createRoot(container);
root.render(<ModernApp />);