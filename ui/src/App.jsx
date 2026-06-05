import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Gear, ChartLine, Scroll, Users, Spinner } from '@phosphor-icons/react'
import Dashboard from './components/Dashboard'
import ConfigPanel from './components/ConfigPanel'
import NicknameEditor from './components/NicknameEditor'
import LogViewer from './components/LogViewer'
import Onboarding from './components/Onboarding'

const TABS = [
  { id: 'dashboard', label: '运行状态', icon: ChartLine },
  {
    id: 'config', label: '系统配置', icon: Gear,
    subs: [
      { id: 'ai', label: 'AI 后端配置' },
      { id: 'identity', label: '机器人身份' },
      { id: 'features', label: '功能开关' },
    ],
  },
  { id: 'nicknames', label: '群友昵称', icon: Users },
  { id: 'logs', label: '运行日志', icon: Scroll },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [configSection, setConfigSection] = useState('ai')
  const [botStatus, setBotStatus] = useState(null)
  const [onboardingDone, setOnboardingDone] = useState(null) // null = loading

  // Check onboarding status on mount
  useEffect(() => {
    async function check() {
      try {
        const res = await fetch('http://127.0.0.1:7327/api/onboarding/status')
        const d = await res.json()
        setOnboardingDone(d.onboarding_done)
      } catch {
        setTimeout(check, 1000) // Retry every 1s until server is ready
      }
    }
    check()
  }, [])

  // Connect WebSocket only after onboarding is confirmed
  useEffect(() => {
    if (!onboardingDone) return
    let reconnectTimer = null
    let socket = null

    function connectWS() {
      socket = new WebSocket('ws://127.0.0.1:7327/ws')
      socket.onmessage = (e) => {
        try { setBotStatus(JSON.parse(e.data)) } catch {}
      }
      socket.onclose = () => {
        reconnectTimer = setTimeout(connectWS, 3000)
      }
      socket.onerror = () => {
        socket?.close()
      }
    }
    connectWS()

    return () => {
      clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [onboardingDone])

  const status = botStatus || {
    running: false,
    uptime_sec: 0,
    messages_processed: 0,
    wechat_backend: 'wcdb',
    ai_backend: 'deepseek',
    db_ok: false,
    last_api_call_sec_ago: -1,
    last_api_call_time: 0,
    timestamp: '',
    error: '',
  }

  // Loading state
  if (onboardingDone === null) {
    return (
      <div className="min-h-[100dvh] bg-[#F7F6F3] flex items-center justify-center">
        <div className="text-center">
          <Spinner size={32} weight="bold" className="animate-spin text-[#346538] mx-auto mb-4" />
          <p className="text-sm text-[#787774] font-mono">正在加载...</p>
        </div>
      </div>
    )
  }

  // Onboarding
  if (!onboardingDone) {
    return <Onboarding onComplete={() => setOnboardingDone(true)} />
  }

  return (
    <div className="min-h-[100dvh] bg-[#F7F6F3]">
      {/* Sidebar */}
      <div className="fixed left-0 top-0 h-full w-56 bg-white border-r border-[#EAEAEA] z-40">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-8">
            <div className="relative">
              <img src="/logo-128.png" alt="WeChatBot" className="w-8 h-8 rounded-lg" />
              <div className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full ring-2 ring-white ${status.running ? 'bg-[#346538]' : 'bg-[#B8B8B6]'}`} />
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-[#1F1F1F]">微信机器人</h1>
              <p className="text-xs text-[#787774] font-mono">{status.running ? '运行中' : '已停止'}</p>
            </div>
          </div>

          <nav className="space-y-1">
            {TABS.map(({ id, label, icon: Icon, subs }) => (
              <div key={id}>
                <button
                  onClick={() => setActiveTab(id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 text-[15px] transition-all duration-200 ${
                    activeTab === id
                      ? 'text-[#1F1F1F] font-semibold'
                      : 'text-[#787774] font-medium hover:text-[#1F1F1F]'
                  }`}
                >
                  <Icon weight={activeTab === id ? 'fill' : 'regular'} size={22} />
                  {label}
                </button>
                {/* Config sub-nav: always visible, with vertical connector line */}
                {subs && (
                  <div className="ml-[30px] mt-1 border-l-2 border-[#EAEAEA] pl-[14px] space-y-0.5">
                    {subs.map(sub => (
                      <button
                        key={sub.id}
                        onClick={() => { setActiveTab(id); setConfigSection(sub.id) }}
                        className={`w-full text-left py-1.5 text-sm transition-all ${
                          activeTab === id && configSection === sub.id
                            ? 'text-[#346538] font-medium'
                            : 'text-[#787774] hover:text-[#1F1F1F]'
                        }`}
                      >
                        {sub.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </div>

        <div className="absolute bottom-0 left-0 right-0 p-4">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${status.running ? 'bg-[#346538]' : 'bg-[#B8B8B6]'}`} />
            <span className="text-xs text-[#787774] font-mono">
              {status.running ? `运行 ${Math.floor(status.uptime_sec / 60)} 分钟` : '已停止'}
            </span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="ml-56">
        <div className="sticky top-0 z-30 bg-[#F7F6F3]/80 backdrop-blur-sm border-b border-[#EAEAEA] px-8 py-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-tight text-[#1F1F1F]">
            {TABS.find(t => t.id === activeTab)?.label}
          </h2>
          <div className="flex items-center gap-4">
            <span className="text-xs text-[#787774] font-mono">
              已处理 {status.messages_processed.toLocaleString()} 条消息
            </span>
            <div className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-semibold transition-all ${
                status.running
                  ? 'bg-[#EDF3EC] text-[#346538] border border-[#C5DAC2]'
                  : 'bg-[#F7F6F3] text-[#B8B8B6] border border-[#EAEAEA]'
              }`}>
              <div className={`w-2 h-2 rounded-full ${status.running ? 'bg-[#346538]' : 'bg-[#B8B8B6]'}`} />
              {status.running ? '运行中' : '未启动'}
            </div>
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="p-8"
          >
            {activeTab === 'dashboard' && <Dashboard status={status} />}
            {activeTab === 'config' && <ConfigPanel activeSection={configSection} onNavigate={setConfigSection} />}
            {activeTab === 'nicknames' && <NicknameEditor />}
            {activeTab === 'logs' && <LogViewer />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
