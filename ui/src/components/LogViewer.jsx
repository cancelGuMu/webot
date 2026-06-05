import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import { ArrowDown, Trash } from '@phosphor-icons/react'

const LEVEL_STYLES = {
  DEBUG: { color: '#B8B8B6', bg: 'transparent' },
  INFO:  { color: '#5F5F5C', bg: 'transparent' },
  WARNING: { color: '#956400', bg: '#FBF3DB' },
  ERROR:  { color: '#9F2F2D', bg: '#FDEBEC' },
}
const LEVEL_LABELS = { ALL: '全部', INFO: 'INFO', WARNING: '警告', ERROR: '错误', DEBUG: 'DEBUG' }
const FILTER_OPTIONS = ['ALL', 'INFO', 'WARNING', 'ERROR', 'DEBUG']

export default function LogViewer() {
  const [filter, setFilter] = useState('ALL')
  const [logs, setLogs] = useState([])
  const scrollRef = useRef(null)
  const seenRef = useRef(new Set())
  // Track whether the user has scrolled up — only auto-scroll when
  // they're near the bottom of the log view.
  const [autoScroll, setAutoScroll] = useState(true)
  const SCROLL_THRESHOLD = 50  // px from bottom considered "at bottom"

  const filtered = filter === 'ALL' ? logs : logs.filter(l => l.level === filter)

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch('http://127.0.0.1:7327/api/logs')
      const data = await res.json()
      if (data.ok && data.logs?.length) {
        setLogs(prev => {
          // Dedupe by raw line content and only append new entries
          const merged = [...prev]
          for (const entry of data.logs) {
            const key = entry.raw
            if (!seenRef.current.has(key)) {
              seenRef.current.add(key)
              merged.push(entry)
            }
          }
          // Keep at most 2000 entries in memory
          return merged.length > 2000 ? merged.slice(-2000) : merged
        })
      }
    } catch {
      // silently retry on next poll
    }
  }, [])

  // Poll for new logs every 2 seconds
  useEffect(() => {
    fetchLogs()
    const timer = setInterval(fetchLogs, 2000)
    return () => clearInterval(timer)
  }, [fetchLogs])

  // Detect manual scroll to pause/resume auto-scroll
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

  // Auto-scroll only when user hasn't scrolled up
  useEffect(() => {
    if (autoScroll) {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    }
  }, [logs, autoScroll])

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 bg-white border border-[#EAEAEA] rounded-lg p-1">
          {FILTER_OPTIONS.map(level => (
            <button
              key={level}
              onClick={() => setFilter(level)}
              className={`px-3.5 py-1.5 rounded-md text-xs font-medium transition-all ${
                filter === level ? 'bg-[#F7F6F3] text-[#1F1F1F]' : 'text-[#B8B8B6] hover:text-[#5F5F5C]'
              }`}
            >
              {LEVEL_LABELS[level]}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <span className="text-xs text-[#B8B8B6] font-mono">{filtered.length} 条</span>
        <button onClick={scrollToBottom} className="p-2 rounded-md text-[#B8B8B6] hover:text-[#5F5F5C] hover:bg-[#F7F6F3] transition-colors">
          <ArrowDown size={16} />
        </button>
        <button onClick={() => { setLogs([]); seenRef.current.clear() }} className="p-2 rounded-md text-[#B8B8B6] hover:text-[#9F2F2D] hover:bg-[#FDEBEC] transition-colors">
          <Trash size={16} />
        </button>
      </div>

      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        ref={scrollRef}
        onScroll={handleScroll}
        className="bg-white border border-[#EAEAEA] rounded-xl overflow-hidden max-h-[600px] overflow-y-auto font-mono text-sm leading-relaxed"
      >
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-[#B8B8B6]">
            <p className="text-base">暂无日志</p>
            <p className="text-xs mt-2">启动机器人后，运行日志将实时显示在这里。</p>
            <p className="text-xs mt-1">日志文件位置: data/bot.log</p>
          </div>
        ) : (
          filtered.map((log, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i * 0.003, 0.2) }}
              className="flex items-center gap-4 px-6 py-2.5 border-b border-[#F0F0EE] last:border-0 hover:bg-[#F9F9F8] transition-colors"
            >
              <span className="text-[#B8B8B6] shrink-0" style={{ width: 70 }}>{log.ts}</span>
              <span
                className="shrink-0 font-semibold rounded text-center text-xs inline-flex items-center justify-center"
                style={{
                  width: 72,
                  height: 24,
                  color: LEVEL_STYLES[log.level].color,
                  backgroundColor: LEVEL_STYLES[log.level].bg,
                }}
              >
{log.level}
              </span>
              <span className="text-[#5F5F5C] break-all">{log.msg}</span>
            </motion.div>
          ))
        )}
      </motion.div>
    </div>
  )
}
