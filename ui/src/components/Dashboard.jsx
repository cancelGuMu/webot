import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Database, Brain, Clock, ChatCircle, Pulse, Play, Stop, Key, Spinner, CheckCircle, XCircle } from '@phosphor-icons/react'

const spring = { type: 'spring', stiffness: 100, damping: 20 }

function generateSmoothPath(data, width = 120, height = 30) {
  if (!data || data.length === 0) return ''
  const max = Math.max(...data, 4)
  const points = data.map((val, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - 2 - (val / max) * (height - 6)
    return { x, y }
  })

  let d = `M ${points[0].x} ${points[0].y}`
  for (let i = 0; i < points.length - 1; i++) {
    const curr = points[i]
    const next = points[i + 1]
    const cpX1 = curr.x + (next.x - curr.x) / 2
    const cpY1 = curr.y
    const cpX2 = curr.x + (next.x - curr.x) / 2
    const cpY2 = next.y
    d += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${next.x} ${next.y}`
  }
  return d
}

function MetricCard({ icon: Icon, label, value, sub, accent = 'green', chartData }) {
  const accents = {
    green: 'bg-brand-green-light text-brand-green-hover border-brand-green/20 dark:bg-brand-green/10 dark:text-brand-green dark:border-brand-green/20',
    blue: 'bg-blue-500/10 text-[#3772cf] border-blue-500/20',
    amber: 'bg-amber-500/10 text-[#c37d0d] border-amber-500/20',
    rose: 'bg-rose-500/10 text-[#d45656] border-rose-500/20',
  }
  const a = accents[accent]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
      whileHover={{ y: -2 }}
      className="bg-bg-card border border-border-main rounded-2xl p-6 transition-all duration-200 shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none hover:border-text-muted/30 dark:hover:border-text-muted/40 relative overflow-hidden flex flex-col justify-between"
      style={{ minHeight: 145 }}
    >
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center border shadow-sm ${a}`}>
            <Icon size={18} weight="fill" />
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-[12px] text-text-muted font-semibold font-mono uppercase tracking-[0.6px]">{label}</p>
          <p className="text-3xl font-bold tracking-tight font-mono text-text-main">{value}</p>
          {sub && <p className="text-[11px] text-text-muted/85 font-medium font-mono uppercase tracking-[0.3px]">{sub}</p>}
        </div>
      </div>

      {chartData && (
        <div className="absolute bottom-0 left-0 right-0 h-12 pointer-events-none select-none opacity-45 dark:opacity-30">
          <svg className="w-full h-full" viewBox="0 0 120 30" preserveAspectRatio="none">
            <defs>
              <linearGradient id={`grad-${accent}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={accent === 'green' ? '#18E299' : (accent === 'blue' ? '#3772cf' : (accent === 'amber' ? '#c37d0d' : '#d45656'))} stopOpacity="0.4" />
                <stop offset="100%" stopColor={accent === 'green' ? '#18E299' : (accent === 'blue' ? '#3772cf' : (accent === 'amber' ? '#c37d0d' : '#d45656'))} stopOpacity="0.0" />
              </linearGradient>
            </defs>
            <motion.path
              animate={{ d: `${generateSmoothPath(chartData)} L 120 30 L 0 30 Z` }}
              transition={{ type: 'spring', stiffness: 50, damping: 15 }}
              fill={`url(#grad-${accent})`}
            />
            <motion.path
              animate={{ d: generateSmoothPath(chartData) }}
              transition={{ type: 'spring', stiffness: 50, damping: 15 }}
              fill="none"
              stroke={accent === 'green' ? '#18E299' : (accent === 'blue' ? '#3772cf' : (accent === 'amber' ? '#c37d0d' : '#d45656'))}
              strokeWidth="1.5"
            />
          </svg>
        </div>
      )}
    </motion.div>
  )
}

function LiveIndicator({ label, ok }) {
  return (
    <motion.div
      whileHover={{ x: 2 }}
      className="flex items-center gap-3 py-3.5 border-b border-border-main/40 last:border-0 transition-colors"
    >
      <div className="relative flex-shrink-0">
        <div
          className={`w-2.5 h-2.5 rounded-full transition-colors duration-500 shadow-sm ${ok ? 'bg-brand-green shadow-brand-green/30' : 'bg-[#d45656] shadow-[#d45656]/30'}`}
        />
        {ok && (
          <motion.div
            animate={{ scale: [1, 2.2, 1], opacity: [0.4, 0, 0.4] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-brand-green"
          />
        )}
      </div>
      <span className="text-sm text-text-main font-medium flex-1">{label}</span>
      <span
        className={`text-[11px] font-semibold font-mono px-3.5 py-1 rounded-full border transition-all ${
          ok
            ? 'bg-brand-green-light text-brand-green-hover border-brand-green/20 dark:bg-brand-green/10 dark:text-brand-green dark:border-brand-green/20'
            : 'bg-[#d45656]/10 text-[#d45656] border-[#d45656]/20'
        }`}
      >
        {ok ? '正常' : '异常'}
      </span>
    </motion.div>
  )
}

const backendLabels = { wcdb: '本地数据库直读', direct: 'UIA 窗口读取' }
const aiLabels = { deepseek: 'DeepSeek', claude: 'Claude' }

export default function Dashboard({ status }) {
  const [busy, setBusy] = useState(false)
  const [, setTick] = useState(0)

  // Diagnostics state
  const [diagnosing, setDiagnosing] = useState(false)
  const [diagResult, setDiagResult] = useState(null)

  // Chart state arrays (rolling rate buffers of 10 points)
  const [msgHistory, setMsgHistory] = useState([2, 4, 3, 5, 4, 6, 3, 5, 4, 5])
  const [uptimeHistory, setUptimeHistory] = useState([10, 12, 15, 18, 20, 24, 28, 32, 35, 40])
  const [latencyHistory, setLatencyHistory] = useState([110, 125, 115, 130, 120, 118, 124, 115, 122, 128])

  const lastMsgCount = useRef(status.messages_processed)

  // 1-second heartbeat — drives real-time "X 秒前" display and charts updates
  useEffect(() => {
    const timer = setInterval(() => {
      setTick(t => t + 1)

      // Update charts every tick
      const currentCount = status.messages_processed
      const diff = Math.max(0, currentCount - lastMsgCount.current)
      lastMsgCount.current = currentCount

      setMsgHistory(prev => {
        const base = diff > 0 ? diff * 3 + 4 : Math.floor(Math.random() * 2) + 2
        return [...prev.slice(1), base]
      })

      setUptimeHistory(prev => {
        const lastVal = prev[prev.length - 1]
        const nextVal = status.running ? lastVal + 1 : Math.max(5, lastVal - 2)
        return [...prev.slice(1), nextVal]
      })

      setLatencyHistory(prev => {
        const base = status.running ? 115 + Math.floor(Math.random() * 15) : 5
        return [...prev.slice(1), base]
      })
    }, 1500)

    return () => clearInterval(timer)
  }, [status.messages_processed, status.running])

  async function handleToggle() {
    setBusy(true)
    try {
      const endpoint = status.running ? '/api/stop' : '/api/start'
      await fetch(`http://127.0.0.1:7327${endpoint}`, { method: 'POST' })
    } catch {}
    setTimeout(() => setBusy(false), 1000)  // debounce
  }

  async function triggerDiagnostics() {
    setDiagnosing(true)
    setDiagResult(null)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/onboarding/diagnose')
      const d = await res.json()
      if (d.ok) {
        const hasError = Object.values(d.diagnostics).some(item => !item.ok)
        setDiagResult({ error: hasError ? '检测到部分环境配置异常' : null })
      } else {
        setDiagResult({ error: d.error || '获取诊断失败' })
      }
    } catch {
      setDiagResult({ error: '诊断异常，无法访问后端' })
    }
    setTimeout(() => {
      setDiagnosing(false)
    }, 850)
  }

  const uptimeMin = Math.floor(status.uptime_sec / 60)
  const uptimeStr = uptimeMin < 60
    ? `${uptimeMin} 分钟`
    : `${Math.floor(uptimeMin / 60)} 小时 ${uptimeMin % 60} 分钟`

  const apiSecAgo = status.last_api_call_time > 0
    ? Math.floor(Date.now() / 1000 - status.last_api_call_time)
    : -1
  const lastApi = apiSecAgo > 0 ? `${apiSecAgo} 秒前` : '暂无调用'

  return (
    <div className="space-y-8 max-w-6xl">
      {/* Control bar */}
      <div className="flex items-center gap-4 bg-bg-card border border-border-main p-4 rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
        <motion.button
          whileTap={{ scale: 0.96 }}
          whileHover={{ scale: 1.02 }}
          onClick={handleToggle}
          disabled={busy}
          className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide shadow-sm transition-all duration-300 disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2 ${
            status.running
              ? 'bg-bg-raised text-text-main border border-border-main hover:bg-[#d45656]/10 hover:text-[#d45656] hover:border-[#d45656]/20'
              : 'bg-brand-green text-[#0d0d0d] hover:opacity-90'
          }`}
        >
          {status.running ? (
            <><Stop size={18} weight="fill" /> 停止机器人</>
          ) : (
            <><Play size={18} weight="fill" /> 启动机器人</>
          )}
        </motion.button>
        <span className="text-xs text-text-muted font-mono font-medium">
          {busy ? '处理中...' : (status.running ? '点击停止微信消息轮询' : '点击启动微信消息轮询')}
        </span>
      </div>

      {/* Error banner */}
      {status.error && !status.error.includes('KEY_MISSING') && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 px-5 py-4 bg-[#d45656]/5 border border-[#d45656]/20 rounded-2xl text-sm text-[#d45656] shadow-sm font-medium"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1L15 14H1L8 1Z" fill="currentColor"/><path d="M8 6V9" stroke="white" strokeWidth="1.5"/><circle cx="8" cy="11.5" r="0.75" fill="white"/></svg>
          <span>{status.error}</span>
        </motion.div>
      )}

      {/* KEY_MISSING banner with inline extraction */}
      {status.error && status.error.includes('KEY_MISSING') && (
        <KeyExtractionBanner />
      )}

      <div className="grid grid-cols-3 gap-6">
        <MetricCard icon={ChatCircle} accent="green" label="已处理消息" value={status.messages_processed.toLocaleString()} sub={status.running ? '机器人监控中' : '机器人已挂起'} chartData={msgHistory} />
        <MetricCard icon={Clock} accent="blue" label="运行时长" value={uptimeStr} sub={status.running ? '自本次启动' : '—'} chartData={uptimeHistory} />
        <MetricCard icon={Brain} accent="amber" label="最近 API 调用" value={lastApi} sub={`${aiLabels[status.ai_backend] || status.ai_backend || '—'} / ${backendLabels[status.wechat_backend] || status.wechat_backend || '—'}`} chartData={latencyHistory} />
      </div>

      <div className="grid grid-cols-5 gap-6">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.1 }} className="bg-bg-card border border-border-main rounded-2xl p-6 col-span-3 shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
          <div className="flex items-center justify-between mb-3 pb-3 border-b border-border-main/50">
            <div className="flex items-center gap-2">
              <Pulse size={16} weight="fill" className="text-brand-green animate-pulse" />
              <h3 className="text-sm font-semibold tracking-tight text-text-main">系统状态</h3>
            </div>
            <button
              onClick={triggerDiagnostics}
              disabled={diagnosing}
              title="一键诊断系统环境"
              className="p-1 rounded-full text-text-muted hover:text-brand-green hover:bg-brand-green-light/20 transition-all cursor-pointer disabled:opacity-50"
            >
              <svg
                className={`w-4 h-4 ${diagnosing ? 'animate-spin text-brand-green' : ''}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3m0 0l3 3m-3-3v12" />
              </svg>
            </button>
          </div>
          <div className="divide-y divide-border-main/40">
            <LiveIndicator label="数据库连接" ok={status.db_ok} />
            <LiveIndicator label="微信后端" ok={!!status.wechat_backend} />
            <LiveIndicator label="AI 后端" ok={!!status.ai_backend} />
            <LiveIndicator label="机器人进程" ok={status.running} />
          </div>
          {diagResult && (
            <div className="mt-3 text-xs flex justify-between items-center font-mono">
              <span className="text-text-muted">实时诊断反馈:</span>
              <span className={diagResult.error ? 'text-[#d45656] font-semibold' : 'text-brand-green font-semibold'}>
                {diagResult.error ? diagResult.error : '✓ 所有环境就绪'}
              </span>
            </div>
          )}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.15 }} className="bg-bg-card border border-border-main rounded-2xl p-6 col-span-2 shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
          <div className="flex items-center gap-2 mb-3 pb-3 border-b border-border-main/50">
            <Database size={16} weight="fill" className="text-text-muted" />
            <h3 className="text-sm font-semibold tracking-tight text-text-main">后端信息</h3>
          </div>
          <div className="space-y-4 pt-1">
            {[
              ['微信后端', backendLabels[status.wechat_backend] || status.wechat_backend || '—'],
              ['AI 后端', aiLabels[status.ai_backend] || status.ai_backend || '—'],
              ['日志文件', 'data/bot.log'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between items-center py-0.5">
                <span className="text-xs text-text-muted font-medium">{k}</span>
                <span className="text-xs font-mono text-text-main bg-bg-raised border border-border-main px-2.5 py-1 rounded-full">{v}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="text-[10px] text-text-muted font-mono uppercase tracking-[0.6px]">
        {status.timestamp ? `最近同步: ${status.timestamp}` : '等待首次状态更新...'}
      </motion.div>
    </div>
  )
}

// ── Inline key extraction banner ───────────────────────────────────────

const API = 'http://127.0.0.1:7327'
const EXTRACTION_PHASE_MAP = {
  hooking:         { label: '正在尝试直接获取...' },
  waiting_exit:    { label: '请退出微信' },
  waiting_login:   { label: '等待登录微信' },
  hooking_restart: { label: '正在安装 Hook...' },
}

function KeyExtractionBanner() {
  const [phase, setPhase] = useState('idle') // idle | extracting | hooking | waiting_exit | ...
  const [msg, setMsg] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const pollRef = useRef(null)

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  async function handleExtract() {
    setBusy(true)
    setPhase('extracting')
    setMsg('正在准备...')
    setResult(null)
    try {
      await fetch(`${API}/api/onboarding/reset`, { method: 'POST' })
      const startRes = await fetch(`${API}/api/onboarding/step1`, { method: 'POST' })
      const start = await startRes.json()
      if (!start.ok) {
        setPhase('error')
        setMsg(start.message || '启动失败，请稍后重试')
        setBusy(false)
        return
      }

      pollRef.current = setInterval(async () => {
        try {
          const res = await fetch(`${API}/api/onboarding/step1-status`)
          const s = await res.json()

          if (s.phase === 'waiting_exit' || s.phase === 'waiting_login'
              || s.phase === 'hooking' || s.phase === 'hooking_restart') {
            setPhase(s.phase)
            setMsg(s.message || '')
          } else if (s.phase === 'done' && s.result) {
            clearInterval(pollRef.current)
            pollRef.current = null
            setPhase('done')
            setMsg('')
            setResult(s.result)
            setBusy(false)
          } else if (s.phase === 'timeout' || s.phase === 'error') {
            clearInterval(pollRef.current)
            pollRef.current = null
            setPhase(s.phase)
            setMsg(s.message || (s.phase === 'timeout' ? '超时，请重试' : '提取失败'))
            setBusy(false)
          }
        } catch {}
      }, 1000)
    } catch {
      setPhase('error')
      setMsg('无法连接服务器')
      setBusy(false)
    }
  }

  const phaseMeta = EXTRACTION_PHASE_MAP[phase]
  const isDone = phase === 'done'

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex flex-col gap-4 p-6 rounded-2xl border transition-all duration-500 shadow-sm ${
        isDone
          ? 'bg-brand-green-light border-brand-green/20 text-brand-green-hover dark:text-brand-green'
          : 'bg-[#d45656]/5 border-[#d45656]/20 text-[#d45656]'
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-semibold">
        {isDone ? (
          <CheckCircle size={18} weight="fill" className="text-brand-green" />
        ) : (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1L15 14H1L8 1Z" fill="currentColor"/><path d="M8 6V9" stroke="white" strokeWidth="1.5"/><circle cx="8" cy="11.5" r="0.75" fill="white"/></svg>
        )}
        <span>{isDone ? '密钥获取成功 — 请重启机器人' : '加密密钥缺失 — 需要重新获取才能读取微信消息'}</span>
      </div>

      {phase !== 'idle' && phase !== 'done' && phase !== 'timeout' && phase !== 'error' && phaseMeta && (
        <motion.div initial={{opacity:0}} animate={{opacity:1}}
          className="flex items-center gap-3 p-4 rounded-2xl border border-blue-500/20 bg-blue-500/10">
          <Spinner size={20} weight="bold" className="animate-spin text-blue-600 dark:text-blue-400" />
          <div>
            <p className="text-sm font-semibold text-blue-800 dark:text-blue-400">{phaseMeta.label}</p>
            <p className="text-xs text-blue-600 dark:text-blue-400/80 mt-1 font-medium">{msg}</p>
          </div>
        </motion.div>
      )}

      {phase === 'done' && result && (
        <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}} className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-bg-raised border border-border-main rounded-2xl p-4 shadow-sm">
              <p className="text-xs text-text-muted mb-1 font-semibold">微信账号</p>
              <p className="text-sm font-mono text-text-main font-bold truncate">{result.wxid || '—'}</p>
            </div>
            <div className="bg-bg-raised border border-border-main rounded-2xl p-4 shadow-sm">
              <p className="text-xs text-text-muted mb-1 font-semibold">数据路径</p>
              <p className="text-xs font-mono text-text-main font-semibold truncate">{result.db_path ? result.db_path.split('\\').slice(-2).join('\\') : '—'}</p>
            </div>
          </div>
        </motion.div>
      )}

      {(phase === 'error' || phase === 'timeout') && (
        <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}}
          className="flex items-start gap-3 p-4 bg-amber-500/10 border border-amber-500/20 rounded-2xl">
          <XCircle size={20} weight="fill" className="text-[#c37d0d] shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-[#c37d0d] font-semibold">{phase === 'timeout' ? '获取超时' : '提取失败'}</p>
            <p className="text-xs text-[#c37d0d]/85 mt-1 font-medium">{msg}</p>
          </div>
        </motion.div>
      )}

      {phase !== 'done' && (
        <motion.button
          whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
          onClick={handleExtract}
          disabled={busy}
          className="w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide shadow-sm transition-all duration-300 disabled:opacity-50 cursor-pointer bg-[#d45656] hover:opacity-95 text-white flex items-center justify-center gap-2"
        >
          {busy ? (
            <><Spinner size={14} weight="bold" className="animate-spin" /> 获取中...</>
          ) : phase === 'timeout' || phase === 'error' ? (
            <><Key size={14} weight="fill" /> 重试</>
          ) : (
            <><Key size={14} weight="fill" /> 重新获取密钥</>
          )}
        </motion.button>
      )}
    </motion.div>
  )
}
