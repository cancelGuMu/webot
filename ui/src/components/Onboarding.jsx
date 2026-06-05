import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Spinner, Lock } from '@phosphor-icons/react'
import { Step1Prepare, Step2WeChatConfig, Step3AIConfig, Step4Features } from './OnboardingSteps'

const STEPS = [
  { id: 1, label: '准备环境', desc: '获取微信密钥' },
  { id: 2, label: '微信配置', desc: '设置机器人身份' },
  { id: 3, label: 'AI 后端', desc: '配置 AI 服务' },
  { id: 4, label: '功能设置', desc: '选择功能开关' },
]

const COLORS = ['#346538', '#1F6C9F', '#956400', '#346538']

const pageTransition = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
}

export default function Onboarding({ onComplete }) {
  const [activeStep, setActiveStep] = useState(1)
  const [stepDone, setStepDone] = useState({ 1: false, 2: false, 3: false, 4: false })
  const [data, setData] = useState({
    // Step 1
    key: '', wxid: '', db_path: '',
    // Step 2
    bot_display_name: '', wechat_groups: '*',
    // Step 3
    ai_backend: 'deepseek', deepseek_api_key: '', deepseek_model: 'deepseek-v4-flash',
    anthropic_api_key: '', summarize_model: 'claude-haiku-4-5-20251001',
    // Step 4
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
    <div className="min-h-[100dvh] bg-[#F7F6F3]">
      {/* Sidebar */}
      <div className="fixed left-0 top-0 h-full w-56 bg-white border-r border-[#EAEAEA] z-40">
        <div className="p-6">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-8 h-8 rounded-lg bg-[#EDF3EC] flex items-center justify-center">
              <div className="w-2.5 h-2.5 rounded-full bg-[#346538]" />
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-[#1F1F1F]">微信机器人</h1>
              <p className="text-xs text-[#787774] font-mono">初始设置</p>
            </div>
          </div>

          <nav className="space-y-1">
            {STEPS.map(({ id, label, desc }) => {
              const done = stepDone[id]
              const active = activeStep === id
              const locked = !done && !active && !stepDone[id - 1]
              const color = COLORS[id - 1]

              return (
                <div key={id}>
                  <button
                    onClick={() => { if (!locked) setActiveStep(id) }}
                    disabled={locked}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-[15px] transition-all duration-200 text-left ${
                      active ? 'font-semibold text-[#1F1F1F]' : 'text-[#787774]'
                    } ${locked ? 'cursor-not-allowed opacity-50' : 'hover:text-[#1F1F1F]'}`}
                  >
                    {done ? (
                      <CheckCircle size={20} weight="fill" style={{ color }} />
                    ) : active ? (
                      <div className="w-5 h-5 rounded-full border-2 flex items-center justify-center" style={{ borderColor: color }}>
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                      </div>
                    ) : locked ? (
                      <Lock size={20} className="text-[#D4D4D2]" />
                    ) : (
                      <div className="w-5 h-5 rounded-full border-2 border-[#D4D4D2]" />
                    )}
                    <div>
                      <p className="text-sm">{label}</p>
                      <p className="text-[11px] text-[#B8B8B6] font-mono">{desc}</p>
                    </div>
                  </button>
                </div>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Main content */}
      <div className="ml-56 flex items-center justify-center min-h-[100dvh] px-8">
        <div className="w-full max-w-2xl">
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
