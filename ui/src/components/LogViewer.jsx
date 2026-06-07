import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import { ArrowDown, Trash, MagnifyingGlass } from '@phosphor-icons/react'

const LEVEL_STYLES = {
  DEBUG:   { color: '#888888', bg: 'rgba(136, 136, 136, 0.12)' },
  INFO:    { color: '#3772cf', bg: 'rgba(55, 114, 207, 0.12)' },
  WARNING: { color: '#c37d0d', bg: 'rgba(195, 125, 13, 0.12)' },
  ERROR:   { color: '#d45656', bg: 'rgba(212, 86, 86, 0.12)' },
}
const LEVEL_LABELS = { ALL: '全部', INFO: 'INFO', WARNING: '警告', ERROR: '错误', DEBUG: 'DEBUG' }
const FILTER_OPTIONS = ['ALL', 'INFO', 'WARNING', 'ERROR', 'DEBUG']

function renderHighlightedMsg(msg) {
  if (!msg) return ''
  const regex = /(\[[^\]]+\]|收到消息|发送消息|\b\d+(?:\.\d+)?(?:ms|s|毫秒|秒)\b|\b(?:OK|SUCCESS|ERROR)\b|成功|失败)/g
  const parts = msg.split(regex)
  if (parts.length === 1) return <span>{msg}</span>

  return (
    <span>
      {parts.map((part, i) => {
        if (!part) return null
        if (part.startsWith('[') && part.endsWith(']')) {
          return (
            <span key={i} className="px-1.5 py-0.5 rounded-full bg-blue-500/10 text-[#3772cf] border border-blue-500/20 text-[11px] font-semibold font-mono mx-0.5">
              {part}
            </span>
          )
        }
        if (part === '收到消息' || part === '发送消息') {
          const isRecv = part === '收到消息'
          return (
            <span key={i} className={`px-1.5 py-0.5 rounded-full text-[11px] font-semibold font-mono mx-0.5 ${isRecv ? 'bg-[#18E299]/10 text-[#18E299] border border-[#18E299]/20' : 'bg-amber-500/10 text-[#c37d0d] border border-amber-500/20'}`}>
              {part}
            </span>
          )
        }
        if (/^\d+(?:\.\d+)?(?:ms|s|毫秒|秒)$/.test(part)) {
          return (
            <span key={i} className="px-1.5 py-0.5 rounded-full bg-bg-main/60 dark:bg-white/5 border border-border-main dark:border-white/10 text-text-main dark:text-zinc-300 text-[11px] font-semibold font-mono mx-0.5">
              {part}
            </span>
          )
        }
        if (part === '成功' || part === 'OK' || part === 'SUCCESS') {
          return (
            <span key={i} className="text-[#18E299] font-semibold font-mono mx-0.5">
              {part}
            </span>
          )
        }
        if (part === '失败' || part === 'ERROR') {
          return (
            <span key={i} className="text-[#d45656] font-semibold font-mono mx-0.5">
              {part}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </span>
  )
}

export default function LogViewer() {
  const [filter, setFilter] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')
  const [logs, setLogs] = useState([])
  const [clearedManually, setClearedManually] = useState(false)
  const scrollRef = useRef(null)
  const seenRef = useRef(new Set())
  const [autoScroll, setAutoScroll] = useState(true)
  const SCROLL_THRESHOLD = 50  // px from bottom considered "at bottom"

  const filtered = logs.filter(l => {
    const matchesLevel = filter === 'ALL' || l.level === filter
    const matchesSearch = !searchQuery ||
      l.msg.toLowerCase().includes(searchQuery.toLowerCase()) ||
      l.ts.toLowerCase().includes(searchQuery.toLowerCase()) ||
      l.level.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesLevel && matchesSearch
  })

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch('http://127.0.0.1:7327/api/logs')
      const data = await res.json()
      if (data.ok && data.logs?.length) {
        setLogs(prev => {
          const merged = [...prev]
          let added = false
          for (const entry of data.logs) {
            const key = entry.raw
            if (!seenRef.current.has(key)) {
              seenRef.current.add(key)
              merged.push(entry)
              added = true
            }
          }
          if (added) {
            setClearedManually(false)
          }
          return merged.length > 2000 ? merged.slice(-2000) : merged
        })
      }
    } catch {}
  }, [])

  useEffect(() => {
    fetchLogs()
    const timer = setInterval(fetchLogs, 2000)
    return () => clearInterval(timer)
  }, [fetchLogs])

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setAutoScroll(distFromBottom < SCROLL_THRESHOLD)
  }

  function scrollToBottom() {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    setAutoScroll(true)
  }

  useEffect(() => {
    if (autoScroll) {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    }
  }, [logs, autoScroll])

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-1 bg-bg-card border border-border-main rounded-full p-1 shrink-0">
          {FILTER_OPTIONS.map(level => (
            <button
              key={level}
              onClick={() => setFilter(level)}
              className={`px-3 py-1.25 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                filter === level
                  ? 'bg-bg-raised text-text-main font-semibold shadow-sm'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              {LEVEL_LABELS[level]}
            </button>
          ))}
        </div>

        {/* Log Search Input */}
        <div className="relative flex-1 max-w-sm">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-muted/60">
            <MagnifyingGlass size={14} />
          </span>
          <input
            type="text"
            placeholder="搜索日志关键字、事件、耗时..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-8 py-1.5 bg-bg-card border border-border-main rounded-full text-xs placeholder:text-text-muted/50 focus:outline-none focus:border-brand-green/60 text-text-main transition-all font-mono"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-text-muted/50 hover:text-[#d45656] text-[10px] font-sans font-semibold cursor-pointer"
            >
              清除
            </button>
          )}
        </div>

        <div className="flex-1 hidden sm:block" />
        <div className="flex items-center gap-2.5 ml-auto sm:ml-0 shrink-0">
          <span className="text-xs text-text-muted font-mono bg-bg-card border border-border-main px-3 py-1 rounded-full">{filtered.length} 条</span>
          <button onClick={scrollToBottom} title="滚动到底部" className="p-2 rounded-full text-text-muted hover:text-text-main hover:bg-bg-raised transition-colors cursor-pointer border border-transparent hover:border-border-main">
            <ArrowDown size={16} />
          </button>
          <button onClick={() => { setLogs([]); seenRef.current.clear(); setClearedManually(true) }} title="仅清空屏幕展示日志（不删除后台日志文件）" className="p-2 rounded-full text-text-muted hover:text-[#d45656] hover:bg-[#d45656]/10 border border-transparent hover:border-[#d45656]/20 transition-colors cursor-pointer">
            <Trash size={16} />
          </button>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        ref={scrollRef}
        onScroll={handleScroll}
        className="bg-bg-raised dark:bg-[#141414] border border-border-main rounded-2xl overflow-hidden max-h-[600px] overflow-y-auto font-mono text-[13px] leading-relaxed p-4 divide-y divide-border-main shadow-sm text-text-main"
      >
        {filtered.length === 0 ? (
          clearedManually ? (
            <div className="p-16 text-center text-text-muted">
              <p className="text-base font-semibold text-text-main font-mono">Terminal Cleared</p>
              <p className="text-xs mt-1.5 font-medium text-text-muted">等待新事件写入日志文件...</p>
            </div>
          ) : (
            <div className="p-16 text-center text-text-muted">
              <p className="text-base font-semibold text-text-main font-mono">Console Offline</p>
              <p className="text-xs mt-1.5 font-medium text-text-muted">启动机器人后，日志数据流将在此输出</p>
              <p className="text-xs mt-1 font-mono text-text-muted/65">位置: data/bot.log</p>
            </div>
          )
        ) : (
          filtered.map((log, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i * 0.003, 0.2) }}
              className="flex items-center gap-4 px-4 py-2 hover:bg-bg-main/50 dark:hover:bg-white/5 transition-colors border-0"
            >
              <span className="text-text-muted shrink-0 text-xs font-mono" style={{ width: 70 }}>{log.ts}</span>
              <span
                className="shrink-0 font-bold rounded-full text-center text-[10px] tracking-wider inline-flex items-center justify-center border font-mono uppercase"
                style={{
                  width: 68,
                  height: 20,
                  color: LEVEL_STYLES[log.level]?.color || '#888888',
                  backgroundColor: LEVEL_STYLES[log.level]?.bg || 'var(--bg-main)',
                  borderColor: LEVEL_STYLES[log.level]?.color ? `${LEVEL_STYLES[log.level].color}25` : 'var(--border-main)',
                }}
              >
                {log.level}
              </span>
              <span className="text-text-main break-all select-all font-mono">{renderHighlightedMsg(log.msg)}</span>
            </motion.div>
          ))
        )}
      </motion.div>
    </div>
  )
}
