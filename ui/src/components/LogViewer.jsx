import { useState, useEffect, useRef } from 'react'
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

const MOCK_LOGS = [
  { ts: '12:01:03', level: 'INFO', msg: 'WcdbBackend 正在启动 (groups=*, poll=1.0s)' },
  { ts: '12:01:03', level: 'INFO', msg: 'WCDB 引擎初始化完成 (DRM 补丁已应用)' },
  { ts: '12:01:04', level: 'INFO', msg: '数据库已打开: session.db' },
  { ts: '12:01:04', level: 'INFO', msg: '自动发现 7 个群聊' },
  { ts: '12:01:05', level: 'INFO', msg: '机器人已启动，按 Ctrl+C 停止' },
  { ts: '12:01:35', level: 'INFO', msg: '回复已发送: 群="技术交流" (47 字)' },
  { ts: '12:02:10', level: 'DEBUG', msg: '回调耗时 0.35s (msg_id=a3f2, 群="技术交流")' },
  { ts: '12:02:45', level: 'WARNING', msg: '发送确认超时(3s): 群="摸鱼群"' },
  { ts: '12:03:00', level: 'INFO', msg: '心跳: uptime=2m, msgs=15, db=正常' },
  { ts: '12:04:22', level: 'ERROR', msg: 'AI 对话失败: 网络连接错误' },
  { ts: '12:04:23', level: 'INFO', msg: '回复已发送: 群="技术交流" (32 字)' },
]

export default function LogViewer() {
  const [filter, setFilter] = useState('ALL')
  const [logs, setLogs] = useState(MOCK_LOGS)
  const scrollRef = useRef(null)

  const filtered = filter === 'ALL' ? logs : logs.filter(l => l.level === filter)

  function scrollToBottom() {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }
  useEffect(() => { scrollToBottom() }, [logs])

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
        <button onClick={() => setLogs([])} className="p-2 rounded-md text-[#B8B8B6] hover:text-[#9F2F2D] hover:bg-[#FDEBEC] transition-colors">
          <Trash size={16} />
        </button>
      </div>

      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
        ref={scrollRef}
        className="bg-white border border-[#EAEAEA] rounded-xl overflow-hidden max-h-[600px] overflow-y-auto font-mono text-sm leading-relaxed"
      >
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-[#B8B8B6]">
            <p className="text-base">暂无日志</p>
            <p className="text-xs mt-2">启动机器人后日志会显示在这里</p>
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
