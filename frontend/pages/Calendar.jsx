const CalendarView = ({ events = [], loading, error, currentMonth, onMonthChange, onResetMonth, onCreateEvent, onUpdateEvent, onDeleteEvent }) => {
  const [selectedEvent, setSelectedEvent] = React.useState(null);
  const [isEditing, setIsEditing] = React.useState(false);
  const [isCreating, setIsCreating] = React.useState(false);
  const [editForm, setEditForm] = React.useState({});

  const handleEventClick = (event) => {
    setSelectedEvent(event);
    setIsEditing(false);
    setIsCreating(false);
    setEditForm({});
  };

  const handleCloseModal = () => {
    setSelectedEvent(null);
    setIsEditing(false);
    setIsCreating(false);
  };

  const handleCreateClick = () => {
    setIsCreating(true);
    const now = new Date();
    const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
    // Adjust to local ISO string for input[type="datetime-local"]
    const toLocalISO = (date) => {
      const offset = date.getTimezoneOffset() * 60000;
      return new Date(date.getTime() - offset).toISOString().slice(0, 16);
    };
    
    setEditForm({
      summary: '',
      description: '',
      start: toLocalISO(now),
      end: toLocalISO(oneHourLater),
    });
  };

  const handleEditClick = () => {
    setIsEditing(true);
    setIsCreating(false);
    const toLocalISO = (dateStr) => {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        const offset = date.getTimezoneOffset() * 60000;
        return new Date(date.getTime() - offset).toISOString().slice(0, 16);
    };

    setEditForm({
      summary: selectedEvent.summary,
      description: selectedEvent.description,
      start: toLocalISO(selectedEvent.start?.dateTime || selectedEvent.start?.date),
      end: toLocalISO(selectedEvent.end?.dateTime || selectedEvent.end?.date),
    });
  };

  const handleSaveClick = async () => {
    if (isCreating && onCreateEvent) {
        // Convert back to ISO string with timezone if needed, or just send as is if backend handles it.
        // The backend expects ISO strings. The input gives "YYYY-MM-DDTHH:mm".
        // We should append ":00Z" or handle timezone properly. 
        // For simplicity, let's assume local time and convert to ISO.
        const toISO = (localStr) => new Date(localStr).toISOString();
        
        const payload = {
            title: editForm.summary,
            notes: editForm.description,
            start: toISO(editForm.start),
            end: toISO(editForm.end),
        };
        const success = await onCreateEvent(payload);
        if (success) {
            handleCloseModal();
        }
    } else if (onUpdateEvent && selectedEvent) {
        const toISO = (localStr) => new Date(localStr).toISOString();
        const payload = {
            ...editForm,
            start: toISO(editForm.start),
            end: toISO(editForm.end),
        };
        const success = await onUpdateEvent(selectedEvent.id, payload);
        if (success) {
            handleCloseModal();
        }
    }
  };

  const handleDeleteClick = async () => {
    if (onDeleteEvent && confirm('Are you sure you want to delete this event?')) {
      const success = await onDeleteEvent(selectedEvent.id);
      if (success) {
        handleCloseModal();
      }
    }
  };

  const activeMonth = currentMonth ? new Date(currentMonth) : new Date();
  const monthStart = new Date(activeMonth.getFullYear(), activeMonth.getMonth(), 1);
  const daysInMonth = new Date(activeMonth.getFullYear(), activeMonth.getMonth() + 1, 0).getDate();
  const startOffset = monthStart.getDay();

  const getEventStart = (event) => {
    if (event?.start?.date) {
       const [y, m, d] = event.start.date.split('-').map(Number);
       return new Date(y, m - 1, d);
    }
    const raw = event?.start?.dateTime;
    return raw ? new Date(raw) : null;
  };

  const getEventEnd = (event) => {
    if (event?.end?.date) {
       const [y, m, d] = event.end.date.split('-').map(Number);
       return new Date(y, m - 1, d);
    }
    const raw = event?.end?.dateTime;
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
    if (!start) return acc;

    const isAllDay = !!event?.start?.date;
    const end = getEventEnd(event);
    
    let current = new Date(start);
    current.setHours(0,0,0,0);
    
    let endLimit;
    if (end) {
        endLimit = new Date(end);
        if (!isAllDay) {
            // For timed events, subtract 1ms so midnight end doesn't spill over
            endLimit = new Date(endLimit.getTime() - 1);
        }
        endLimit.setHours(0,0,0,0);
    } else {
        endLimit = new Date(current);
    }

    // Safety break to prevent infinite loops
    let safety = 0;
    while (current <= endLimit && safety < 365) {
        // For all-day events, the end date from API is exclusive.
        // If start=2023-01-01, end=2023-01-02.
        // current=Jan 1. endLimit=Jan 2.
        // If we use <=, we get Jan 1 and Jan 2.
        // So for all-day, we should use < if we didn't adjust endLimit.
        // But wait, I didn't adjust endLimit for all-day above.
        // Let's adjust logic:
        
        if (isAllDay && current.getTime() === endLimit.getTime() && start.getTime() !== endLimit.getTime()) {
             // If it's the end date of an all-day event, and it's not a single day event (start != end)
             // Actually, single day all-day: start=Jan 1, end=Jan 2.
             // current=Jan 1. endLimit=Jan 2.
             // We want to stop at Jan 1.
             break;
        }
        
        const key = toDateKey(current);
        acc[key] = acc[key] || [];
        // Avoid duplicates if we process same event? No, reduce runs once per event.
        acc[key].push(event);
        
        current.setDate(current.getDate() + 1);
        safety++;
    }
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
          <button onClick={handleCreateClick} style={{background:'#2563eb',color:'#fff',padding:'6px 10px',borderRadius:8,border:0}}>+ 新建日程</button>
        </div>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(7,1fr)',gap:8,textAlign:'center',marginBottom:8}}>
        {['日','一','二','三','四','五','六'].map(d=> <div key={d} style={{color:'#94a3b8'}}>{d}</div>)}
      </div>
      <div style={{position:'relative', minHeight: 200}}>
        {loading && (
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(255,255,255,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            borderRadius: 12,
            backdropFilter: 'blur(2px)'
          }}>
            <div style={{color:'#2563eb', fontWeight:600}}>Loading...</div>
          </div>
        )}
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
                    <div key={(evt.id || evt.summary) + key} onClick={() => handleEventClick(evt)} style={{cursor:'pointer',fontSize:11,color:'#1e1b4b',padding:'3px 6px',borderRadius:999,background:'#c7d2fe',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
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
            <div key={event.id || event.summary} onClick={() => handleEventClick(event)} style={{cursor:'pointer',display:'flex',justifyContent:'space-between',alignItems:'center',padding:'14px 20px',border:'1px solid #dbe4ff',borderRadius:16,background:'#eef2ff'}}>
              <div>
                <div style={{fontWeight:600,color:'#0f172a'}}>{event.summary || '未命名事件'}</div>
                <div style={{color:'#475569',fontSize:13}}>{formatRange(event)}</div>
              </div>
              <div style={{fontWeight:700,color:'#1d4ed8',background:'#c7d2fe',padding:'4px 10px',borderRadius:999}}>{formatDayBadge(event)}</div>
            </div>
          ))}
        </div>
      </div>
      {(selectedEvent || isCreating) && (
        <div style={{position:'fixed',top:0,left:0,right:0,bottom:0,background:'rgba(0,0,0,0.5)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000}}>
          <div style={{background:'#fff',padding:24,borderRadius:12,width:400,maxWidth:'90%'}}>
            {isEditing || isCreating ? (
              <div style={{display:'flex',flexDirection:'column',gap:12}}>
                <h3>{isCreating ? '新建日程' : '编辑日程'}</h3>
                <input 
                  value={editForm.summary || ''} 
                  onChange={e => setEditForm({...editForm, summary: e.target.value})}
                  placeholder="标题"
                  style={{padding:8,borderRadius:4,border:'1px solid #ccc'}}
                />
                <textarea 
                  value={editForm.description || ''} 
                  onChange={e => setEditForm({...editForm, description: e.target.value})}
                  placeholder="描述"
                  style={{padding:8,borderRadius:4,border:'1px solid #ccc',minHeight:60}}
                />
                <input 
                  type="datetime-local"
                  value={editForm.start || ''} 
                  onChange={e => setEditForm({...editForm, start: e.target.value})}
                  style={{padding:8,borderRadius:4,border:'1px solid #ccc'}}
                />
                <input 
                  type="datetime-local"
                  value={editForm.end || ''} 
                  onChange={e => setEditForm({...editForm, end: e.target.value})}
                  style={{padding:8,borderRadius:4,border:'1px solid #ccc'}}
                />
                <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:12}}>
                  <button onClick={handleCloseModal} style={{padding:'8px 16px',borderRadius:6,border:'1px solid #ccc',background:'#fff'}}>取消</button>
                  <button onClick={handleSaveClick} style={{padding:'8px 16px',borderRadius:6,border:0,background:'#2563eb',color:'#fff'}}>保存</button>
                </div>
              </div>
            ) : (
              <div>
                <h3 style={{marginTop:0}}>{selectedEvent.summary || '未命名事件'}</h3>
                <p style={{color:'#64748b',fontSize:14}}>{formatRange(selectedEvent)}</p>
                {selectedEvent.description && <p style={{background:'#f1f5f9',padding:12,borderRadius:8,fontSize:14}}>{selectedEvent.description}</p>}
                <div style={{display:'flex',justifyContent:'flex-end',gap:8,marginTop:24}}>
                  <button onClick={handleDeleteClick} style={{padding:'8px 16px',borderRadius:6,border:'1px solid #ef4444',color:'#ef4444',background:'#fff'}}>删除</button>
                  <button onClick={handleEditClick} style={{padding:'8px 16px',borderRadius:6,border:'1px solid #2563eb',color:'#2563eb',background:'#fff'}}>编辑</button>
                  <button onClick={handleCloseModal} style={{padding:'8px 16px',borderRadius:6,border:'1px solid #ccc',background:'#fff'}}>关闭</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
