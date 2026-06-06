import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Warning, FloppyDisk, Info, DownloadSimple, UploadSimple } from '@phosphor-icons/react'
import { spring, Field, Toggle, Select, Input } from './SharedComponents'

const pageTransition = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
}

function TypewriterText({ text, speed = 15 }) {
  const [displayedText, setDisplayedText] = useState('')

  useEffect(() => {
    setDisplayedText('')
    let i = 0
    const interval = setInterval(() => {
      setDisplayedText((prev) => prev + text.charAt(i))
      i++
      if (i >= text.length) {
        clearInterval(interval)
      }
    }, speed)
    return () => clearInterval(interval)
  }, [text, speed])

  return <span>{displayedText}</span>
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
          <Field label="API Base URL" hint="兼容 OpenAI 的转发地址；留默认值使用官方 API">
            <Input value={form.deepseek_base_url} onChange={v => update('deepseek_base_url', v)} placeholder="https://api.deepseek.com" />
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
          <Field label="API Base URL" hint="Anthropic API 地址；可填兼容代理或中转服务">
            <Input value={form.anthropic_base_url} onChange={v => update('anthropic_base_url', v)} placeholder="https://api.anthropic.com" />
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
        setGroups([''])
        syncToForm([''])
      } else {
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
            if (name === '') return null
            return (
              <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                {name === '*' ? '全部群聊' : name}
                <button type="button" onClick={() => removeGroup(i)}
                  className="ml-0.5 text-brand-green-hover/60 hover:text-[#d45656] transition-colors leading-none text-base">&times;</button>
              </span>
            )
          })}
          {!isAll && (
            <button type="button" onClick={addGroup}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-bg-raised border border-dashed border-border-main rounded-lg text-[13px] text-text-muted hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer">
              + 添加群聊
            </button>
          )}
        </div>
        {!isAll && (
          <button type="button" onClick={restoreAll}
            className="text-xs text-[#6E9FCF] hover:text-[#1F6C9F] transition-colors mb-2 cursor-pointer">
            恢复监控所有群聊
          </button>
        )}
        {!isAll && groups.map((name, i) => (
          <input key={`input-${i}`} type="text" value={name}
            onChange={e => updateGroup(i, e.target.value)}
            onBlur={() => { if (!name.trim()) removeGroup(i) }}
            placeholder={`群聊 ${i + 1} 的名称`}
            className="w-full bg-bg-raised border border-border-main rounded-lg px-4 py-2 text-[15px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all duration-200 hover:border-text-muted/30 mb-2" />
        ))}
        <p className="text-[11px] text-text-muted mt-1.5">
          ⚠ 请先将目标群聊添加到微信通讯录，否则无法通过搜索进入
        </p>
        {!isAll && (
          <p className="text-[11px] text-text-muted mt-1">💡 请输入微信中显示的完整群名，必须完全一致</p>
        )}
      </Field>

      <Field label="微信后端" hint="Windows 推荐 WCDB；macOS 推荐混合模式读取数据库并用辅助功能发送">
        <Select value={form.wechat_backend} onChange={v => update('wechat_backend', v)} options={[
          { value: 'wcdb', desc: 'WCDB', hint: '推荐 · 原生数据库直读' },
          { value: 'mac_hybrid', desc: 'macOS Hybrid', hint: '推荐 · 数据库读取 + 辅助功能发送' },
          { value: 'mac_ui', desc: 'macOS UI', hint: '实验性 · 辅助功能自动化' },
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
      <p className="text-[14px] text-text-main font-medium">{label}</p>
      <p className="text-xs text-text-muted mt-0.5 mb-2">{hint}</p>
      {children}
    </div>
  )
}

function FeaturesSection({ form, update }) {
  return (
    <div>
      {/* ── Fun: Draw Lots ── */}
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">趣味抽签</p>
            <p className="text-sm text-text-muted mt-1.5">@机器人说"抽签"，随机返回运势签文（大吉/中吉/小吉/末吉/凶）</p>
          </div>
          <Toggle enabled={form.fun_enabled} onChange={v => update('fun_enabled', v)} />
        </div>
      </div>

      {/* ── Proactive Participation ── */}
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">主动发言</p>
            <p className="text-sm text-text-muted mt-1.5">无需 @提及，根据聊天活跃度自动参与对话</p>
          </div>
          <Toggle enabled={form.proactive_enabled} onChange={v => update('proactive_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.proactive_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-bg-raised rounded-lg space-y-3">
              <p className="text-xs text-text-muted leading-relaxed">
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
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">粘性提及</p>
            <p className="text-sm text-text-muted mt-1.5">@机器人后无需等待回复即可继续说，机器人会追踪后续消息</p>
          </div>
          <Toggle enabled={form.sticky_mention_enabled} onChange={v => update('sticky_mention_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.sticky_mention_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-bg-raised rounded-lg">
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

const sectionTitles = { ai: 'AI 后端配置', identity: '机器人身份', features: '功能开关', sandbox: '提示词沙箱' }
const sectionAccents = { ai: '#18E299', identity: '#3772cf', features: '#c37d0d', sandbox: '#8b5cf6' }

function SandboxSection({ form }) {
  const [message, setMessage] = useState('')
  const [senderName, setSenderName] = useState('张三')
  const [groupName, setGroupName] = useState('技术讨论群')
  const [groupMemory, setGroupMemory] = useState('这个群的群友大多是程序员，喜欢探讨最新的大模型和AI工具。')
  const [loading, setLoading] = useState(false)
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')
  const [latency, setLatency] = useState(0)

  async function handleTest() {
    if (!message.trim()) return
    setLoading(true)
    setReply('')
    setError('')
    const start = Date.now()
    try {
      const res = await fetch('http://127.0.0.1:7327/api/sandbox/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          sender_name: senderName,
          group_name: groupName,
          group_memory: groupMemory,
          ai_backend: form.ai_backend,
          deepseek_api_key: form.deepseek_api_key,
          deepseek_model: form.deepseek_model,
          anthropic_api_key: form.anthropic_api_key,
          summarize_model: form.summarize_model,
        })
      })
      const data = await res.json()
      setLatency(Date.now() - start)
      if (data.ok) {
        setReply(data.reply)
      } else {
        setError(data.error || '测试请求失败')
      }
    } catch (err) {
      setError(err.message || '网络连接错误')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <Field label="测试输入消息" hint="模拟用户在群里发送的消息内容">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="输入测试消息，例如：@小助手 今天有什么好玩的大模型推荐？"
            className="w-full min-h-[90px] bg-bg-raised border border-border-main rounded-2xl p-4 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15 transition-all duration-200"
          />
        </Field>
      </div>

      <div className="border-t border-border-main/50 my-2" />

      {/* Advanced variables */}
      <details className="group">
        <summary className="text-xs font-semibold text-text-muted hover:text-text-main cursor-pointer select-none flex items-center gap-1.5 py-1">
          <span className="transition-transform group-open:rotate-90 font-mono">&#8250;</span>
          高级上下文环境变量 (可自定义)
        </summary>
        <div className="mt-3 space-y-4 pl-4 border-l border-border-main/60">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="模拟发送人" hint="例如：张三">
              <input
                type="text"
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
                className="w-full bg-bg-raised border border-border-main rounded-full px-5 py-2.5 text-[14px] text-text-main focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15 transition-all duration-200 font-mono"
              />
            </Field>
            <Field label="模拟群聊名称" hint="例如：技术讨论群">
              <input
                type="text"
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                className="w-full bg-bg-raised border border-border-main rounded-full px-5 py-2.5 text-[14px] text-text-main focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15 transition-all duration-200 font-mono"
              />
            </Field>
          </div>
          <Field label="模拟长期群聊记忆" hint="帮助 AI 了解当前的群聊背景（可选）">
            <textarea
              value={groupMemory}
              onChange={(e) => setGroupMemory(e.target.value)}
              placeholder="在此输入群聊历史重点记忆内容..."
              className="w-full min-h-[60px] bg-bg-raised border border-border-main rounded-2xl p-4 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15 transition-all duration-200"
            />
          </Field>
        </div>
      </details>

      <div className="flex items-center gap-4 mt-6">
        <motion.button
          whileTap={{ scale: 0.97 }}
          whileHover={{ scale: 1.02 }}
          onClick={handleTest}
          disabled={loading || !message.trim()}
          className={`px-6 py-2.5 rounded-full text-[14px] font-semibold transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer
            ${loading
              ? 'bg-bg-raised text-text-muted border border-border-main'
              : 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] border border-[#0d0d0d] dark:border-border-main hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed'}`}
        >
          {loading ? (
            <>
              <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-text-muted" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              AI 思考中...
            </>
          ) : '发送沙箱测试'}
        </motion.button>
        {latency > 0 && !loading && (
          <span className="text-xs text-text-muted font-mono">
            耗时: {(latency / 1000).toFixed(2)}s
          </span>
        )}
      </div>

      {/* Output reply */}
      {(reply || error) && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6 space-y-2"
        >
          <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted">沙箱测试输出</h4>
          {reply && (
            <div className="bg-brand-green/5 border border-brand-green/20 rounded-2xl p-5 text-sm text-text-main leading-relaxed shadow-sm font-sans whitespace-pre-wrap">
              <span className="font-semibold text-brand-green-hover dark:text-brand-green font-mono block mb-2">@{form.bot_display_name || '机器人'} :</span>
              <TypewriterText text={reply} />
            </div>
          )}
          {error && (
            <div className="bg-[#d45656]/5 border border-[#d45656]/20 rounded-2xl p-5 text-sm text-[#d45656] leading-relaxed shadow-sm font-mono whitespace-pre-wrap">
              <span className="font-bold block mb-1">测试请求出错 :</span>
              {error}
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}

export default function ConfigPanel({ activeSection, onNavigate }) {
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [importSuccess, setImportSuccess] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [form, setForm] = useState({
    ai_backend: 'deepseek', deepseek_api_key: '', deepseek_model: 'deepseek-v4-flash',
    deepseek_base_url: 'https://api.deepseek.com',
    anthropic_api_key: '', anthropic_base_url: 'https://api.anthropic.com',
    summarize_model: 'claude-haiku-4-5-20251001',
    bot_display_name: '', wechat_backend: 'wcdb', wechat_groups: '*',
    fun_enabled: true,
    proactive_enabled: false, proactive_rate_window_sec: 120,
    proactive_rate_quiet: 1.5, proactive_rate_casual: 4.0,
    proactive_rate_lively: 6.5, proactive_rate_burst: 8.5,
    sticky_mention_enabled: true, sticky_mention_ttl_sec: 60,
    log_level: 'INFO',
  })

  function handleExportConfig() {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(form, null, 2))
    const downloadAnchor = document.createElement('a')
    downloadAnchor.setAttribute("href", dataStr)
    downloadAnchor.setAttribute("download", `webot-config-${new Date().toISOString().slice(0, 10)}.json`)
    document.body.appendChild(downloadAnchor)
    downloadAnchor.click()
    downloadAnchor.remove()
  }

  function handleImportConfig(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target.result)
        const expectedKeys = ['ai_backend', 'deepseek_model', 'wechat_backend']
        const hasKeys = expectedKeys.some(k => k in parsed)
        if (!hasKeys) {
          throw new Error('无效的配置文件格式')
        }
        setForm(prev => ({
          ...prev,
          ...parsed
        }))
        setImportSuccess(true)
        setSaved(false)
        setSaveError('')
        setTimeout(() => setImportSuccess(false), 5000)
      } catch (err) {
        setSaveError('导入失败：' + err.message)
        setTimeout(() => setSaveError(''), 5000)
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

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
            wechat_groups: data.config.wechat_groups || '*',
          }))
        }
      } catch {}
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
          deepseek_base_url: form.deepseek_base_url,
          deepseek_model: form.deepseek_model,
          anthropic_api_key: form.anthropic_api_key,
          anthropic_base_url: form.anthropic_base_url,
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
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm"
          >
            <CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" />
            <span>配置已保存。需要重启机器人才能生效。</span>
          </motion.div>
        )}
        {importSuccess && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm"
          >
            <CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" />
            <span>备份配置导入成功！请确认无误后，点击"保存配置"。</span>
          </motion.div>
        )}
        {saveError && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-[#d45656]/5 border border-[#d45656]/20 rounded-full text-sm text-[#d45656] font-medium shadow-sm"
          >
            <Warning size={18} weight="fill" className="text-[#d45656]" />
            <span>{saveError}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <div style={{ minHeight: 420 }}>
        <AnimatePresence mode="wait">
          <motion.div key={activeSection} variants={pageTransition} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.18 }}>
            <div className="flex items-center gap-2.5 mb-5 pl-1">
              <div className="w-1.5 h-4.5 rounded-full shadow-sm" style={{ backgroundColor: sectionAccents[activeSection] }} />
              <h3 className="text-sm font-semibold tracking-tight text-text-main">{sectionTitles[activeSection]}</h3>
            </div>
            <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none">
              <div className="p-7">
                {activeSection === 'ai' && <AiSection form={form} update={update} />}
                {activeSection === 'identity' && <IdentitySection form={form} update={update} />}
                {activeSection === 'features' && <FeaturesSection form={form} update={update} />}
                {activeSection === 'sandbox' && <SandboxSection form={form} />}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      {activeSection !== 'sandbox' && (
        <>
          <div className="mt-8 flex items-center gap-4">
            <motion.button
              whileTap={{ scale: 0.97 }}
              whileHover={{ scale: 1.02 }}
              onClick={handleSave}
              className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide shadow-sm transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer ${
                saved
                  ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green font-semibold'
                  : 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] border border-[#0d0d0d] dark:border-border-main hover:opacity-90'
              }`}
            >
              {saved ? (
                <><CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" /> 已保存</>
              ) : (
                <><FloppyDisk size={18} /> 保存配置</>
              )}
            </motion.button>
            {saved ? (
              <span className="flex items-center gap-1.5 text-xs text-[#c37d0d] bg-[#c37d0d]/10 border border-[#c37d0d]/20 px-4 py-1.5 rounded-full font-medium">
                <Info size={14} className="text-[#c37d0d]" />
                配置已更新，重启机器人后生效
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-xs text-text-muted bg-bg-raised border border-border-main px-4 py-1.5 rounded-full font-medium">
                <Info size={14} className="text-text-muted opacity-80" />
                保存将应用所有模块的修改，重启后生效
              </span>
            )}
          </div>

          {/* Config Backup & Restore Card */}
          <div className="mt-12 pt-6 border-t border-border-main/50">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-bg-card/40 border border-border-main rounded-2xl p-5">
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-text-muted">配置备份与导入</h4>
                <p className="text-[11px] text-text-muted/80 mt-1">导出当前的机器人配置为 JSON 文件，或上传 JSON 备份恢复配置</p>
              </div>
              <div className="flex items-center gap-2.5">
                <button
                  onClick={handleExportConfig}
                  className="px-4 py-2 rounded-full border border-border-main bg-bg-main text-text-main text-xs font-semibold hover:border-text-muted/30 hover:bg-bg-raised transition-all cursor-pointer flex items-center gap-1.5"
                >
                  <DownloadSimple size={14} /> 导出备份
                </button>
                <label className="px-4 py-2 rounded-full border border-border-main bg-bg-main text-text-main text-xs font-semibold hover:border-text-muted/30 hover:bg-bg-raised transition-all cursor-pointer flex items-center gap-1.5">
                  <UploadSimple size={14} /> 导入恢复
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleImportConfig}
                    className="hidden"
                  />
                </label>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
