import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MagnifyingGlass, CheckCircle, Trash, ArrowUUpLeft, X, ListChecks, FloppyDisk, Info, Warning } from '@phosphor-icons/react'
import { Toggle, Input, Field } from './SharedComponents'

const API = 'http://127.0.0.1:7327'

const tabTransition = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

const configPanel = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, y: 20, transition: { duration: 0.2 } },
}

function ParamRow({ label, hint, children }) {
  return (
    <div>
      <p className="text-[14px] text-text-main font-medium">{label}</p>
      <p className="text-xs text-text-muted mt-0.5 mb-2">{hint}</p>
      {children}
    </div>
  )
}

function KeywordChips({ keywords, update, minItems = 1 }) {
  const [inputValue, setInputValue] = useState('')

  function addKeyword() {
    const val = inputValue.trim()
    if (val && !keywords.includes(val)) {
      update([...keywords, val])
      setInputValue('')
    }
  }

  function handleKeyDown(e) {
    if (e.key !== 'Enter') return
    if (e.nativeEvent.isComposing) return  // 中文输入法组合输入中，跳过
    e.preventDefault()
    addKeyword()
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {(keywords || []).map((kw, i) => (
          <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
            {kw}
            <button type="button" disabled={keywords.length <= minItems}
              onClick={() => { const next = keywords.filter((_, idx) => idx !== i); update(next) }}
              className={`ml-0.5 leading-none text-base transition-colors ${keywords.length <= minItems ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input type="text" value={inputValue} onChange={e => setInputValue(e.target.value)}
          placeholder="输入新触发词，回车添加"
          className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
          onKeyDown={handleKeyDown} />
        <button type="button" onClick={addKeyword}
          className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">添加</button>
      </div>
    </div>
  )
}

export default function TodoManager() {
  // ── Todo config state ──────────────────────────────────────────
  const [configLoaded, setConfigLoaded] = useState(false)
  const [configSaved, setConfigSaved] = useState(false)
  const [configSaveError, setConfigSaveError] = useState('')
  const [todoEnabled, setTodoEnabled] = useState(true)
  const [todoGroups, setTodoGroups] = useState(['*'])
  const [todoMaxPerGroup, setTodoMaxPerGroup] = useState(50)
  const [todoCompletedRetention, setTodoCompletedRetention] = useState(30)
  const [todoDeletedRetention, setTodoDeletedRetention] = useState(30)
  const [todoAddKeywords, setTodoAddKeywords] = useState(['记一下', '添加待办', '新建待办', '帮我记', '待办'])
  const [todoCompleteKeywords, setTodoCompleteKeywords] = useState(['搞定', '做完了', '完成', '完成了', 'done'])
  const [todoDeleteKeywords, setTodoDeleteKeywords] = useState(['删掉', '删除', '取消', '不要了'])

  // ── Todo management state ──────────────────────────────────────
  const [activeTab, setActiveTab] = useState('active')
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [availableGroups, setAvailableGroups] = useState([])  // {chat_id, group_name, member_count}[]

  // ── Load todo config on mount ─────────────────────────────────
  useEffect(() => {
    async function loadConfig() {
      try {
        const res = await fetch(`${API}/api/load-config`)
        const data = await res.json()
        if (data.ok && data.config) {
          const c = data.config
          if (typeof c.todo_enabled === 'boolean') setTodoEnabled(c.todo_enabled)
          if (c.todo_groups) setTodoGroups(Array.isArray(c.todo_groups) ? c.todo_groups : ['*'])
          if (c.todo_max_per_group != null) setTodoMaxPerGroup(c.todo_max_per_group)
          if (c.todo_completed_retention_days != null) setTodoCompletedRetention(c.todo_completed_retention_days)
          if (c.todo_deleted_retention_days != null) setTodoDeletedRetention(c.todo_deleted_retention_days)
          if (c.todo_add_keywords) setTodoAddKeywords(Array.isArray(c.todo_add_keywords) ? c.todo_add_keywords : String(c.todo_add_keywords).split(','))
          if (c.todo_complete_keywords) setTodoCompleteKeywords(Array.isArray(c.todo_complete_keywords) ? c.todo_complete_keywords : String(c.todo_complete_keywords).split(','))
          if (c.todo_delete_keywords) setTodoDeleteKeywords(Array.isArray(c.todo_delete_keywords) ? c.todo_delete_keywords : String(c.todo_delete_keywords).split(','))
        }
      } catch {}
      setConfigLoaded(true)
    }
    loadConfig()
  }, [])

  // ── Load available groups for dropdown ──────────────────────────
  useEffect(() => {
    async function loadGroups() {
      try {
        const res = await fetch(`${API}/api/nicknames/groups`)
        const data = await res.json()
        if (data.ok) setAvailableGroups(data.groups || [])
      } catch {}
    }
    loadGroups()
  }, [])

  // ── Save todo config ──────────────────────────────────────────
  async function handleSaveConfig() {
    setConfigSaved(false)
    setConfigSaveError('')
    try {
      const res = await fetch(`${API}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          todo_enabled: todoEnabled,
          todo_groups: todoGroups,
          todo_max_per_group: todoMaxPerGroup,
          todo_completed_retention_days: todoCompletedRetention,
          todo_deleted_retention_days: todoDeletedRetention,
          todo_add_keywords: todoAddKeywords,
          todo_complete_keywords: todoCompleteKeywords,
          todo_delete_keywords: todoDeleteKeywords,
        }),
      })
      const data = await res.json()
      if (data.ok) { setConfigSaved(true); setTimeout(() => setConfigSaved(false), 3000) }
      else { setConfigSaveError(data.error || '保存失败'); setTimeout(() => setConfigSaveError(''), 5000) }
    } catch { setConfigSaveError('无法连接到服务器，请确认机器人已启动'); setTimeout(() => setConfigSaveError(''), 5000) }
  }

  function addGroup(chatId) {
    if (!chatId) return
    if (todoGroups.includes('*')) {
      setTodoGroups([chatId])
    } else if (!todoGroups.includes(chatId)) {
      setTodoGroups([...todoGroups, chatId])
    }
  }
  function removeGroup(index) {
    const next = todoGroups.filter((_, i) => i !== index)
    setTodoGroups(next.length === 0 ? ['*'] : next)
  }

  // ── Todo management ────────────────────────────────────────────

  useEffect(() => { loadData() }, [activeTab, selectedGroup])

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({ status: activeTab })
      if (selectedGroup) params.set('chat_id', selectedGroup)
      const res = await fetch(`${API}/api/todos?${params}`)
      const d = await res.json()
      if (d.ok) {
        setItems(d.items || [])
        setGroups(d.groups || [])
      } else {
        setError(d.error || '加载失败')
      }
    } catch { setError('无法连接到服务器，请确认机器人已启动') }
    setLoading(false)
  }

  async function doAction(action, chatId, target) {
    setActionMsg('')
    try {
      const res = await fetch(`${API}/api/todos/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, chat_id: chatId, target: String(target) }),
      })
      const d = await res.json()
      if (d.ok) {
        setActionMsg(d.reply || '操作成功')
        setTimeout(() => setActionMsg(''), 3000)
        loadData()
      } else {
        setActionMsg(d.reply || d.error || '操作失败')
        setTimeout(() => setActionMsg(''), 5000)
      }
    } catch {
      setActionMsg('网络错误')
      setTimeout(() => setActionMsg(''), 5000)
    }
  }

  const filtered = items.filter(item =>
    !search || item.content.toLowerCase().includes(search.toLowerCase())
  )

  const managementTabs = [
    { id: 'active', label: '群聊待办' },
    { id: 'deleted', label: '已删除' },
    { id: 'completed', label: '已完成' },
  ]

  return (
    <div className="max-w-3xl">
      {/* ================================================================ */}
      {/* Part (a): Todo Feature Toggle + Configuration                    */}
      {/* ================================================================ */}
      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none p-7 mb-8">
        <div className="flex items-center gap-2.5 mb-5 pl-1">
          <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: '#e8794b' }} />
          <h3 className="text-sm font-semibold tracking-tight text-text-main">功能开关与配置</h3>
        </div>

        {/* Toggle row */}
        <div className="flex items-center justify-between mb-5">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">群聊待办</p>
            <p className="text-sm text-text-muted mt-1.5">@机器人发送触发词，管理群聊待办事项。支持添加、完成、删除、恢复。</p>
          </div>
          <Toggle enabled={todoEnabled} onChange={v => setTodoEnabled(v)} />
        </div>

        <AnimatePresence>
          {todoEnabled && (
            <motion.div variants={configPanel} initial="initial" animate="animate" exit="exit"
              className="p-4 bg-bg-raised rounded-lg space-y-5">

              {/* 生效群聊范围 */}
              <div>
                <p className="text-[14px] text-text-main font-medium">生效群聊范围</p>
                <p className="text-xs text-text-muted mt-0.5 mb-2">选择哪些群聊启用待办功能，未选中的群不响应待办命令</p>
                <div className="flex flex-wrap gap-2 mb-2">
                  {(todoGroups || []).map((g, i) => {
                    const info = availableGroups.find(ag => ag.chat_id === g)
                    const label = g === '*' ? '全部群聊' : (info?.group_name || g)
                    return (
                      <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                        {label}
                        <button type="button"
                          onClick={() => removeGroup(i)}
                          disabled={todoGroups.length === 1 && todoGroups[0] === '*'}
                          className={`ml-0.5 leading-none text-base transition-colors ${(todoGroups.length === 1 && todoGroups[0] === '*') ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
                      </span>
                    )
                  })}
                </div>
                <select value=""
                  onChange={e => { if (e.target.value) { addGroup(e.target.value); e.target.value = '' } }}
                  className="w-full bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all cursor-pointer">
                  <option value="">{availableGroups.length === 0 ? '加载群聊列表...' : '选择群聊...'}</option>
                  {availableGroups.filter(ag => !todoGroups.includes(ag.chat_id)).map(ag => (
                    <option key={ag.chat_id} value={ag.chat_id}>
                      {ag.group_name} — {ag.member_count}人
                    </option>
                  ))}
                </select>
              </div>

              {/* 参数设置 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <ParamRow label="每群待办上限" hint="单个群最多待办数（1-200）">
                  <Input type="number" value={String(todoMaxPerGroup)}
                    onChange={v => setTodoMaxPerGroup(Math.max(1, Math.min(200, parseInt(v) || 50)))} />
                </ParamRow>
                <ParamRow label="已完成保留天数" hint="超期自动清理（0=永久）">
                  <Input type="number" value={String(todoCompletedRetention)}
                    onChange={v => setTodoCompletedRetention(Math.max(0, parseInt(v) || 0))} />
                </ParamRow>
                <ParamRow label="已删除保留天数" hint="超期自动清理（0=永久）">
                  <Input type="number" value={String(todoDeletedRetention)}
                    onChange={v => setTodoDeletedRetention(Math.max(0, parseInt(v) || 0))} />
                </ParamRow>
              </div>

              {/* 添加待办触发词 */}
              <div>
                <p className="text-[14px] text-text-main font-medium">添加待办触发词</p>
                <p className="text-xs text-text-muted mt-0.5 mb-2">群成员 @机器人后发送触发词 + 待办内容，即可添加</p>
                <KeywordChips keywords={todoAddKeywords} update={setTodoAddKeywords} />
              </div>

              {/* 完成待办触发词 */}
              <div>
                <p className="text-[14px] text-text-main font-medium">完成待办触发词</p>
                <p className="text-xs text-text-muted mt-0.5 mb-2">群成员 @机器人后发送触发词 + 编号，即可标记完成</p>
                <KeywordChips keywords={todoCompleteKeywords} update={setTodoCompleteKeywords} />
              </div>

              {/* 删除待办触发词 */}
              <div>
                <p className="text-[14px] text-text-main font-medium">删除待办触发词</p>
                <p className="text-xs text-text-muted mt-0.5 mb-2">群成员 @机器人后发送触发词 + 编号，即可移至已删除</p>
                <KeywordChips keywords={todoDeleteKeywords} update={setTodoDeleteKeywords} />
              </div>

              {/* 使用提示 */}
              <div className="p-3 bg-bg-main/60 border border-border-main rounded-xl">
                <p className="text-xs text-text-muted leading-relaxed">
                  💡 <strong>群内使用提示：</strong><br />
                  @机器人 <code>查看待办</code> · <code>记一下 xxx</code> · <code>搞定 N</code>
                  · <code>删掉 N</code> · <code>恢复待办 N</code>（管理员）<br />
                  <span className="text-text-muted/60">查看待办、已完成列表、已删除列表、清空等命令为固定触发词，无需配置。</span>
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Save button + messages */}
        <div className="mt-6 flex items-center gap-4">
          <AnimatePresence>
            {configSaved && (
              <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                className="flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm">
                <CheckCircle size={18} weight="fill" /> 配置已保存。需要重启机器人才能生效。
              </motion.div>
            )}
            {configSaveError && (
              <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                className="flex items-center gap-2 px-5 py-2.5 bg-[#d45656]/5 border border-[#d45656]/20 rounded-full text-sm text-[#d45656] font-medium shadow-sm">
                <Warning size={18} weight="fill" /> {configSaveError}
              </motion.div>
            )}
          </AnimatePresence>
          {!configSaved && !configSaveError && (
            <motion.button whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }} onClick={handleSaveConfig}
              className="w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide shadow-sm transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] border border-[#0d0d0d] dark:border-border-main hover:opacity-90">
              <FloppyDisk size={18} /> 保存配置
            </motion.button>
          )}
          {configSaved && (
            <span className="flex items-center gap-1.5 text-xs text-[#c37d0d] bg-[#c37d0d]/10 border border-[#c37d0d]/20 px-4 py-1.5 rounded-full font-medium">
              <Info size={14} /> 配置已更新，重启机器人后生效
            </span>
          )}
        </div>
      </div>

      {/* ================================================================ */}
      {/* Part (b): Todo List Management                                   */}
      {/* ================================================================ */}
      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none p-7">
        <div className="flex items-center gap-2.5 mb-5 pl-1">
          <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: '#18E299' }} />
          <h3 className="text-sm font-semibold tracking-tight text-text-main">待办管理</h3>
        </div>

        {/* Action message toast */}
        <AnimatePresence>
          {actionMsg && (
            <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm">
              <CheckCircle size={18} weight="fill" /> {actionMsg}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search + Group filter */}
        <div className="flex items-center gap-3 mb-5">
          <div className="flex-1 relative">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="搜索待办内容..."
              className="w-full bg-bg-card border border-border-main rounded-xl pl-9 pr-4 py-2.5 text-[14px] text-text-main placeholder:text-text-muted/60 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all" />
          </div>
          <select value={selectedGroup} onChange={e => setSelectedGroup(e.target.value)}
            className="bg-bg-card border border-border-main rounded-xl px-3 py-2.5 text-[14px] text-text-main focus:outline-none focus:border-brand-green cursor-pointer">
            <option value="">全部群聊</option>
            {groups.map(g => (
              <option key={g} value={g}>{g.length > 20 ? g.slice(0, 20) + '...' : g}</option>
            ))}
          </select>
        </div>

        {/* Tab switcher */}
        <div className="flex gap-1 mb-5 bg-bg-card border border-border-main rounded-xl p-1 w-fit">
          {managementTabs.map(tab => {
            const active = activeTab === tab.id
            const count = tab.id === 'active' ? items.length : (activeTab === tab.id ? items.length : null)
            return (
              <button key={tab.id} onClick={() => { setActiveTab(tab.id); setSearch('') }}
                className={`relative px-4 py-2 rounded-lg text-[13px] font-medium transition-all cursor-pointer ${
                  active ? 'text-brand-green-hover dark:text-brand-green' : 'text-text-muted hover:text-text-main'
                }`}>
                {active && (
                  <motion.div layoutId="todoMgmtTabBg" className="absolute inset-0 bg-brand-green-light rounded-lg"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }} />
                )}
                <span className="relative z-10">
                  {tab.label}
                  {count !== null && <span className="ml-1.5 text-[11px] opacity-60">({count})</span>}
                </span>
              </button>
            )
          })}
        </div>

        {/* Content area */}
        <div style={{ minHeight: 300 }}>
          <AnimatePresence mode="wait">
            {loading ? (
              <motion.div key="loading" variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="flex items-center justify-center py-20">
                <svg className="animate-spin h-5 w-5 text-brand-green" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </motion.div>
            ) : error ? (
              <motion.div key="error" variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="text-center py-20">
                <p className="text-sm text-[#d45656]">{error}</p>
              </motion.div>
            ) : filtered.length === 0 ? (
              <motion.div key="empty" variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="text-center py-20">
                <ListChecks size={40} className="mx-auto mb-3 text-text-muted/40" />
                <p className="text-sm text-text-muted">
                  {activeTab === 'active' ? '暂无待办事项。@机器人说"记一下 xxx"即可添加' :
                   activeTab === 'deleted' ? '暂无已删除事项' : '暂无已完成事项'}
                </p>
              </motion.div>
            ) : (
              <motion.div key={`${activeTab}-${filtered.length}`} variants={tabTransition} initial="initial" animate="animate" exit="exit"
                className="space-y-3">
                {filtered.map(item => (
                  <div key={item.id}
                    className="bg-bg-card border border-border-main rounded-2xl shadow-sm p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[11px] font-mono text-text-muted bg-bg-raised border border-border-main px-2 py-0.5 rounded-full">
                            #{item.display_order}
                          </span>
                          {!selectedGroup && item.chat_id && (
                            <span className="text-[11px] text-text-muted/60 truncate max-w-[160px]">
                              {item.chat_id.length > 20 ? item.chat_id.slice(0, 20) + '...' : item.chat_id}
                            </span>
                          )}
                        </div>
                        <p className="text-[15px] text-text-main">{item.content}</p>
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-text-muted">
                          {item.creator_name && <span>创建者: @{item.creator_name}</span>}
                          {item.created_at > 0 && (
                            <span>创建时间: {new Date(item.created_at * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                          )}
                          {item.completed_by_name && <span>完成者: @{item.completed_by_name}</span>}
                          {item.completed_at > 0 && (
                            <span>完成时间: {new Date(item.completed_at * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                          )}
                          {item.deleted_by_name && <span>删除者: @{item.deleted_by_name}</span>}
                          {item.deleted_at > 0 && (
                            <span>删除时间: {new Date(item.deleted_at * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                          )}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        {activeTab === 'active' && (
                          <>
                            <button onClick={() => doAction('complete', item.chat_id, String(item.display_order))}
                              className="px-3 py-1.5 text-[12px] bg-brand-green-light border border-brand-green/20 rounded-lg text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <CheckCircle size={14} /> 完成
                            </button>
                            <button onClick={() => doAction('delete', item.chat_id, String(item.display_order))}
                              className="px-3 py-1.5 text-[12px] bg-bg-raised border border-border-main rounded-lg text-text-muted hover:text-[#d45656] hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <Trash size={14} /> 删除
                            </button>
                          </>
                        )}
                        {activeTab === 'deleted' && (
                          <>
                            <button onClick={() => doAction('restore', item.chat_id, String(item.display_order))}
                              className="px-3 py-1.5 text-[12px] bg-brand-green-light border border-brand-green/20 rounded-lg text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <ArrowUUpLeft size={14} /> 恢复
                            </button>
                            <button onClick={() => doAction('clear_deleted', item.chat_id, '')}
                              className="px-3 py-1.5 text-[12px] bg-bg-raised border border-border-main rounded-lg text-text-muted hover:text-[#d45656] hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium flex items-center gap-1">
                              <X size={14} /> 彻底删除
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Clear all button for completed tab */}
                {activeTab === 'completed' && filtered.length > 0 && (
                  <div className="pt-2">
                    <button onClick={() => {
                      const cid = selectedGroup || (filtered[0]?.chat_id || '')
                      doAction('clear_completed', cid, '')
                    }}
                      className="px-4 py-2 text-[12px] bg-bg-raised border border-border-main rounded-lg text-text-muted hover:text-[#d45656] hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium flex items-center gap-1.5">
                      <Trash size={14} /> 清空已完成
                    </button>
                  </div>
                )}

                {/* Footer */}
                <div className="pt-2 text-xs text-text-muted/60">
                  共 {filtered.length} 项
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
