import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Warning, FloppyDisk } from '@phosphor-icons/react'

const spring = { type: 'spring', stiffness: 200, damping: 25 }
const pageTransition = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
}

function Field({ label, hint, error, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <label className="block text-[15px] font-medium text-[#1F1F1F] mb-1.5">{label}</label>
      {children}
      {hint && !error && <p className="text-xs text-[#B8B8B6] mt-1.5">{hint}</p>}
      {error && <p className="text-xs text-[#9F2F2D] flex items-center gap-1 mt-1.5"><Warning size={12} />{error}</p>}
    </div>
  )
}

function Toggle({ enabled, onChange }) {
  const w = 64, d = 24, mx = 5, my = 3  // wider track, thinner height, dot unchanged
  const travel = w - d - mx * 2

  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      onClick={() => onChange(!enabled)}
      className="relative rounded-full shrink-0 transition-colors duration-300"
      style={{
        width: w, height: d + my * 2,
        backgroundColor: enabled ? 'rgb(52 101 56 / 0.12)' : '#EBEBE9',
        border: enabled ? '1px solid rgb(52 101 56 / 0.28)' : '1px solid #D4D4D2',
      }}
    >
      <span
        className="absolute text-[11px] font-semibold select-none pointer-events-none"
        style={{ left: mx + 2, top: '50%', transform: 'translateY(-50%)', color: '#346538', opacity: enabled ? 1 : 0, transition: 'opacity 0.15s' }}
      >ON</span>
      <span
        className="absolute text-[11px] font-semibold select-none pointer-events-none"
        style={{ right: mx + 2, top: '50%', transform: 'translateY(-50%)', color: '#B0B0AE', opacity: enabled ? 0 : 1, transition: 'opacity 0.15s' }}
      >OFF</span>
      <motion.div
        animate={{ x: enabled ? travel : 0 }}
        transition={spring}
        className="absolute rounded-full"
        style={{
          top: my, left: mx,
          width: d, height: d,
          backgroundColor: enabled ? '#346538' : '#B0B0AE',
        }}
      />
    </motion.button>
  )
}

function Select({ value, onChange, options }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handleClick(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const selected = options.find(o => o.value === value)

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full bg-[#F9F9F8] border border-[#E0E0DE] rounded-lg pl-4 pr-10 py-2.5 text-[15px] text-[#1F1F1F]
                   focus:outline-none focus:border-[#C5DAC2] focus:ring-1 focus:ring-[#346538]/15
                   transition-all duration-200 cursor-pointer text-left
                   hover:border-[#D0D0CE]"
      >
        {selected ? `${selected.value}  ·  ${selected.desc}` : value}
      </button>
      <span
        className="absolute right-3 top-1/2 pointer-events-none select-none text-[#B8B8B6] text-lg font-mono transition-all duration-200"
        style={{ transform: open ? 'translateY(-55%) rotate(90deg)' : 'translateY(-55%) rotate(0deg)' }}
      >&#8250;</span>

      {open && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute z-50 left-0 right-0 mt-1 bg-white border border-[#EAEAEA] rounded-lg shadow-[0_4px_16px_rgba(0,0,0,0.06)] overflow-hidden"
        >
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-4 py-2.5 text-[15px] transition-colors flex items-center gap-3 font-mono
                ${value === opt.value ? 'bg-[#EDF3EC] text-[#346538]' : 'text-[#1F1F1F] hover:bg-[#F7F6F3]'}`}
            >
              <span className="w-[72px] shrink-0 font-semibold">{opt.value}</span>
              <span className="w-[4px] shrink-0 text-[#D0D0CE]">·</span>
              <span className="w-[80px] shrink-0">{opt.desc}</span>
              <span className="w-[4px] shrink-0 text-[#D0D0CE]">·</span>
              <span className="text-[#787774] truncate">{opt.hint}</span>
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}

function Input({ type = 'text', value, onChange, placeholder }) {
  return (
    <motion.input
      whileFocus={{ scale: 1.003 }}
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-[#F9F9F8] border border-[#E0E0DE] rounded-lg px-4 py-2.5 text-[15px] text-[#1F1F1F]
                 placeholder:text-[#C8C8C6] font-mono tabular-nums
                 focus:outline-none focus:border-[#C5DAC2] focus:ring-1 focus:ring-[#346538]/15
                 transition-all duration-200
                 hover:border-[#D0D0CE]"
    />
  )
}

function AiSection({ form, update }) {
  return (
    <div>
      <Field label="AI 服务商" hint="推荐使用 DeepSeek，中文群聊效果更好">
        <Select value={form.ai_backend} onChange={v => update('ai_backend', v)} options={[
          { value: 'deepseek', desc: 'DeepSeek', hint: '推荐 · 中文效果好' },
          { value: 'claude', desc: 'Claude', hint: 'Anthropic' },
        ]} />
      </Field>
      <Field label="API Key" hint="在 platform.deepseek.com/api_keys 免费注册获取" error={!form.deepseek_api_key ? '请填写 API Key' : null}>
        <Input type="password" value={form.deepseek_api_key} onChange={v => update('deepseek_api_key', v)} placeholder="sk-xxxxxxxxxxxxxxxx" />
      </Field>
      <Field label="模型选择">
        <Select value={form.deepseek_model} onChange={v => update('deepseek_model', v)} options={[
          { value: 'deepseek-v4-flash', desc: 'V4 Flash', hint: '极速 · 极低费用' },
          { value: 'deepseek-v4-pro', desc: 'V4 Pro', hint: '百万上下文 · 旗舰版' },
        ]} />
      </Field>
    </div>
  )
}

function IdentitySection({ form, update }) {
  return (
    <div>
      <Field label="机器人微信昵称" hint="用于检测 @提及">
        <Input value={form.bot_display_name} onChange={v => update('bot_display_name', v)} placeholder="例如：群聊小助手" />
      </Field>
      <Field label="目标群聊" hint="留空表示监控所有群聊，填写群名可用逗号分隔">
        <Input value={form.wechat_groups} onChange={v => update('wechat_groups', v)} placeholder="留空 = 所有群聊" />
      </Field>
    </div>
  )
}

function FeaturesSection({ form, update }) {
  return (
    <div>
      <div className="flex items-center justify-between py-4 border-b border-[#F0F0EE]">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-[#1F1F1F] font-medium">主动发言</p>
          <p className="text-sm text-[#B8B8B6] mt-1.5">无需 @提及，根据聊天活跃度自动参与对话</p>
        </div>
        <Toggle enabled={form.proactive_enabled} onChange={v => update('proactive_enabled', v)} />
      </div>
      <div className="flex items-center justify-between py-4 border-b border-[#F0F0EE]">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-[#1F1F1F] font-medium">低俗内容过滤</p>
          <p className="text-sm text-[#B8B8B6] mt-1.5">检测并警告群内的不当内容，过滤 AI 输出</p>
        </div>
        <Toggle enabled={form.vulgar_guard_enabled} onChange={v => update('vulgar_guard_enabled', v)} />
      </div>
      <div className="pt-4">
        <Field label="日志级别" hint="记录机器人运行日志的详细程度">
          <Select value={form.log_level} onChange={v => update('log_level', v)} options={[
            { value: 'DEBUG', desc: '调试信息', hint: '排查故障时使用' },
            { value: 'INFO', desc: '常规信息', hint: '日常使用（推荐）' },
            { value: 'WARNING', desc: '仅警告', hint: '长期稳定运行时使用' },
            { value: 'ERROR', desc: '仅错误', hint: '只关心故障时使用' },
          ]} />
        </Field>
      </div>
    </div>
  )
}

const sectionTitles = { ai: 'AI 后端配置', identity: '机器人身份', features: '功能开关' }
const sectionAccents = { ai: '#346538', identity: '#1F6C9F', features: '#956400' }

export default function ConfigPanel({ activeSection, onNavigate }) {
  const [saved, setSaved] = useState(false)
  const [form, setForm] = useState({
    ai_backend: 'deepseek', deepseek_api_key: '', deepseek_model: 'deepseek-v4-flash',
    bot_display_name: '', wechat_backend: 'wcdb', wechat_groups: '',
    proactive_enabled: false, vulgar_guard_enabled: true, log_level: 'INFO',
  })

  function update(key, value) { setForm(prev => ({ ...prev, [key]: value })); setSaved(false) }
  function handleSave() { setSaved(true); setTimeout(() => setSaved(false), 3000) }

  return (
    <div className="max-w-2xl">
      <div style={{ minHeight: 420 }}>
        <AnimatePresence mode="wait">
          <motion.div key={activeSection} variants={pageTransition} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.18 }}>
            <div className="flex items-center gap-2 mb-6">
              <div className="w-1 h-5 rounded-full" style={{ backgroundColor: sectionAccents[activeSection] }} />
              <h3 className="text-base font-semibold tracking-tight text-[#1F1F1F]">{sectionTitles[activeSection]}</h3>
            </div>
            <div className="bg-white border border-[#EAEAEA] rounded-xl">
              <div className="p-7">
                {activeSection === 'ai' && <AiSection form={form} update={update} />}
                {activeSection === 'identity' && <IdentitySection form={form} update={update} />}
                {activeSection === 'features' && <FeaturesSection form={form} update={update} />}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="mt-12">
        <motion.button
          whileTap={{ scale: 0.97 }}
          whileHover={{ scale: 1.02 }}
          onClick={handleSave}
          className="w-48 py-2.5 rounded-xl text-[15px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2"
          style={{
            backgroundColor: saved ? '#EDF3EC' : '#1F1F1F',
            color: saved ? '#346538' : '#FFFFFF',
            border: saved ? '1px solid #C5DAC2' : '1px solid #1F1F1F',
          }}
        >
          {saved ? (
            <><CheckCircle size={18} weight="fill" /> 已保存</>
          ) : (
            <><FloppyDisk size={18} /> 保存配置</>
          )}
        </motion.button>
      </div>
    </div>
  )
}
