

const HomeView = ()=>{
  const logs = [
    { id: 1, title: "邮件分类完成", desc: "成功将 '发票 #2024' 归档至财务文件夹", time: "刚刚", status: "success" },
    { id: 2, title: "检测到垃圾邮件", desc: "拦截了来自 marketing@spam.com 的邮件", time: "10分钟前", status: "warning" },
  ];
  return (
    <div>
      <header style={{marginBottom:16}}>
        <h1 style={{fontSize:22}}>系统概览</h1>
        <p style={{color:'#6b7280'}}>后端自动化任务的实时监控面板</p>
      </header>
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:12,marginBottom:16}}>
        <div style={{background:'#fff',padding:16,borderRadius:12,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
          <div style={{fontSize:12,color:'#6b7280'}}>今日处理</div>
          <div style={{fontSize:20,fontWeight:700}}>128 封</div>
        </div>
        <div style={{background:'#fff',padding:16,borderRadius:12,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
          <div style={{fontSize:12,color:'#6b7280'}}>平均耗时</div>
          <div style={{fontSize:20,fontWeight:700}}>0.8 秒</div>
        </div>
        <div style={{background:'#fff',padding:16,borderRadius:12,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
          <div style={{fontSize:12,color:'#6b7280'}}>异常错误</div>
          <div style={{fontSize:20,fontWeight:700}}>1 个</div>
        </div>
      </div>

      <div style={{background:'#fff',borderRadius:12,boxShadow:'0 1px 2px rgba(0,0,0,0.03)'}}>
        <div style={{padding:16,borderBottom:'1px solid #f1f5f9',display:'flex',justifyContent:'space-between'}}>
          <h3 style={{margin:0}}>最近处理日志</h3>
          <button style={{background:'none',border:0,color:'#2563eb'}}>查看全部</button>
        </div>
        <div>
          {logs.map(log=> (
            <div key={log.id} style={{padding:16,borderBottom:'1px solid #f8fafc',display:'flex',gap:12}}>
              <div style={{width:8,height:8,borderRadius:8,marginTop:6,background: log.status==='success'? '#10b981': (log.status==='warning'?'#f59e0b':'#ef4444')}}></div>
              <div style={{flex:1}}>
                <div style={{display:'flex',justifyContent:'space-between'}}>
                  <h4 style={{margin:0}}>{log.title}</h4>
                  <span style={{fontSize:12,color:'#94a3b8'}}>{log.time}</span>
                </div>
                <p style={{margin:0,color:'#6b7280',fontSize:13}}>{log.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
