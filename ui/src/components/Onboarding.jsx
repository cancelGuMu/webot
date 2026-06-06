import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Spinner, Lock, Sun, Moon } from '@phosphor-icons/react'
import { Step1Prepare, Step2WeChatConfig, Step3AIConfig, Step4Features } from './OnboardingSteps'

const iconVariants = {
  hover: { y: -1.5, scale: 1.05, transition: { type: 'spring', stiffness: 300, damping: 15 } }
}

const STEPS = [
  { id: 1, label: '环境诊断与密钥', desc: '诊断系统 & 提取/输入密钥' },
  { id: 2, label: '微信配置', desc: '设置机器人身份' },
  { id: 3, label: 'AI 后端', desc: '配置 AI 服务' },
  { id: 4, label: '功能设置', desc: '选择功能开关' },
]

const pageTransition = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
}

export default function Onboarding({ onComplete }) {
  const [activeStep, setActiveStep] = useState(1)
  const [stepDone, setStepDone] = useState({ 1: false, 2: false, 3: false, 4: false })

  // Onboarding manages its local storage theme state as well
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
    localStorage.setItem('theme', theme)
  }, [theme])

  const [data, setData] = useState({
    // Step 1
    key: '', wxid: '', db_path: '',
    // Step 2
    bot_display_name: '', wechat_groups: '*',
    // Step 3
    ai_backend: 'deepseek', deepseek_api_key: '', deepseek_model: 'deepseek-v4-flash',
    anthropic_api_key: '', summarize_model: 'claude-haiku-4-5-20251001',
    // Step 4
    fun_enabled: true,
    proactive_enabled: false,
    sticky_mention_enabled: true,
  })

  function updateData(updates) {
    setData(prev => ({ ...prev, ...updates }))
  }

  function markDone(step) {
    setStepDone(prev => ({ ...prev, [step]: true }))
    if (step < 4) setActiveStep(step + 1)
  }

  return (
    <div className="min-h-[100dvh] bg-bg-main text-text-main font-sans transition-colors duration-200 relative overflow-hidden">
      {/* Sidebar */}
      <div className="fixed left-0 top-0 h-full w-56 bg-bg-main border-r border-border-main z-40">
        <div className="p-5 flex flex-col h-full justify-between">
          <div>
            <div className="flex items-center gap-3 mb-8">
              <div className="relative">
                <img src="/logo-128.png" alt="webot" className="w-9 h-9 rounded-full border border-border-main" />
                <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full ring-2 ring-bg-main bg-brand-green animate-pulse" />
              </div>
              <div>
                <h1 className="text-sm font-semibold tracking-tight text-text-main">微信机器人</h1>
                <p className="text-[11px] text-text-muted font-mono font-medium tracking-wider uppercase">启动工坊</p>
              </div>
            </div>

            <nav className="space-y-1">
              {STEPS.map(({ id, label, desc }) => {
                const done = stepDone[id]
                const active = activeStep === id
                const locked = !done && !active && !stepDone[id - 1]

                return (
                  <div key={id}>
                    <motion.button
                      whileHover={locked ? undefined : "hover"}
                      whileTap={locked ? undefined : { scale: 0.98 }}
                      onClick={() => { if (!locked) setActiveStep(id) }}
                      disabled={locked}
                      className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-full text-[14px] transition-all duration-200 text-left cursor-pointer relative ${
                        active
                          ? 'text-brand-green-hover dark:text-brand-green font-semibold'
                          : 'text-text-muted font-medium'
                      } ${locked ? 'cursor-not-allowed opacity-40' : 'hover:text-text-main hover:bg-bg-raised/60'}`}
                    >
                      {active && (
                        <motion.div
                          layoutId="activeOnboardingStep"
                          className="absolute inset-0 bg-brand-green-light rounded-full -z-10"
                          transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                        />
                      )}
                      <motion.div variants={iconVariants} className="flex items-center z-10">
                        {done ? (
                          <CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green shrink-0" />
                        ) : active ? (
                          <div className="w-4.5 h-4.5 rounded-full border-2 flex items-center justify-center shrink-0 border-brand-green-hover dark:border-brand-green">
                            <div className="w-2 h-2 rounded-full bg-brand-green-hover dark:bg-brand-green" />
                          </div>
                        ) : locked ? (
                          <Lock size={16} className="text-text-muted/40 shrink-0" />
                        ) : (
                          <div className="w-4.5 h-4.5 rounded-full border-2 border-border-main shrink-0" />
                        )}
                      </motion.div>
                      <div className="z-10">
                        <p className="text-xs font-semibold">{label}</p>
                        <p className="text-[9px] text-text-muted font-mono tracking-tight">{desc}</p>
                      </div>
                    </motion.button>
                  </div>
                )
              })}
            </nav>
          </div>

          <div className="border-t border-border-main pt-4 mt-auto space-y-3">
            {/* Theme switcher toggle button inside onboarding sidebar */}
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-full text-xs font-semibold bg-bg-main border border-border-main text-text-muted hover:text-text-main hover:border-text-muted/30 transition-colors cursor-pointer"
            >
              {theme === 'dark' ? <><Sun size={14} /> 正常模式</> : <><Moon size={14} /> 夜航控制台</>}
            </button>

            <div className="flex items-center gap-2.5 px-4 py-2 bg-bg-raised/80 rounded-full border border-border-main">
              <div className="w-2 h-2 rounded-full relative bg-brand-green">
                <span className="absolute inset-0 rounded-full bg-brand-green animate-ping opacity-75" />
              </div>
              <span className="text-[10px] text-text-muted font-semibold font-mono tracking-wider uppercase">
                DIAGNOSTICS READY
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="ml-56 flex items-center justify-center min-h-[100dvh] px-8 py-12 relative z-10">
        {/* Atmospheric Hero Gradient behind hero card */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] pointer-events-none opacity-60 blur-3xl"
          style={{ backgroundImage: 'radial-gradient(circle, rgba(24, 226, 153, 0.12) 0%, rgba(24, 226, 153, 0) 70%)' }}
        />

        <div className="w-full max-w-2xl bg-bg-card border border-border-main rounded-2xl p-8 shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none relative z-20">
          <AnimatePresence mode="wait">
            <motion.div key={activeStep} variants={pageTransition} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.18 }}>
              {activeStep === 1 && (
                <Step1Prepare data={data} updateData={updateData} onDone={() => markDone(1)} />
              )}
              {activeStep === 2 && (
                <Step2WeChatConfig data={data} updateData={updateData} onDone={() => markDone(2)} />
              )}
              {activeStep === 3 && (
                <Step3AIConfig data={data} updateData={updateData} onDone={() => markDone(3)} />
              )}
              {activeStep === 4 && (
                <Step4Features data={data} updateData={updateData} onComplete={onComplete} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
