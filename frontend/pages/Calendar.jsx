

const CalendarView = ({ events, loading, error }) => (
  <div style={{background:'#fff',padding:16,borderRadius:12}}>
    <div style={{display:'flex',justifyContent:'space-between',marginBottom:12}}>
      <h2>2025年 11月</h2>
      <div>
        <button style={{marginRight:8}}>今天</button>
        <button style={{background:'#2563eb',color:'#fff',padding:'6px 10px',borderRadius:8,border:0}}>+ 新建日程</button>
      </div>
    </div>
    <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:8,textAlign:'center',marginBottom:8}}>
      {['日','一','二','三','四','五','六'].map(d=> <div key={d} style={{color:'#94a3b8'}}>{d}</div>)}
    </div>
    <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:8}}>
      {Array.from({length:30}).map((_,i)=> (
        <div key={i} style={{height:120,border:'1px solid #eef2f7',borderRadius:8,padding:8,textAlign:'left'}}>
          <div style={{fontWeight:600}}>{i+1}</div>
        </div>
      ))}
    </div>
    {loading && <p>Loading events...</p>}
    {error && <p>{error}</p>}
    {events && events.map(event => (
      <div key={event.id}>{event.summary}</div>
    ))}
  </div>
)
