import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Database, Brain, Clock, ChatCircle, Pulse, Play, Stop, Key, Spinner, CheckCircle, XCircle } from '@phosphor-icons/react'

const spring = { type: 'spring', stiffness: 100, damping: 20 }

function MetricCard({ icon: Icon, label, value, sub, accent = 'green' }) {
  const accents = {
    green:  { bg: '#EDF3EC', text: '#346538', border: '#C5DAC2' },
    blue:   { bg: '#E1F3FE', text: '#1F6C9F', border: '#B8DEF7' },
    amber:  { bg: '#FBF3DB', text: '#956400', border: '#F0DCAC' },
    rose:   { bg: '#FDEBEC', text: '#9F2F2D', border: '#F5C6C8' },
  }
  const a = accents[accent]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
      whileHover={{ y: -2 }}
      className="bg-white border border-[#EAEAEA] rounded-xl p-7 transition-shadow duration-300 hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: a.bg }}>
          <Icon size={20} weight="fill" style={{ color: a.text }} />
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-sm text-[#787774] font-medium">{label}</p>
        <p className="text-3xl font-semibold tracking-tight font-mono text-[#1F1F1F]">{value}</p>
        {sub && <p className="text-xs text-[#B8B8B6]">{sub}</p>}
      </div>
    </motion.div>
  )
}

function LiveIndicator({ label, ok }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-[#EAEAEA] last:border-0">
      <div className="relative flex-shrink-0">
        <div
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: ok ? '#346538' : '#9F2F2D' }}
        />
        {ok && (
          <motion.div
            animate={{ scale: [1, 2, 1], opacity: [0.3, 0, 0.3] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute inset-0 w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: '#346538' }}
          />
        )}
      </div>
      <span className="text-sm text-[#5F5F5C] flex-1">{label}</span>
      <span
        className="text-xs font-semibold font-mono px-2 py-0.5 rounded-full"
        style={{
          backgroundColor: ok ? '#EDF3EC' : '#FDEBEC',
          color: ok ? '#346538' : '#9F2F2D',
        }}
      >
        {ok ? '正常' : '异常'}
      </span>
    </div>
  )
}

const backendLabels = { wcdb: '本地数据库直读', direct: 'UIA 窗口读取' }
const aiLabels = { deepseek: 'DeepSeek', claude: 'Claude' }

export default function Dashboard({ status }) {
  const [busy, setBusy] = useState(false)
  const [, setTick] = useState(0)

  // 1-second heartbeat — drives real-time "X 秒前" display
  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  async function handleToggle() {
    setBusy(true)
    try {
      const endpoint = status.running ? '/api/stop' : '/api/start'
      await fetch(`http://127.0.0.1:7327${endpoint}`, { method: 'POST' })
      // Status update will come via WebSocket
    } catch {
      // Silently handle — status will update via WS or stay unchanged
    }
    setTimeout(() => setBusy(false), 1000)  // debounce
  }

  const uptimeMin = Math.floor(status.uptime_sec / 60)
  const uptimeStr = uptimeMin < 60
    ? `${uptimeMin} 分钟`
    : `${Math.floor(uptimeMin / 60)} 小时 ${uptimeMin % 60} 分钟`

  // Real-time: frontend computes elapsed seconds from absolute timestamp.
  // Server pushes last_api_call_time (Unix timestamp, 0 = never called).
  const apiSecAgo = status.last_api_call_time > 0
    ? Math.floor(Date.now() / 1000 - status.last_api_call_time)
    : -1
  const lastApi = apiSecAgo > 0 ? `${apiSecAgo} 秒前` : '暂无调用'

  return (
    <div className="space-y-10 max-w-6xl">
      {/* Control bar */}
      <div className="flex items-center gap-4">
        <motion.button
          whileTap={{ scale: 0.96 }}
          whileHover={{ scale: 1.02 }}
          onClick={handleToggle}
          disabled={busy}
          className="flex items-center gap-2.5 px-6 py-3 rounded-xl text-sm font-semibold tracking-wide transition-all duration-300 disabled:opacity-50"
          style={{
            backgroundColor: status.running ? '#FDEBEC' : '#EDF3EC',
            color: status.running ? '#9F2F2D' : '#346538',
            border: status.running ? '1px solid #F5C6C8' : '1px solid #C5DAC2',
          }}
        >
          {status.running ? (
            <><Stop size={18} weight="fill" /> 停止机器人</>
          ) : (
            <><Play size={18} weight="fill" /> 启动机器人</>
          )}
        </motion.button>
        <span className="text-xs text-[#B8B8B6] font-mono">
          {busy ? '处理中...' : (status.running ? '点击停止消息轮询' : '点击启动消息轮询')}
        </span>
      </div>

      {/* Error banner */}
      {status.error && !status.error.includes('KEY_MISSING') && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2 px-4 py-4 bg-[#FDEBEC] border border-[#F5C6C8] rounded-lg text-sm text-[#9F2F2D]"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1L15 14H1L8 1Z" fill="currentColor"/><path d="M8 6V9" stroke="white" strokeWidth="1.5"/><circle cx="8" cy="11.5" r="0.75" fill="white"/></svg>
          <span>{status.error}</span>
        </motion.div>
      )}

      {/* KEY_MISSING banner with inline extraction */}
      {status.error && status.error.includes('KEY_MISSING') && (
        <KeyExtractionBanner />
      )}
      <div className="grid grid-cols-3 gap-5">
        <MetricCard icon={ChatCircle} accent="green" label="已处理消息" value={status.messages_processed.toLocaleString()} sub={status.running ? '机器人运行中' : '机器人已停止'} />
        <MetricCard icon={Clock} accent="blue" label="运行时长" value={uptimeStr} sub={status.running ? '自上次启动' : '—'} />
        <MetricCard icon={Brain} accent="amber" label="最近 API 调用" value={lastApi} sub={`${aiLabels[status.ai_backend] || status.ai_backend || '—'} / ${backendLabels[status.wechat_backend] || status.wechat_backend || '—'}`} />
      </div>

      <div className="grid grid-cols-5 gap-5">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.1 }} className="bg-white border border-[#EAEAEA] rounded-xl p-7 col-span-3">
          <div className="flex items-center gap-2 mb-4">
            <Pulse size={16} weight="fill" className="text-[#346538]" />
            <h3 className="text-sm font-medium tracking-tight text-[#1F1F1F]">系统状态</h3>
          </div>
          <LiveIndicator label="数据库连接" ok={status.db_ok} />
          <LiveIndicator label="微信后端" ok={!!status.wechat_backend} />
          <LiveIndicator label="AI 后端" ok={!!status.ai_backend} />
          <LiveIndicator label="机器人进程" ok={status.running} />
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.15 }} className="bg-white border border-[#EAEAEA] rounded-xl p-7 col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Database size={16} weight="fill" className="text-[#787774]" />
            <h3 className="text-sm font-medium tracking-tight text-[#1F1F1F]">后端信息</h3>
          </div>
          <div className="space-y-4">
            {[
              ['微信后端', backendLabels[status.wechat_backend] || status.wechat_backend || '—'],
              ['AI 后端', aiLabels[status.ai_backend] || status.ai_backend || '—'],
              ['日志文件', 'data/bot.log'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between items-center">
                <span className="text-xs text-[#787774]">{k}</span>
                <span className="text-xs font-mono text-[#5F5F5C]">{v}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="text-xs text-[#B8B8B6] font-mono">
        {status.timestamp ? `最近更新: ${status.timestamp}` : '等待首次状态更新...'}
      </motion.div>
    </div>
  )
}

// ── Inline key extraction banner ───────────────────────────────────────

const API = 'http://127.0.0.1:7327'
const EXTRACTION_PHASE_MAP = {
  hooking:         { color: '#1F6C9F', bg: '#E1F3FE', border: '#B8DEF7', label: '正在尝试直接获取...' },
  waiting_exit:    { color: '#956400', bg: '#FBF3DB', border: '#F0DCAC', label: '请退出微信' },
  waiting_login:   { color: '#1F6C9F', bg: '#E1F3FE', border: '#B8DEF7', label: '等待登录微信' },
  hooking_restart: { color: '#346538', bg: '#EDF3EC', border: '#C5DAC2', label: '正在安装 Hook...' },
}

function KeyExtractionBanner() {
  const [phase, setPhase] = useState('idle') // idle | extracting | hooking | waiting_exit | waiting_login | hooking_restart | done | timeout | error
  const [msg, setMsg] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const pollRef = useRef(null)

  // Clean up polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  async function handleExtract() {
    setBusy(true)
    setPhase('extracting')
    setMsg('正在准备...')
    setResult(null)
    try {
      // Step 1: Reset any previous onboarding state
      await fetch(`${API}/api/onboarding/reset`, { method: 'POST' })

      // Step 2: Start extraction
      const startRes = await fetch(`${API}/api/onboarding/step1`, { method: 'POST' })
      const start = await startRes.json()
      if (!start.ok) {
        setPhase('error')
        setMsg(start.message || '启动失败，请稍后重试')
        setBusy(false)
        return
      }

      // Step 3: Poll for progress
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
        } catch {
          // Server error, keep polling
        }
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
      className="flex flex-col gap-3 px-4 py-4 rounded-lg border transition-colors duration-500"
      style={{
        backgroundColor: isDone ? '#EDF3EC' : '#FDEBEC',
        borderColor: isDone ? '#C5DAC2' : '#F5C6C8',
      }}
    >
      {/* Title bar — red warning or green success */}
      <div className="flex items-center gap-2 text-sm"
        style={{ color: isDone ? '#346538' : '#9F2F2D' }}>
        {isDone ? (
          <CheckCircle size={16} weight="fill" />
        ) : (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1L15 14H1L8 1Z" fill="currentColor"/><path d="M8 6V9" stroke="white" strokeWidth="1.5"/><circle cx="8" cy="11.5" r="0.75" fill="white"/></svg>
        )}
        <span>{isDone ? '密钥获取成功 — 请重启机器人' : '加密密钥缺失 — 需要重新获取才能读取微信消息'}</span>
      </div>

      {/* Progress display */}
      {phase !== 'idle' && phase !== 'done' && phase !== 'timeout' && phase !== 'error' && phaseMeta && (
        <motion.div initial={{opacity:0}} animate={{opacity:1}}
          className="flex items-center gap-3 px-4 py-3 rounded-lg"
          style={{ backgroundColor: phaseMeta.bg, border: `1px solid ${phaseMeta.border}` }}>
          <Spinner size={20} weight="bold" className="animate-spin" style={{ color: phaseMeta.color }} />
          <div>
            <p className="text-sm font-medium" style={{ color: phaseMeta.color }}>{phaseMeta.label}</p>
            <p className="text-xs mt-1" style={{ color: phaseMeta.color, opacity: 0.7 }}>{msg}</p>
          </div>
        </motion.div>
      )}

      {/* Done state */}
      {phase === 'done' && result && (
        <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[#F9F9F8] border border-[#EAEAEA] rounded-lg p-3">
              <p className="text-xs text-[#B8B8B6] mb-1">微信账号</p>
              <p className="text-sm font-mono text-[#1F1F1F] truncate">{result.wxid || '—'}</p>
            </div>
            <div className="bg-[#F9F9F8] border border-[#EAEAEA] rounded-lg p-3">
              <p className="text-xs text-[#B8B8B6] mb-1">数据路径</p>
              <p className="text-xs font-mono text-[#787774] truncate">{result.db_path ? result.db_path.split('\\').slice(-2).join('\\') : '—'}</p>
            </div>
          </div>
        </motion.div>
      )}

      {/* Error / timeout state */}
      {(phase === 'error' || phase === 'timeout') && (
        <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}}
          className="flex items-start gap-3 px-4 py-3 bg-[#FBF3DB] border border-[#F0DCAC] rounded-lg">
          <XCircle size={20} weight="fill" className="text-[#956400] shrink-0 mt-0.5" />
          <div>
            <p className="text-sm text-[#956400] font-medium">{phase === 'timeout' ? '获取超时' : '提取失败'}</p>
            <p className="text-xs text-[#956400]/70 mt-1">{msg}</p>
          </div>
        </motion.div>
      )}

      {/* Action button */}
      {phase !== 'done' && (
        <motion.button
          whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
          onClick={handleExtract}
          disabled={busy}
          className="flex items-center gap-2 self-start px-4 py-2 rounded-lg text-xs font-semibold transition-all duration-300 disabled:opacity-50"
          style={{
            backgroundColor: busy ? '#D4D4D2' : '#9F2F2D',
            color: '#FFFFFF',
          }}
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
