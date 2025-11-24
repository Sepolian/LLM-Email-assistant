

const EmailView = ({ emails, loading, error, onDeleteEmail, selectedEmail, onSelectEmail, page, onPageChange }) => {
  const EmailDetailView = ({email, onBack}) => (
    <div style={{padding: 16, flex: 1}}>
        <button onClick={onBack} style={{marginBottom: '16px', background: 'transparent', border: '1px solid #ccc', padding: '8px 12px', borderRadius: '6px', cursor: 'pointer' }}>
            &larr; Back to Inbox
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
    <div style={{flex:1,padding:16, overflowY: 'auto'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
        <h2 style={{margin:0}}>收件箱</h2>
        <input placeholder="搜索邮件..." style={{padding:'8px 12px',borderRadius:8,border:'1px solid #e6eef6'}} />
      </div>
      {loading && <p>Loading emails...</p>}
      {error && <p>{error}</p>}
      {emails && emails.map(email => (
        <div key={email.id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:12,borderBottom:'1px solid #f1f5f9', cursor: 'pointer'}} onClick={() => onSelectEmail(email)}>
          <div style={{display:'flex',gap:12,alignItems:'center'}}>
            <div style={{width:40,height:40,background:'#eef2ff',borderRadius:40,display:'flex',alignItems:'center',justifyContent:'center'}}>{email.from.charAt(0).toUpperCase()}</div>
            <div>
              <div style={{fontWeight:600}}>{email.from}</div>
              <div style={{color:'#6b7280'}}>{email.subject}</div>
            </div>
          </div>
          <div>
            <div style={{color:'#94a3b8',fontSize:12, textAlign: 'right', marginBottom: '4px'}}>{new Date(email.received).toLocaleTimeString()}</div>
            <button onClick={(e) => { e.stopPropagation(); onDeleteEmail(email.id); }} style={{background:'transparent', border: '1px solid #ef4444', color: '#ef4444', padding: '4px 8px', borderRadius: '6px', cursor: 'pointer'}}>Delete</button>
          </div>
        </div>
      ))}
      <div style={{display:'flex', justifyContent:'center', alignItems:'center', marginTop: 16}}>
        <button onClick={() => onPageChange(page - 1)} disabled={page === 1} style={{padding: '8px 12px', borderRadius: 8, border: '1px solid #ccc', marginRight: 8, cursor: 'pointer'}}>Previous</button>
        <span>Page {page}</span>
        <button onClick={() => onPageChange(page + 1)} style={{padding: '8px 12px', borderRadius: 8, border: '1px solid #ccc', marginLeft: 8, cursor: 'pointer'}}>Next</button>
      </div>
    </div>
  );
  
  return (
    <div style={{display:'flex',height:'85vh',background:'#fff',borderRadius:12,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
      <div style={{width:220,borderRight:'1px solid #e6eef6',padding:12}}>
        <button style={{width:'100%',background:'#2563eb',color:'#fff',padding:8,borderRadius:8,border:0}}>撰写邮件</button>
        <div style={{marginTop:12}}>
          {['收件箱','已发送','草稿','垃圾箱'].map(item=> (
            <div key={item} style={{padding:'8px 6px',borderRadius:8,cursor:'pointer',marginTop:6}}>{item}</div>
          ))}
        </div>
      </div>
      {selectedEmail ? <EmailDetailView email={selectedEmail} onBack={() => onSelectEmail(null)} /> : <EmailListView />}
    </div>
  );
}
