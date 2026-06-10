import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { MagnifyingGlass, CheckCircle, Trash, ArrowUUpLeft, X, ListChecks } from '@phosphor-icons/react'

const API = 'http://127.0.0.1:7327'

const tabTransition = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

export default function TodoManager() {
  const [activeTab, setActiveTab] = useState('active')
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')

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

  const tabs = [
    { id: 'active', label: '群聊待办' },
    { id: 'deleted', label: '已删除' },
    { id: 'completed', label: '已完成' },
  ]

  return (
    <div className="max-w-3xl">
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
        {tabs.map(tab => {
          const active = activeTab === tab.id
          const count = tab.id === 'active' ? items.length : (activeTab === tab.id ? items.length : null)
          return (
            <button key={tab.id} onClick={() => { setActiveTab(tab.id); setSearch('') }}
              className={`relative px-4 py-2 rounded-lg text-[13px] font-medium transition-all cursor-pointer ${
                active ? 'text-brand-green-hover dark:text-brand-green' : 'text-text-muted hover:text-text-main'
              }`}>
              {active && (
                <motion.div layoutId="todoTabBg" className="absolute inset-0 bg-brand-green-light rounded-lg"
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
  )
}
