const CalendarView = ({ events = [], loading, error, currentMonth, onMonthChange, onResetMonth }) => {
  const activeMonth = currentMonth ? new Date(currentMonth) : new Date();
  const monthStart = new Date(activeMonth.getFullYear(), activeMonth.getMonth(), 1);
  const daysInMonth = new Date(activeMonth.getFullYear(), activeMonth.getMonth() + 1, 0).getDate();
  const startOffset = monthStart.getDay();

  const getEventStart = (event) => {
    const raw = event?.start?.dateTime || event?.start?.date;
    return raw ? new Date(raw) : null;
  };

  const toDateKey = (date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const isSameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

  const eventsByDay = events.reduce((acc, event) => {
    const start = getEventStart(event);
    if (!start) {
      return acc;
    }
    const key = toDateKey(start);
    acc[key] = acc[key] || [];
    acc[key].push(event);
    return acc;
  }, {});

  Object.values(eventsByDay).forEach(list => {
    list.sort((a, b) => {
      const aStart = getEventStart(a)?.getTime() || 0;
      const bStart = getEventStart(b)?.getTime() || 0;
      return aStart - bStart;
    });
  });

  const allEventsSorted = [...events].sort((a, b) => {
    const aStart = getEventStart(a)?.getTime() || 0;
    const bStart = getEventStart(b)?.getTime() || 0;
    return bStart - aStart; // most recent first
  });
  const mostRecent = allEventsSorted.slice(0, 10);

  const cells = [];
  for (let i = 0; i < startOffset; i += 1) {
    cells.push(null);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    cells.push(new Date(activeMonth.getFullYear(), activeMonth.getMonth(), day));
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }

  const monthLabel = `${activeMonth.getFullYear()}年 ${activeMonth.getMonth() + 1}月`;

  const formatRange = (event) => {
    const start = event?.start?.dateTime;
    const end = event?.end?.dateTime;
    if (!start || !end) {
      return '全天';
    }
    const startDate = new Date(start);
    const endDate = new Date(end);
    return `${startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${endDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  };

  const formatDayBadge = (event) => {
    const start = getEventStart(event);
    if (!start) {
      return '日期待定';
    }
    return `${start.getMonth() + 1}月${start.getDate()}日`;
  };

  return (
    <div style={{background:'#fff',padding:16,borderRadius:12}}>
      <div style={{display:'flex',justifyContent:'space-between',marginBottom:12,alignItems:'center'}}>
        <div>
          <h2 style={{margin:0}}>{monthLabel}</h2>
          <p style={{margin:0,color:'#94a3b8'}}>浏览或跳转至任意月份，查看最近更新的事件。</p>
        </div>
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <button onClick={() => onMonthChange && onMonthChange(-1)} style={{padding:'6px 10px',borderRadius:8,border:'1px solid #dbe4ff'}}>上一月</button>
          <button onClick={() => onResetMonth && onResetMonth()} style={{padding:'6px 10px',borderRadius:8,border:'1px solid #dbe4ff'}}>今天</button>
          <button onClick={() => onMonthChange && onMonthChange(1)} style={{padding:'6px 10px',borderRadius:8,border:'1px solid #dbe4ff'}}>下一月</button>
          <button style={{background:'#2563eb',color:'#fff',padding:'6px 10px',borderRadius:8,border:0}}>+ 新建日程</button>
        </div>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:8,textAlign:'center',marginBottom:8}}>
        {['日','一','二','三','四','五','六'].map(d=> <div key={d} style={{color:'#94a3b8'}}>{d}</div>)}
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:8}}>
        {cells.map((cellDate, idx) => {
          if (!cellDate) {
            return <div key={`empty-${idx}`} />;
          }
          const key = toDateKey(cellDate);
          const dayEvents = eventsByDay[key] || [];
          const hasEvents = dayEvents.length > 0;
          const today = isSameDay(cellDate, new Date());
          const cellBackground = today ? '#dbeafe' : hasEvents ? '#eef2ff' : '#f8fafc';
          const borderColor = today ? '#2563eb' : hasEvents ? '#94a3b8' : '#eef2f7';
          return (
            <div key={key} style={{minHeight:120,border:`1px solid ${borderColor}`,borderRadius:12,padding:10,textAlign:'left',background:cellBackground,display:'flex',flexDirection:'column',gap:6}}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                <div style={{fontWeight:700,color:'#0f172a'}}>{cellDate.getDate()}</div>
                {today && <span style={{fontSize:11,color:'#2563eb',fontWeight:600}}>今天</span>}
              </div>
              <div style={{flex:1,display:'flex',flexDirection:'column',gap:4}}>
                {dayEvents.slice(0,2).map(evt => (
                  <div key={(evt.id || evt.summary) + key} style={{fontSize:11,color:'#1e1b4b',padding:'3px 6px',borderRadius:999,background:'#c7d2fe',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
                    {evt.summary || '未命名事件'}
                  </div>
                ))}
                {dayEvents.length === 0 && <div style={{fontSize:11,color:'#94a3b8'}}>暂无日程</div>}
                {dayEvents.length > 2 && <div style={{fontSize:11,color:'#4c1d95'}}>+{dayEvents.length - 2} 更多</div>}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{marginTop:24}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
          <h3 style={{margin:0}}>最新事件</h3>
          <span style={{color:'#94a3b8',fontSize:12}}>按更新时间倒序</span>
        </div>
        {loading && <p>Loading events...</p>}
        {error && <p>{error}</p>}
        {!loading && mostRecent.length === 0 && <div style={{color:'#94a3b8'}}>暂无事件</div>}
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          {mostRecent.map(event => (
            <div key={event.id || event.summary} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'14px 20px',border:'1px solid #dbe4ff',borderRadius:16,background:'#eef2ff'}}>
              <div>
                <div style={{fontWeight:600,color:'#0f172a'}}>{event.summary || '未命名事件'}</div>
                <div style={{color:'#475569',fontSize:13}}>{formatRange(event)}</div>
              </div>
              <div style={{fontWeight:700,color:'#1d4ed8',background:'#c7d2fe',padding:'4px 10px',borderRadius:999}}>{formatDayBadge(event)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
