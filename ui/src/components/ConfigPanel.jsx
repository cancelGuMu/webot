import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Warning, FloppyDisk, Info } from '@phosphor-icons/react'
import { spring, Field, Toggle, Select, Input } from './SharedComponents'

const pageTransition = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
}

function AiSection({ form, update }) {
  const isDeepSeek = form.ai_backend === 'deepseek'

  return (
    <div>
      <Field label="AI 服务商" hint="推荐使用 DeepSeek，中文群聊效果更好；Claude 需要 Anthropic API Key">
        <Select value={form.ai_backend} onChange={v => update('ai_backend', v)} options={[
          { value: 'deepseek', desc: 'DeepSeek', hint: '推荐 · 中文效果好' },
          { value: 'claude', desc: 'Claude', hint: 'Anthropic' },
        ]} />
      </Field>

      {isDeepSeek ? (
        <>
          <Field label="DeepSeek API Key" hint="在 platform.deepseek.com/api_keys 免费注册获取" error={!form.deepseek_api_key ? '请填写 API Key' : null}>
            <Input type="password" value={form.deepseek_api_key} onChange={v => update('deepseek_api_key', v)} placeholder="sk-xxxxxxxxxxxxxxxx" />
          </Field>
          <Field label="DeepSeek 模型选择">
            <Select value={form.deepseek_model} onChange={v => update('deepseek_model', v)} options={[
              { value: 'deepseek-v4-flash', desc: 'V4 Flash', hint: '极速 · 极低费用' },
              { value: 'deepseek-v4-pro', desc: 'V4 Pro', hint: '百万上下文 · 旗舰版' },
            ]} />
          </Field>
        </>
      ) : (
        <>
          <Field label="Anthropic API Key" hint="在 console.anthropic.com 获取" error={!form.anthropic_api_key ? '请填写 API Key' : null}>
            <Input type="password" value={form.anthropic_api_key} onChange={v => update('anthropic_api_key', v)} placeholder="sk-ant-xxxxxxxxxxxxxxxx" />
          </Field>
          <Field label="Claude 模型选择">
            <Select value={form.summarize_model} onChange={v => update('summarize_model', v)} options={[
              { value: 'claude-haiku-4-5-20251001', desc: 'Haiku 4.5', hint: '快速 · 低成本' },
              { value: 'claude-sonnet-4-6', desc: 'Sonnet 4.6', hint: '高质量 · 推荐' },
            ]} />
          </Field>
        </>
      )}
    </div>
  )
}

function IdentitySection({ form, update }) {
  // Local editable groups array — source of truth for rendering
  const [groups, setGroups] = useState([])

  // Initialize from form.wechat_groups on mount only
  useEffect(() => {
    const raw = (form.wechat_groups || '').trim()
    if (raw === '*' || raw === '') {
      setGroups(['*'])
    } else {
      setGroups(raw.split(',').map(s => {
        const trimmed = s.trim()
        if (!trimmed) return ''
        try { return decodeURIComponent(trimmed) } catch { return trimmed }
      }).filter(Boolean))
    }
  }, [])

  // Sync local groups array back to form.wechat_groups (comma-separated, URL-encoded)
  function syncToForm(newGroups) {
    const nonEmpty = newGroups.filter(g => g !== '')
    if (nonEmpty.length === 0 || nonEmpty.includes('*')) {
      update('wechat_groups', '*')
    } else {
      update('wechat_groups', nonEmpty.map(g => encodeURIComponent(g)).join(','))
    }
  }

  const isAll = groups.length === 1 && groups[0] === '*'

  function updateGroup(index, value) {
    const next = [...groups]
    next[index] = value
    if (groups.length === 1 && groups[0] === '*') {
      // User started typing over the * chip → replace it
      setGroups([value])
      syncToForm([value])
    } else {
      setGroups(next)
      syncToForm(next)
    }
  }

  function removeGroup(index) {
    const removed = groups[index]
    const next = groups.filter((_, i) => i !== index)
    if (next.length === 0) {
      if (removed === '*') {
        // Removed the * chip → switch to empty input for adding specific groups
        setGroups([''])
        syncToForm([''])
      } else {
        // Last real group removed → default back to all groups
        setGroups(['*'])
        syncToForm(['*'])
      }
    } else {
      setGroups(next)
      syncToForm(next)
    }
  }

  function addGroup() {
    const next = [...groups, '']
    setGroups(next)
    syncToForm(next)
  }

  function restoreAll() {
    setGroups(['*'])
    syncToForm(['*'])
  }

  return (
    <div>
      <Field label="机器人微信昵称" hint="用于检测 @提及">
        <Input value={form.bot_display_name} onChange={v => update('bot_display_name', v)} placeholder="例如：群聊小助手" />
      </Field>

      <Field label="目标群聊" hint={isAll ? '当前监控所有群聊。点击 × 删除「全部群聊」后可指定群名' : `监控 ${groups.filter(g => g !== '').length} 个群聊`}>
        <div className="flex flex-wrap gap-2 mb-2">
          {groups.map((name, i) => {
            if (name === '') return null  // empty placeholder slot — input shown below
            return (
              <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-[#EDF3EC] border border-[#C5DAC2] rounded-lg text-[13px] text-[#346538]">
                {name === '*' ? '全部群聊' : name}
                <button type="button" onClick={() => removeGroup(i)}
                  className="ml-0.5 text-[#8AB88A] hover:text-[#9F2F2D] transition-colors leading-none text-base">&times;</button>
              </span>
            )
          })}
          {!isAll && (
            <button type="button" onClick={addGroup}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-[#F8F8F5] border border-dashed border-[#D0D0CE] rounded-lg text-[13px] text-[#6E6E6C] hover:border-[#346538] hover:text-[#346538] transition-colors">
              + 添加群聊
            </button>
          )}
        </div>
        {/* Restore link — visible when NOT in * mode */}
        {!isAll && (
          <button type="button" onClick={restoreAll}
            className="text-xs text-[#6E9FCF] hover:text-[#1F6C9F] transition-colors mb-2 cursor-pointer">
            恢复监控所有群聊
          </button>
        )}
        {/* Text inputs for each group, including empty placeholder slots */}
        {!isAll && groups.map((name, i) => (
          <input key={`input-${i}`} type="text" value={name}
            onChange={e => updateGroup(i, e.target.value)}
            onBlur={() => { if (!name.trim()) removeGroup(i) }}
            placeholder={`群聊 ${i + 1} 的名称`}
            className="w-full bg-[#F9F9F8] border border-[#E0E0DE] rounded-lg px-4 py-2 text-[15px] text-[#1F1F1F] placeholder:text-[#C8C8C6] focus:outline-none focus:border-[#C5DAC2] focus:ring-1 focus:ring-[#346538]/15 transition-all duration-200 hover:border-[#D0D0CE] mb-2" />
        ))}
        <p className="text-[11px] text-[#B8B8B6] mt-1.5">
          ⚠ 请先将目标群聊添加到微信通讯录，否则无法通过搜索进入
        </p>
        {!isAll && (
          <p className="text-[11px] text-[#B8B8B6] mt-1">💡 请输入微信中显示的完整群名，必须完全一致</p>
        )}
      </Field>

      <Field label="微信后端" hint="当前使用本地数据库直读模式（无需外部进程）">
        <Select value={form.wechat_backend} onChange={v => update('wechat_backend', v)} options={[
          { value: 'wcdb', desc: 'WCDB', hint: '推荐 · 原生数据库直读' },
        ]} />
      </Field>
    </div>
  )
}

const paramPanel = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, y: 20, transition: { duration: 0.2 } },
}

function ParamRow({ label, hint, children }) {
  return (
    <div>
      <p className="text-[14px] text-[#333333] font-medium">{label}</p>
      <p className="text-xs text-[#999999] mt-0.5 mb-2">{hint}</p>
      {children}
    </div>
  )
}

function FeaturesSection({ form, update }) {
  return (
    <div>
      {/* ── Fun: Draw Lots ── */}
      <div className="py-4 border-b border-[#F0F0EE]">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-[#1F1F1F] font-medium">趣味抽签</p>
            <p className="text-sm text-[#B8B8B6] mt-1.5">@机器人说"抽签"，随机返回运势签文（大吉/中吉/小吉/末吉/凶）</p>
          </div>
          <Toggle enabled={form.fun_enabled} onChange={v => update('fun_enabled', v)} />
        </div>
      </div>

      {/* ── Proactive Participation ── */}
      <div className="py-4 border-b border-[#F0F0EE]">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-[#1F1F1F] font-medium">主动发言</p>
            <p className="text-sm text-[#B8B8B6] mt-1.5">无需 @提及，根据聊天活跃度自动参与对话</p>
          </div>
          <Toggle enabled={form.proactive_enabled} onChange={v => update('proactive_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.proactive_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-[#F8F8F5] rounded-lg space-y-3">
              <p className="text-xs text-[#B8B8B6] leading-relaxed">
                机器人统计最近 <strong>速率窗口</strong> 秒内的群聊消息速率（条/分钟），
                与下方四个阈值比较，决定发言频率：
              </p>
              <div className="grid grid-cols-2 gap-3">
                <ParamRow label="速率窗口" hint="统计消息速率的时间范围（秒），默认 120 = 2 分钟">
                  <Input type="number" value={String(form.proactive_rate_window_sec || 120)}
                    onChange={v => update('proactive_rate_window_sec', parseInt(v) || 120)} />
                </ParamRow>
                <ParamRow label="安静阈值" hint={"速率低于此值不发言（默认 1.5 条/分）"}>
                  <Input type="number" value={String(form.proactive_rate_quiet ?? 1.5)}
                    onChange={v => update('proactive_rate_quiet', parseFloat(v) || 1.5)} />
                </ParamRow>
                <ParamRow label="随口阈值" hint={"超过此值偶尔插话（默认 4.0 条/分）"}>
                  <Input type="number" value={String(form.proactive_rate_casual ?? 4.0)}
                    onChange={v => update('proactive_rate_casual', parseFloat(v) || 4.0)} />
                </ParamRow>
                <ParamRow label="活跃阈值" hint={"超过此值频繁参与（默认 6.5 条/分）"}>
                  <Input type="number" value={String(form.proactive_rate_lively ?? 6.5)}
                    onChange={v => update('proactive_rate_lively', parseFloat(v) || 6.5)} />
                </ParamRow>
                <ParamRow label="爆发阈值" hint={"超过此值火力全开（默认 8.5 条/分）"}>
                  <Input type="number" value={String(form.proactive_rate_burst ?? 8.5)}
                    onChange={v => update('proactive_rate_burst', parseFloat(v) || 8.5)} />
                </ParamRow>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Sticky Mention ── */}
      <div className="py-4 border-b border-[#F0F0EE]">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-[#1F1F1F] font-medium">粘性提及</p>
            <p className="text-sm text-[#B8B8B6] mt-1.5">@机器人后无需等待回复即可继续说，机器人会追踪后续消息</p>
          </div>
          <Toggle enabled={form.sticky_mention_enabled} onChange={v => update('sticky_mention_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.sticky_mention_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-[#F8F8F5] rounded-lg">
              <ParamRow label="追踪超时" hint="用户发送空 @消息后，等待后续消息的最长时间">
                <Select value={String(form.sticky_mention_ttl_sec || 60) + ' 秒'}
                  onChange={v => update('sticky_mention_ttl_sec', parseInt(v))}
                  options={[
                    { value: '30 秒', desc: '快速响应', hint: '30 秒后自动失效' },
                    { value: '60 秒', desc: '默认', hint: '60 秒后自动失效' },
                    { value: '120 秒', desc: '宽松', hint: '120 秒后自动失效' },
                    { value: '300 秒', desc: '最长时间', hint: '300 秒后自动失效' },
                  ]} />
              </ParamRow>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Log Level ── */}
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
  const [saveError, setSaveError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [form, setForm] = useState({
    ai_backend: 'deepseek', deepseek_api_key: '', deepseek_model: 'deepseek-v4-flash',
    anthropic_api_key: '', summarize_model: 'claude-haiku-4-5-20251001',
    bot_display_name: '', wechat_backend: 'wcdb', wechat_groups: '*',
    fun_enabled: true,
    proactive_enabled: false, proactive_rate_window_sec: 120,
    proactive_rate_quiet: 1.5, proactive_rate_casual: 4.0,
    proactive_rate_lively: 6.5, proactive_rate_burst: 8.5,
    sticky_mention_enabled: true, sticky_mention_ttl_sec: 60,
    log_level: 'INFO',
  })

  // Load current config from server on mount
  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('http://127.0.0.1:7327/api/load-config')
        const data = await res.json()
        if (data.ok && data.config) {
          setForm(prev => ({
            ...prev,
            ...data.config,
            // Ensure wechat_groups defaults to * if empty
            wechat_groups: data.config.wechat_groups || '*',
          }))
        }
      } catch {
        // Server not ready yet, use defaults
      }
      setLoaded(true)
    }
    load()
  }, [])

  function update(key, value) { setForm(prev => ({ ...prev, [key]: value })); setSaved(false); setSaveError('') }
  async function handleSave() {
    setSaved(false)
    setSaveError('')
    try {
      const res = await fetch('http://127.0.0.1:7327/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ai_backend: form.ai_backend,
          deepseek_api_key: form.deepseek_api_key,
          deepseek_model: form.deepseek_model,
          anthropic_api_key: form.anthropic_api_key,
          summarize_model: form.summarize_model,
          bot_display_name: form.bot_display_name,
          wechat_backend: form.wechat_backend,
          wechat_groups: form.wechat_groups,
          fun_enabled: form.fun_enabled,
          proactive_enabled: form.proactive_enabled,
          proactive_rate_window_sec: form.proactive_rate_window_sec,
          proactive_rate_quiet: form.proactive_rate_quiet,
          proactive_rate_casual: form.proactive_rate_casual,
          proactive_rate_lively: form.proactive_rate_lively,
          proactive_rate_burst: form.proactive_rate_burst,
          sticky_mention_enabled: form.sticky_mention_enabled,
          sticky_mention_ttl_sec: form.sticky_mention_ttl_sec,
          log_level: form.log_level,
        }),
      })
      const data = await res.json()
      if (data.ok) {
        setSaved(true)
        // Auto-clear success indicator after 3 seconds
        setTimeout(() => setSaved(false), 3000)
      } else {
        setSaveError(data.error || '保存失败')
        setTimeout(() => setSaveError(''), 5000)
      }
    } catch (e) {
      setSaveError('无法连接到服务器，请确认机器人已启动')
      setTimeout(() => setSaveError(''), 5000)
    }
  }

  return (
    <div className="max-w-2xl">
      {/* Save status banner */}
      <AnimatePresence>
        {saved && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-4 py-3 bg-[#EDF3EC] border border-[#C5DAC2] rounded-lg text-sm text-[#346538]"
          >
            <CheckCircle size={16} weight="fill" />
            <span>配置已保存。需要重启机器人才能生效。</span>
          </motion.div>
        )}
        {saveError && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-4 py-3 bg-[#FDEBEC] border border-[#F5C6C8] rounded-lg text-sm text-[#9F2F2D]"
          >
            <Warning size={16} weight="fill" />
            <span>{saveError}</span>
          </motion.div>
        )}
      </AnimatePresence>

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

      <div className="mt-8 flex items-center gap-4">
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
        {saved && (
          <span className="flex items-center gap-1.5 text-xs text-[#956400]">
            <Info size={14} />
            需要重启机器人
          </span>
        )}
      </div>
    </div>
  )
}
