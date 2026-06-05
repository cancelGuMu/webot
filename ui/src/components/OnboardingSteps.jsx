import { useState } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, ArrowRight, Spinner, XCircle } from '@phosphor-icons/react'
import { Field, Toggle, Select, Input, spring } from './SharedComponents'

const API = 'http://127.0.0.1:7327'

// ── Step 1: Key Extraction ───────────────────────────────────────────

export function Step1Prepare({ data, updateData, onDone }) {
  const [phase, setPhase] = useState('idle') // idle | extracting | done | timeout | error
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleExtract() {
    setBusy(true)
    setPhase('extracting')
    setMsg('')
    try {
      // Start extraction
      const startRes = await fetch(`${API}/api/onboarding/step1`, { method: 'POST' })
      const start = await startRes.json()
      if (!start.ok) {
        setPhase('error')
        setMsg(start.message || '启动失败')
        setBusy(false)
        return
      }

      // Poll status every second
      const poll = setInterval(async () => {
        try {
          const res = await fetch(`${API}/api/onboarding/step1-status`)
          const s = await res.json()

          if (s.phase === 'waiting_exit' || s.phase === 'waiting_login'
              || s.phase === 'hooking' || s.phase === 'hooking_restart') {
            setMsg(s.message || '')
          } else if (s.phase === 'done' && s.result) {
            clearInterval(poll)
            updateData({ key: s.result.key, wxid: s.result.wxid, db_path: s.result.db_path })
            setPhase('done')
            setBusy(false)
            onDone()
          } else if (s.phase === 'timeout' || s.phase === 'error') {
            clearInterval(poll)
            setPhase(s.phase === 'timeout' ? 'timeout' : 'error')
            setMsg(s.message || '提取失败')
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

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#346538' }} />
        <h3 className="text-base font-semibold tracking-tight text-[#1F1F1F]">准备环境</h3>
      </div>

      <div className="bg-white border border-[#EAEAEA] rounded-xl p-7 space-y-5">
        <p className="text-[15px] text-[#5F5F5C] leading-relaxed">
          webot 需要从微信获取加密密钥以读取聊天记录。此操作安全、无侵入，不会影响微信正常使用。
        </p>

        {/* Key display field */}
        <Field label="加密密钥" hint={data.key ? '密钥已成功获取' : '点击下方按钮自动获取'}>
          <input
            type="password"
            value={data.key || ''}
            readOnly
            disabled={!data.key}
            placeholder={phase === 'extracting' ? '正在获取...' : '等待获取...'}
            className="w-full bg-[#F9F9F8] border border-[#E0E0DE] rounded-lg px-4 py-2.5 text-[15px] text-[#1F1F1F]
                       placeholder:text-[#C8C8C6] font-mono tracking-[0.2em]
                       focus:outline-none transition-all duration-200
                       disabled:opacity-60 disabled:cursor-not-allowed"
          />
        </Field>

        {/* Status display */}
        {phase === 'extracting' && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}}
            className="flex items-center gap-3 px-4 py-3 bg-[#E1F3FE] border border-[#B8DEF7] rounded-lg">
            <Spinner size={20} weight="bold" className="animate-spin text-[#1F6C9F]" />
            <div>
              <p className="text-sm text-[#1F6C9F] font-medium">正在获取密钥...</p>
              <p className="text-xs text-[#1F6C9F]/70 mt-1">{msg || '正在等待微信操作...'}</p>
            </div>
          </motion.div>
        )}

        {phase === 'timeout' && (
          <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}}
            className="flex items-start gap-3 px-4 py-3 bg-[#FBF3DB] border border-[#F0DCAC] rounded-lg">
            <div className="w-6 h-6 rounded-full bg-[#956400]/10 flex items-center justify-center shrink-0 mt-0.5">
              <span className="text-[#956400] text-xs font-bold">!</span>
            </div>
            <div>
              <p className="text-sm text-[#956400] font-medium">获取超时</p>
              <p className="text-xs text-[#956400]/70 mt-1">{msg}</p>
            </div>
          </motion.div>
        )}

        {phase === 'error' && (
          <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}}
            className="flex items-start gap-3 px-4 py-3 bg-[#FDEBEC] border border-[#F5C6C8] rounded-lg">
            <XCircle size={20} weight="fill" className="text-[#9F2F2D] shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-[#9F2F2D] font-medium">提取失败</p>
              <p className="text-xs text-[#9F2F2D]/70 mt-1">{msg}</p>
            </div>
          </motion.div>
        )}

        {phase === 'done' && (
          <motion.div initial={{opacity:0,y:-4}} animate={{opacity:1,y:0}}
            className="space-y-3">
            <div className="flex items-center gap-3 px-4 py-3 bg-[#EDF3EC] border border-[#C5DAC2] rounded-lg">
              <CheckCircle size={20} weight="fill" className="text-[#346538]" />
              <span className="text-sm text-[#346538] font-medium">密钥获取成功</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[#F9F9F8] border border-[#EAEAEA] rounded-lg p-3">
                <p className="text-xs text-[#B8B8B6] mb-1">微信账号</p>
                <p className="text-sm font-mono text-[#1F1F1F] truncate">{data.wxid || '—'}</p>
              </div>
              <div className="bg-[#F9F9F8] border border-[#EAEAEA] rounded-lg p-3">
                <p className="text-xs text-[#B8B8B6] mb-1">数据路径</p>
                <p className="text-sm font-mono text-[#1F1F1F] truncate">{data.db_path ? data.db_path.split('\\').slice(-2).join('\\') : '—'}</p>
              </div>
            </div>
          </motion.div>
        )}

        {/* Action button */}
        {phase !== 'done' && (
          <motion.button
            whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
            onClick={handleExtract}
            disabled={busy}
            className="w-48 py-2.5 rounded-xl text-[15px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-50"
            style={{
              backgroundColor: '#1F1F1F', color: '#FFFFFF', border: '1px solid #1F1F1F',
            }}
          >
            {busy ? <><Spinner size={18} weight="bold" className="animate-spin" /> 获取中...</>
              : phase === 'timeout' ? '重试' : '获取密钥'}
          </motion.button>
        )}
      </div>
    </div>
  )
}

// ── Step 2: WeChat Config ────────────────────────────────────────────

export function Step2WeChatConfig({ data, updateData, onDone }) {
  const [busy, setBusy] = useState(false)
  const valid = (data.bot_display_name || '').trim().length >= 2

  async function handleNext() {
    setBusy(true)
    try {
      await fetch(`${API}/api/onboarding/step2`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bot_display_name: data.bot_display_name || '群聊小助手',
          wechat_groups: data.wechat_groups || '*',
          wechat_backend: 'wcdb',
          wxid: data.wxid || '',
          db_path: data.db_path || '',
        }),
      })
      onDone()
    } catch {}
    setBusy(false)
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#1F6C9F' }} />
        <h3 className="text-base font-semibold tracking-tight text-[#1F1F1F]">微信配置</h3>
      </div>

      <div className="bg-white border border-[#EAEAEA] rounded-xl p-7 space-y-5">
        {/* Read-only info from step 1 */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#F9F9F8] border border-[#EAEAEA] rounded-lg p-3">
            <p className="text-xs text-[#B8B8B6] mb-1">检测到的微信账号</p>
            <p className="text-sm font-mono text-[#1F1F1F] truncate">{data.wxid || '未检测到'}</p>
          </div>
          <div className="bg-[#F9F9F8] border border-[#EAEAEA] rounded-lg p-3">
            <p className="text-xs text-[#B8B8B6] mb-1">数据路径</p>
            <p className="text-xs font-mono text-[#787774] truncate">{data.db_path || '—'}</p>
          </div>
        </div>

        <Field label="机器人名称" hint="在群聊中显示的名称，用于 @ 提及检测">
          <Input
            value={data.bot_display_name || ''}
            onChange={v => updateData({ bot_display_name: v })}
            placeholder="例如：群聊小助手"
          />
        </Field>

        <Field label="目标群聊" hint="输入 * 表示监控所有群聊，指定群名可用逗号分隔">
          <Input
            value={data.wechat_groups || '*'}
            onChange={v => updateData({ wechat_groups: v })}
            placeholder="* = 所有群聊"
          />
        </Field>

        <motion.button
          whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
          onClick={handleNext}
          disabled={!valid || busy}
          className="w-48 py-2.5 rounded-xl text-[15px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-50"
          style={{ backgroundColor: valid ? '#1F1F1F' : '#D4D4D2', color: '#FFFFFF', border: `1px solid ${valid ? '#1F1F1F' : '#D4D4D2'}` }}
        >
          {busy ? <Spinner size={18} weight="bold" className="animate-spin" /> : <><ArrowRight size={18} /> 下一步</>}
        </motion.button>
      </div>
    </div>
  )
}

// ── Step 3: AI Backend ────────────────────────────────────────────────

export function Step3AIConfig({ data, updateData, onDone }) {
  const [busy, setBusy] = useState(false)
  const isDeepSeek = data.ai_backend === 'deepseek'
  const apiKey = isDeepSeek ? data.deepseek_api_key : data.anthropic_api_key
  const valid = (apiKey || '').trim().length >= 10

  async function handleNext() {
    setBusy(true)
    try {
      await fetch(`${API}/api/onboarding/step3`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ai_backend: data.ai_backend || 'deepseek',
          deepseek_api_key: data.deepseek_api_key || '',
          deepseek_model: data.deepseek_model || 'deepseek-v4-flash',
          anthropic_api_key: data.anthropic_api_key || '',
          summarize_model: data.summarize_model || 'claude-haiku-4-5-20251001',
        }),
      })
      onDone()
    } catch {}
    setBusy(false)
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#956400' }} />
        <h3 className="text-base font-semibold tracking-tight text-[#1F1F1F]">AI 后端配置</h3>
      </div>

      <div className="bg-white border border-[#EAEAEA] rounded-xl p-7 space-y-5">
        <Field label="AI 服务商" hint="推荐 DeepSeek，中文群聊效果更好">
          <Select value={data.ai_backend || 'deepseek'} onChange={v => updateData({ ai_backend: v })} options={[
            { value: 'deepseek', desc: 'DeepSeek', hint: '推荐 · 中文效果好' },
            { value: 'claude', desc: 'Claude', hint: 'Anthropic' },
          ]} />
        </Field>

        {isDeepSeek ? (
          <>
            <Field label="DeepSeek API Key" hint="在 platform.deepseek.com/api_keys 免费注册获取">
              <Input type="password" value={data.deepseek_api_key || ''} onChange={v => updateData({ deepseek_api_key: v })} placeholder="sk-xxxxxxxxxxxxxxxx" />
            </Field>
            <Field label="模型选择">
              <Select value={data.deepseek_model || 'deepseek-v4-flash'} onChange={v => updateData({ deepseek_model: v })} options={[
                { value: 'deepseek-v4-flash', desc: 'V4 Flash', hint: '极速 · 极低费用' },
                { value: 'deepseek-v4-pro', desc: 'V4 Pro', hint: '百万上下文 · 旗舰版' },
              ]} />
            </Field>
          </>
        ) : (
          <>
            <Field label="Anthropic API Key" hint="在 console.anthropic.com 获取">
              <Input type="password" value={data.anthropic_api_key || ''} onChange={v => updateData({ anthropic_api_key: v })} placeholder="sk-ant-xxxxxxxxxxxxxxxx" />
            </Field>
            <Field label="模型选择">
              <Select value={data.summarize_model || 'claude-haiku-4-5-20251001'} onChange={v => updateData({ summarize_model: v })} options={[
                { value: 'claude-haiku-4-5-20251001', desc: 'Haiku 4.5', hint: '快速 · 低成本' },
                { value: 'claude-sonnet-4-6', desc: 'Sonnet 4.6', hint: '高质量 · 推荐' },
              ]} />
            </Field>
          </>
        )}

        <motion.button
          whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
          onClick={handleNext}
          disabled={!valid || busy}
          className="w-48 py-2.5 rounded-xl text-[15px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-50"
          style={{ backgroundColor: valid ? '#1F1F1F' : '#D4D4D2', color: '#FFFFFF', border: `1px solid ${valid ? '#1F1F1F' : '#D4D4D2'}` }}
        >
          {busy ? <Spinner size={18} weight="bold" className="animate-spin" /> : <><ArrowRight size={18} /> 下一步</>}
        </motion.button>
      </div>
    </div>
  )
}

// ── Step 4: Features ──────────────────────────────────────────────────

export function Step4Features({ data, updateData, onComplete }) {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function handleFinish() {
    setBusy(true)
    try {
      await fetch(`${API}/api/onboarding/step4`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fun_enabled: data.fun_enabled ?? true,
          proactive_enabled: data.proactive_enabled ?? false,
          sticky_mention_enabled: data.sticky_mention_enabled ?? true,
        }),
      })
      setDone(true)
      setTimeout(onComplete, 1200)
    } catch {}
    setBusy(false)
  }

  if (done) {
    return (
      <motion.div initial={{opacity:0,scale:0.95}} animate={{opacity:1,scale:1}} transition={spring}
        className="flex flex-col items-center justify-center py-24">
        <motion.div initial={{scale:0}} animate={{scale:1}} transition={{delay:0.1,...spring}}
          className="w-16 h-16 rounded-full bg-[#EDF3EC] flex items-center justify-center mb-6">
          <CheckCircle size={36} weight="fill" className="text-[#346538]" />
        </motion.div>
        <h2 className="text-lg font-semibold text-[#1F1F1F] mb-2">设置完成</h2>
        <p className="text-sm text-[#787774]">正在进入仪表盘...</p>
      </motion.div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-5 rounded-full" style={{ backgroundColor: '#346538' }} />
        <h3 className="text-base font-semibold tracking-tight text-[#1F1F1F]">功能设置</h3>
      </div>

      <div className="bg-white border border-[#EAEAEA] rounded-xl p-7">
        <div className="space-y-0">
          <ToggleRow label="趣味抽签" desc="@机器人说抽签，随机返回运势签文" enabled={data.fun_enabled ?? true}
            onChange={v => updateData({ fun_enabled: v })} />
          <ToggleRow label="主动发言" desc="根据群聊活跃度自动参与对话" enabled={data.proactive_enabled ?? false}
            onChange={v => updateData({ proactive_enabled: v })} />
          <ToggleRow label="粘性提及" desc="@机器人后无需等待，机器人会追踪后续消息" enabled={data.sticky_mention_enabled ?? true}
            onChange={v => updateData({ sticky_mention_enabled: v })} />
        </div>

        <div className="mt-8">
          <motion.button
            whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
            onClick={handleFinish}
            disabled={busy}
            className="w-56 py-2.5 rounded-xl text-[15px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2"
            style={{ backgroundColor: '#346538', color: '#FFFFFF', border: '1px solid #346538' }}
          >
            {busy ? <Spinner size={18} weight="bold" className="animate-spin" /> : <><CheckCircle size={18} /> 完成设置</>}
          </motion.button>
        </div>
      </div>
    </div>
  )
}

function ToggleRow({ label, desc, enabled, onChange }) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-[#F0F0EE]">
      <div className="flex-1 mr-8">
        <p className="text-[15px] text-[#1F1F1F] font-medium">{label}</p>
        <p className="text-sm text-[#B8B8B6] mt-1.5">{desc}</p>
      </div>
      <Toggle enabled={enabled} onChange={onChange} />
    </div>
  )
}
