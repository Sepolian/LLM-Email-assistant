const FOLDER_DISPLAY = [
  { key: 'inbox', label: '收件箱' },
  { key: 'sent', label: '已发送' },
  { key: 'drafts', label: '草稿' },
  { key: 'trash', label: '回收站' },
];

const EmailView = ({ mailbox, loading, error, onDeleteEmail, selectedEmail, onSelectEmail, page, onPageChange, activeFolder, onFolderChange }) => {
  const folderData = mailbox?.folders?.[activeFolder] || { items: [], page, has_next_page: false };
  const emails = folderData.items || [];
  const displayEmails = emails.slice(0, perPage);
  const perPage = mailbox?.per_page || 20;
  const isEmpty = !loading && displayEmails.length === 0;

  const EmailDetailView = ({email, onBack}) => (
    <div style={{padding: 16, flex: 1}}>
        <button onClick={onBack} style={{marginBottom: '16px', background: 'transparent', border: '1px solid #ccc', padding: '8px 12px', borderRadius: '6px', cursor: 'pointer' }}>
          &larr; 返回列表
        </button>
        <div style={{borderBottom: '1px solid #eee', paddingBottom: '8px', marginBottom: '16px'}}>
            <h2 style={{margin: 0}}>{email.subject}</h2>
            <p style={{margin: '4px 0', color: '#6b7280'}}>From: {email.from}</p>
        </div>
        <div style={{whiteSpace: 'pre-wrap'}}>
            {email.body}
        </div>
    </div>
  );

  const EmailListView = () => (
    <div style={{flex:1,padding:16, overflowY: 'auto', display:'flex', flexDirection:'column', minHeight:'70vh'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
        <div>
          <h2 style={{margin:0}}>{FOLDER_DISPLAY.find(f => f.key === activeFolder)?.label || '邮件'}</h2>
          <p style={{margin:0, color:'#94a3b8', fontSize:12}}>最多显示 {perPage} 封邮件 / 页，列表会自动填满。</p>
        </div>
        <input placeholder="搜索邮件..." style={{padding:'8px 12px',borderRadius:8,border:'1px solid #e6eef6'}} />
      </div>
      {loading && <p>Loading emails...</p>}
      {error && <p>{error}</p>}
      {isEmpty && <div style={{padding:24,textAlign:'center',color:'#94a3b8'}}>暂无邮件</div>}
      <div style={{flex:1}}>
        {displayEmails.map(email => {
          const initials = email.from ? email.from.charAt(0).toUpperCase() : '?';
          const received = email.received ? new Date(email.received).toLocaleString() : '刚刚';
          return (
            <div key={email.id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'12px 4px',borderBottom:'1px solid #f1f5f9', cursor: 'pointer'}} onClick={() => onSelectEmail(email)}>
              <div style={{display:'flex',gap:12,alignItems:'center'}}>
                <div style={{width:40,height:40,background:'#eef2ff',borderRadius:40,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:600,color:'#4c1d95'}}>{initials}</div>
                <div>
                  <div style={{fontWeight:600}}>{email.from || '未知发件人'}</div>
                  <div style={{color:'#6b7280'}}>{email.subject || '（无主题）'}</div>
                </div>
              </div>
              <div style={{textAlign:'right'}}>
                <div style={{color:'#94a3b8',fontSize:12, marginBottom: '4px'}}>{received}</div>
                <button onClick={(e) => { e.stopPropagation(); onDeleteEmail(email.id); }} style={{background:'transparent', border: '1px solid #ef4444', color: '#ef4444', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer'}}>Delete</button>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{display:'flex', justifyContent:'center', alignItems:'center', marginTop: 16, gap:12}}>
        <button onClick={() => onPageChange(page - 1)} disabled={page === 1} style={{padding: '8px 16px', borderRadius: 999, border: '1px solid #cbd5f5', background: page === 1 ? '#f1f5f9' : '#fff', cursor: page === 1 ? 'not-allowed' : 'pointer'}}>上一页</button>
        <div style={{padding:'6px 16px', borderRadius:999, background:'#eef2ff', fontWeight:600}}>第 {folderData.page || page} 页</div>
        <button onClick={() => onPageChange(page + 1)} disabled={!folderData.has_next_page} style={{padding: '8px 16px', borderRadius: 999, border: '1px solid #cbd5f5', background: folderData.has_next_page ? '#fff' : '#f1f5f9', cursor: folderData.has_next_page ? 'pointer' : 'not-allowed'}}>下一页</button>
      </div>
    </div>
  );
  
  return (
    <div style={{display:'flex',minHeight:'85vh',background:'#fff',borderRadius:12,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
      <div style={{width:220,borderRight:'1px solid #e6eef6',padding:12,display:'flex',flexDirection:'column',gap:16}}>
        <button style={{width:'100%',background:'#2563eb',color:'#fff',padding:8,borderRadius:8,border:0}}>撰写邮件</button>
        <div style={{display:'flex',flexDirection:'column',gap:6}}>
          {FOLDER_DISPLAY.map(folder => (
            <div 
              key={folder.key}
              onClick={() => onFolderChange(folder.key)}
              style={{
                padding:'8px 10px',
                borderRadius:8,
                cursor:'pointer',
                background: activeFolder === folder.key ? '#eef2ff' : 'transparent',
                fontWeight: activeFolder === folder.key ? 600 : 500
              }}
            >{folder.label}</div>
          ))}
        </div>
      </div>
      {selectedEmail ? <EmailDetailView email={selectedEmail} onBack={() => onSelectEmail(null)} /> : <EmailListView />}
    </div>
  );
}
