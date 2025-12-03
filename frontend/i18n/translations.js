// Bilingual translations (English & Chinese)
const translations = {
  en: {
    // Navigation
    nav: {
      overview: 'Overview',
      email: 'Email',
      calendar: 'Calendar',
      chat: 'Chat',
      settings: 'Settings',
      login: 'Login',
      logout: 'Logout',
    },
    // Home page
    home: {
      title: 'System Overview',
      subtitle: 'Real-time monitoring dashboard for backend automation tasks',
      loading: 'Loading...',
      automationStatus: 'Automation Status',
      enabled: 'Enabled',
      disabled: 'Disabled',
      activeRules: 'Active Rules',
      rulesCount: 'rules',
      recentEmails: 'Recent Emails Processed',
      emailsCount: 'emails',
      lastRun: 'Last Run',
      cacheSync: 'Cache Sync',
      justNow: 'Just now',
      minutesAgo: 'minutes ago',
      hoursAgo: 'hours ago',
      noData: 'No data',
      automationRunning: 'Automation task is running...',
      recentError: 'Recent Error',
      activityLogs: 'Recent Activity Logs',
      logsTotal: 'Total',
      logsRetention: 'Retention',
      days: 'days',
      noLogs: 'No logs available',
      error: 'Error',
    },
    // Email page
    email: {
      folders: 'Folders',
      inbox: 'Inbox',
      sent: 'Sent',
      drafts: 'Drafts',
      trash: 'Trash',
      customLabels: 'Custom Labels',
      refresh: 'Refresh',
      noEmails: 'No emails',
      noSubject: '(No subject)',
      backToList: '← Back to list',
      selectEmail: 'Select an email to view',
      prevPage: 'Previous',
      nextPage: 'Next',
      page: 'Page',
      summarize: 'Summarize',
      summarizing: 'Summarizing...',
      summary: 'Summary',
      noSummary: 'No summary yet. Click "Summarize".',
      proposals: 'Proposals',
      addToCalendar: 'Add to Calendar',
      adding: 'Adding...',
      added: 'Added ✓',
      failed: 'Failed ✗',
    },
    // Calendar page
    calendar: {
      title: 'Calendar',
      browseDesc: 'Browse or jump to any month to view recent events.',
      prevMonth: 'Previous',
      today: 'Today',
      nextMonth: 'Next',
      newEvent: '+ New Event',
      sun: 'Sun',
      mon: 'Mon',
      tue: 'Tue',
      wed: 'Wed',
      thu: 'Thu',
      fri: 'Fri',
      sat: 'Sat',
      noEvents: 'No events',
      moreEvents: 'more',
      allDay: 'All day',
      pendingProposals: '📬 Pending Event Proposals',
      pendingCount: 'pending',
      ignore: 'Ignore',
      addToCalendar: 'Add to Calendar',
      fromEmail: 'From email:',
      dateTBD: 'Date TBD',
      recentEvents: 'Recent Events',
      sortedByTime: 'Sorted by update time',
      noEventsYet: 'No events yet',
      unnamed: 'Unnamed event',
      newEventTitle: 'New Event',
      editEvent: 'Edit Event',
      titlePlaceholder: 'Title',
      descPlaceholder: 'Description',
      cancel: 'Cancel',
      save: 'Save',
      delete: 'Delete',
      edit: 'Edit',
      close: 'Close',
      confirmDelete: 'Are you sure you want to delete this event?',
      loading: 'Loading...',
    },
    // Settings page
    settings: {
      title: 'System Settings',
      subtitle: 'Manage your account and automation labels',
      account: 'Account',
      autoLabel: 'Auto Labeling',
      autoLabelDesc: 'Periodically add labels to emails based on custom rules',
      on: 'ON',
      off: 'OFF',
      runNow: 'Run Now',
      running: 'Running...',
      lastRun: 'Last Run',
      lastProcessed: 'Last Processed',
      cacheSync: 'Cache Sync',
      errors: 'Errors',
      noErrors: 'None',
      activityLogs: 'Activity Logs',
      noLogs: 'No logs',
      labelName: 'Label name',
      matchReason: 'Match reason, e.g. "emails from finance department"',
      addRule: 'Add Rule',
      saving: 'Saving...',
      rulesList: 'Rules List',
      loadingRules: 'Loading...',
      noRules: 'No rules yet. Add your first rule to enable auto labeling.',
      label: 'Label',
      reason: 'Reason',
      action: 'Action',
      deleteRule: 'Delete',
      autoAddEvents: '📅 Auto Add Events',
      autoAddEventsDesc: 'Automatically extract events from emails and add to calendar. When disabled, extracted events will be shown as proposals on the calendar page for your confirmation.',
      autoAddOn: '✅ System will automatically add recognized events from emails to your calendar.',
      autoAddOff: '⏸️ System will save recognized events from emails as proposals. You can manually confirm them on the calendar page.',
      notExecuted: 'Not executed',
      enterLabelAndReason: 'Please enter label name and match reason',
    },
    // Chat page
    chat: {
      title: 'Calendar Assistant',
      welcomeMessage: "Hi! I'm your calendar assistant. I can help you:\n\n• Schedule meetings and events\n• Check your upcoming schedule\n• Update or cancel events\n\nTry saying something like \"Schedule a meeting on 03/12 at 2pm in SHB\"",
      inputPlaceholder: 'Type your message... (e.g., "Add a meeting tomorrow at 3pm")',
      send: 'Send',
      sending: 'Sending...',
      newConversation: 'New Chat',
      eventCreated: 'Event Created',
      eventUpdated: 'Event Updated',
      eventDeleted: 'Event Deleted',
      noUpcomingEvents: 'No upcoming events found',
      quickScheduleMeeting: '📅 Schedule Meeting',
      quickScheduleMeetingAction: 'Schedule a meeting for tomorrow at 2pm',
      quickShowSchedule: '📋 Show Schedule',
      quickShowScheduleAction: 'Show my schedule for this week',
      quickAddReminder: '⏰ Add Reminder',
      quickAddReminderAction: 'Add a reminder for tomorrow morning',
    },
    // Common
    common: {
      login: 'Login',
      logout: 'Logout',
      loginPrompt: 'Please log in',
      loginDesc: 'Log in with your Google account to continue.',
      loginWithGoogle: 'Login with Google',
      loading: 'Loading...',
      year: '',
      month: '',
    },
  },
  zh: {
    // Navigation
    nav: {
      overview: '概览',
      email: '邮件',
      calendar: '日历',
      chat: '对话',
      settings: '设置',
      login: '登录',
      logout: '退出',
    },
    // Home page
    home: {
      title: '系统概览',
      subtitle: '后端自动化任务的实时监控面板',
      loading: '加载中...',
      automationStatus: '自动化状态',
      enabled: '已启用',
      disabled: '已禁用',
      activeRules: '活跃规则',
      rulesCount: '条',
      recentEmails: '最近处理邮件',
      emailsCount: '封',
      lastRun: '最近运行',
      cacheSync: '缓存同步',
      justNow: '刚刚',
      minutesAgo: '分钟前',
      hoursAgo: '小时前',
      noData: '暂无',
      automationRunning: '自动化任务正在运行中...',
      recentError: '最近错误',
      activityLogs: '最近处理日志',
      logsTotal: '共',
      logsRetention: '保留',
      days: '天',
      noLogs: '暂无日志记录',
      error: '错误',
    },
    // Email page
    email: {
      folders: '文件夹',
      inbox: '收件箱',
      sent: '已发送',
      drafts: '草稿',
      trash: '回收站',
      customLabels: '自定义标签',
      refresh: '刷新',
      noEmails: '没有邮件',
      noSubject: '(无主题)',
      backToList: '← 返回列表',
      selectEmail: '选择一封邮件查看',
      prevPage: '上一页',
      nextPage: '下一页',
      page: '第',
      summarize: '生成摘要',
      summarizing: '生成中...',
      summary: '摘要',
      noSummary: '暂无摘要，点击"生成摘要"。',
      proposals: '日程提议',
      addToCalendar: '添加到日历',
      adding: '添加中...',
      added: '已添加 ✓',
      failed: '失败 ✗',
    },
    // Calendar page
    calendar: {
      title: '日历',
      browseDesc: '浏览或跳转至任意月份，查看最近更新的事件。',
      prevMonth: '上一月',
      today: '今天',
      nextMonth: '下一月',
      newEvent: '+ 新建日程',
      sun: '日',
      mon: '一',
      tue: '二',
      wed: '三',
      thu: '四',
      fri: '五',
      sat: '六',
      noEvents: '暂无日程',
      moreEvents: '更多',
      allDay: '全天',
      pendingProposals: '📬 待处理的日程提案',
      pendingCount: '个待确认',
      ignore: '忽略',
      addToCalendar: '添加到日历',
      fromEmail: '来自邮件：',
      dateTBD: '日期待定',
      recentEvents: '最新事件',
      sortedByTime: '按更新时间倒序',
      noEventsYet: '暂无事件',
      unnamed: '未命名事件',
      newEventTitle: '新建日程',
      editEvent: '编辑日程',
      titlePlaceholder: '标题',
      descPlaceholder: '描述',
      cancel: '取消',
      save: '保存',
      delete: '删除',
      edit: '编辑',
      close: '关闭',
      confirmDelete: '确定要删除这个事件吗？',
      loading: '加载中...',
    },
    // Settings page
    settings: {
      title: '系统设置',
      subtitle: '管理您的账户信息与自动化标签',
      account: '账户',
      autoLabel: '自动标签',
      autoLabelDesc: '根据自定义规则定期为邮件添加标签',
      on: '已开启',
      off: '已关闭',
      runNow: '立即运行',
      running: '运行中…',
      lastRun: '最近运行',
      lastProcessed: '最近处理',
      cacheSync: '缓存同步',
      errors: '错误',
      noErrors: '暂无',
      activityLogs: '操作日志',
      noLogs: '暂无日志',
      labelName: '标签名称',
      matchReason: '匹配理由，如"来自财务部的对账邮件"',
      addRule: '添加规则',
      saving: '保存中...',
      rulesList: '规则列表',
      loadingRules: '加载中...',
      noRules: '暂无规则，添加第一个规则以启用自动标签。',
      label: '标签',
      reason: '理由',
      action: '操作',
      deleteRule: '删除',
      autoAddEvents: '📅 自动添加日程',
      autoAddEventsDesc: '自动从邮件中提取日程并添加到日历。关闭时，提取的日程会显示在日历页面等待您确认。',
      autoAddOn: '✅ 系统会自动将邮件中识别出的日程事件添加到您的日历中。',
      autoAddOff: '⏸️ 系统会将邮件中识别出的日程事件保存为提案，您可以在日历页面手动确认添加。',
      notExecuted: '尚未执行',
      enterLabelAndReason: '请输入标签名称和匹配理由',
    },
    // Chat page
    chat: {
      title: '日历助手',
      welcomeMessage: '你好！我是你的日历助手。我可以帮你：\n\n• 安排会议和活动\n• 查看日程安排\n• 更新或取消活动\n\n试试说「在03/12下午2点安排一个会议，地点在SHB」',
      inputPlaceholder: '输入消息... (例如：「明天下午3点添加一个会议」)',
      send: '发送',
      sending: '发送中...',
      newConversation: '新对话',
      eventCreated: '活动已创建',
      eventUpdated: '活动已更新',
      eventDeleted: '活动已删除',
      noUpcomingEvents: '暂无即将到来的活动',
      quickScheduleMeeting: '📅 安排会议',
      quickScheduleMeetingAction: '明天下午2点安排一个会议',
      quickShowSchedule: '📋 查看日程',
      quickShowScheduleAction: '显示我这周的日程安排',
      quickAddReminder: '⏰ 添加提醒',
      quickAddReminderAction: '添加一个明天早上的提醒',
    },
    // Common
    common: {
      login: '登录',
      logout: '退出',
      loginPrompt: '请登录',
      loginDesc: '使用您的 Google 账户登录以继续。',
      loginWithGoogle: '使用 Google 登录',
      loading: '加载中...',
      year: '年',
      month: '月',
    },
  },
};

// i18n helper functions
const i18n = {
  currentLang: localStorage.getItem('language') || 'zh',

  t(key) {
    const keys = key.split('.');
    let value = translations[this.currentLang];
    for (const k of keys) {
      if (value && value[k] !== undefined) {
        value = value[k];
      } else {
        // Fallback to English
        value = translations['en'];
        for (const fallbackKey of keys) {
          if (value && value[fallbackKey] !== undefined) {
            value = value[fallbackKey];
          } else {
            return key; // Return key if not found
          }
        }
        break;
      }
    }
    return value;
  },

  setLanguage(lang) {
    if (translations[lang]) {
      this.currentLang = lang;
      localStorage.setItem('language', lang);
      // Dispatch event for React components to re-render
      window.dispatchEvent(new CustomEvent('languageChange', { detail: lang }));
    }
  },

  getLanguage() {
    return this.currentLang;
  },

  getAvailableLanguages() {
    return [
      { code: 'en', name: 'English' },
      { code: 'zh', name: '中文' },
    ];
  },
};

// React hook for using translations
const useTranslation = () => {
  const [lang, setLang] = React.useState(i18n.getLanguage());

  React.useEffect(() => {
    const handleLangChange = (e) => {
      setLang(e.detail);
    };
    window.addEventListener('languageChange', handleLangChange);
    return () => window.removeEventListener('languageChange', handleLangChange);
  }, []);

  return {
    t: (key) => i18n.t(key),
    lang,
    setLanguage: (newLang) => i18n.setLanguage(newLang),
    languages: i18n.getAvailableLanguages(),
  };
};

// Expose globally
window.i18n = i18n;
window.useTranslation = useTranslation;
window.translations = translations;
