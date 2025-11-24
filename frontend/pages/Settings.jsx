

const SettingsView = ({user})=> (
  <div style={{background:'#fff',borderRadius:12,overflow:'hidden'}}>
    <div style={{padding:16,borderBottom:'1px solid #f1f5f9'}}>
      <h2 style={{margin:0}}>系统设置</h2>
      <p style={{color:'#6b7280'}}>管理您的通知偏好和账户信息</p>
    </div>
    <div style={{padding:16}}>
      <h3 style={{fontSize:12,letterSpacing:1}}>账户</h3>
      {user && (
        <div style={{display:'flex',gap:12,alignItems:'center',marginTop:8}}>
            {user.picture && <img src={user.picture} alt={user.name} style={{width:64,height:64,borderRadius:64}} />}
            {!user.picture && <div style={{width:64,height:64,borderRadius:64,background:'#e2e8f0'}}></div>}
            <div>
            <div style={{fontWeight:600}}>{user.name}</div>
            <div style={{color:'#6b7280'}}>{user.email}</div>
            </div>
        </div>
      )}
    </div>
  </div>
)
