const { useState, useEffect } = React;

const ModernApp = ()=>{
  const [page, setPage] = useState(window.location.pathname);
  const [emails, setEmails] = useState(null);
  const [emailPage, setEmailPage] = useState(1);
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const handlePopState = () => setPage(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const fetchEmails = async (page = 1) => {
    try {
      const emailsResponse = await fetch(`/emails?page=${page}&per_page=20&days=7`);
      const emailsData = await emailsResponse.json();
      setEmails(emailsData);
    } catch (err) {
      setError("Failed to fetch emails.");
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

                const [_, eventsResponse] = await Promise.all([
                    fetchEmails(emailPage),
                    fetch('/calendar/events')
                ]);

                const eventsData = await eventsResponse.json();
                
                setEvents(eventsData);

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
      fetchEmails(emailPage);
    }
  }, [emailPage, isLoggedIn]);
  
  const handleEmailPageChange = (newPage) => {
    if (newPage > 0) {
      setEmailPage(newPage);
    }
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
    setEmails(null);
    setEvents(null);
    setError("You have been logged out.");
    navigate('/');
  }

  const handleDeleteEmail = async (emailId) => {
    try {
      const response = await fetch(`/emails/${emailId}`, { method: 'DELETE' });
      if (response.ok) {
        setEmails(emails.filter(email => email.id !== emailId));
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
      case 'email': return <EmailView emails={emails} loading={loading} error={error} onDeleteEmail={handleDeleteEmail} selectedEmail={selectedEmail} onSelectEmail={setSelectedEmail} page={emailPage} onPageChange={handleEmailPageChange} />;
      case 'calendar': return <CalendarView events={events} loading={loading} error={error} />;
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