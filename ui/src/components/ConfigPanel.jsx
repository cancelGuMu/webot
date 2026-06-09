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
              { value: 'deepseek-v4-flash', desc: 'DeepSeek-V4-Flash', hint: '¥1 输入 · ¥2 输出 /M' },
              { value: 'deepseek-v4-pro',   desc: 'DeepSeek-V4-Pro',   hint: '¥3 输入 · ¥6 输出 /M' },
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

// ── Model info lookup ──────────────────────────────────────────────
const MODEL_INFO = {
  tiny:   { size: '~75 MB',   mem: '~200 MB', desc: '速度最快，准确率一般' },
  base:   { size: '~145 MB',  mem: '~300 MB', desc: '平衡速度与准确率' },
  small:  { size: '~488 MB',  mem: '~1 GB',   desc: '推荐 · 中文准确率高' },
  medium: { size: '~1.5 GB',  mem: '~3 GB',   desc: '高精度，需要更强硬件' },
}

function VoiceSection({ form, update }) {
  const isOpenAi = form.voice_asr_backend === 'openai_whisper'
  // dlPhase: "checking" | "not_downloaded" | "downloading" | "installing" | "done" | "error"
  const [dlPhase, setDlPhase] = useState('checking')
  const [dlPct, setDlPct] = useState(0)
  const [dlError, setDlError] = useState('')
  const didDownload = useRef(false)  // true only when user clicked "下载模型" and it finished

  function resetDlState() { setDlPhase('checking'); setDlPct(0); setDlError('') }

  // Check model status on mount and when model size changes
  useEffect(() => {
    if (isOpenAi) { setDlPhase('checking'); return }
    async function check() {
      try {
        const res = await fetch(`http://127.0.0.1:7327/api/voice/model-status?model=${form.voice_local_model || 'small'}`)
        const d = await res.json()
        if (!d.ok) { setDlPhase('error'); setDlError(d.error || '查询失败'); return }
        if (d.downloaded) { setDlPhase('done'); return }
        // If there's an active phase on the server, resume polling
        if (d.phase === 'downloading') { setDlPhase('downloading'); setDlPct(d.pct || 0) }
        else if (d.phase === 'installing') { setDlPhase('installing'); setDlPct(d.pct || 0) }
        else { setDlPhase('not_downloaded') }
      } catch { setDlPhase('checking') }
    }
    check()
  }, [form.voice_local_model, isOpenAi])

  // Poll while download/install is in progress
  const isActive = dlPhase === 'downloading' || dlPhase === 'installing'
  useEffect(() => {
    if (!isActive) return
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:7327/api/voice/model-status?model=${form.voice_local_model || 'small'}`)
        const d = await res.json()
        if (!d.ok) return
        setDlPct(d.pct || 0)
        if (d.phase === 'done' || d.downloaded) { setDlPhase('done'); setDlPct(100) }
        else if (d.phase === 'error') { setDlPhase('error'); setDlError(d.error || '失败') }
        else if (d.phase) { setDlPhase(d.phase) }
      } catch { /* keep polling */ }
    }, 1500)
    return () => clearInterval(timer)
  }, [isActive, form.voice_local_model])

  async function handleDownload() {
    setDlPhase('downloading')
    setDlPct(0)
    setDlError('')
    didDownload.current = true
    try {
      const res = await fetch('http://127.0.0.1:7327/api/voice/download-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: form.voice_local_model || 'small' }),
      })
      const d = await res.json()
      if (!d.ok) { setDlPhase('error'); setDlError(d.error || '下载启动失败') }
    } catch (e) {
      setDlPhase('error')
      setDlError('无法连接到服务器')
    }
  }

  const info = MODEL_INFO[form.voice_local_model || 'small'] || MODEL_INFO.small
  const phaseLabel = dlPhase === 'downloading' ? '下载中' : dlPhase === 'installing' ? '安装中' : ''

  return (
    <div>
      <div className="space-y-5">
        {/* ── Master toggle ───────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">启用语音识别</p>
            <p className="text-sm text-text-muted mt-1.5">
              开启后，群聊中的语音消息将自动转文字参与 AI 总结
            </p>
          </div>
          <Toggle enabled={form.voice_asr_enabled} onChange={v => update('voice_asr_enabled', v)} />
        </div>

        <AnimatePresence>
          {form.voice_asr_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="p-5 bg-bg-raised rounded-xl space-y-5">

              {/* ── Backend ─────────────────────────────────── */}
              <Field label="识别后端"
                hint={isOpenAi
                  ? 'OpenAI Whisper API — 云端识别，约 ¥0.04 / 分钟，不占本地内存'
                  : '本地 Whisper — 免费离线，模型常驻内存，无需网络'}>
                <Select value={form.voice_asr_backend} onChange={v => update('voice_asr_backend', v)} options={[
                  { value: 'local_whisper',  desc: '本地模型',  hint: '免费离线 · 推荐' },
                  { value: 'openai_whisper', desc: '云端 API',   hint: '约 ¥0.04 / 分钟' },
                ]} />
              </Field>

              {/* ── OpenAI settings ──────────────────────────── */}
              {isOpenAi && (
                <>
                  <Field label="OpenAI API Key" hint="用于调用 Whisper API；留空则复用 AI 后端配置中的 Key">
                    <Input type="password" value={form.voice_openai_api_key || ''}
                      onChange={v => update('voice_openai_api_key', v)}
                      placeholder="sk-xxxxxxxxxxxxxxxx（可选）" />
                  </Field>
                  <Field label="API Base URL" hint="自定义 API 地址；留空使用默认">
                    <Input value={form.voice_openai_base_url || ''}
                      onChange={v => update('voice_openai_base_url', v)}
                      placeholder="https://api.openai.com" />
                  </Field>
                </>
              )}

              {/* ── Local model settings ────────────────────── */}
              {!isOpenAi && (
                <>
                  <Field label="本地模型大小"
                    hint={info.desc}>
                    <Select value={form.voice_local_model || 'small'}
                      onChange={v => { update('voice_local_model', v); resetDlState() }}
                      options={[
                        { value: 'tiny',   desc: 'Tiny',   hint: `${MODEL_INFO.tiny.size} 下载 · ${MODEL_INFO.tiny.mem} 内存` },
                        { value: 'base',   desc: 'Base',   hint: `${MODEL_INFO.base.size} 下载 · ${MODEL_INFO.base.mem} 内存` },
                        { value: 'small',  desc: 'Small',  hint: `${MODEL_INFO.small.size} 下载 · ${MODEL_INFO.small.mem} 内存` },
                        { value: 'medium', desc: 'Medium', hint: `${MODEL_INFO.medium.size} 下载 · ${MODEL_INFO.medium.mem} 内存` },
                      ]} />
                  </Field>

                  {/* ── Model download card ───────────────── */}
                  <div className="bg-bg-main/60 border border-border-main/70 rounded-xl p-4">
                    <div className="flex items-start justify-between gap-4 mb-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] text-text-main font-medium">
                          {form.voice_local_model === 'small' ? 'Small' : form.voice_local_model === 'tiny' ? 'Tiny' : form.voice_local_model === 'base' ? 'Base' : 'Medium'} 模型
                        </p>
                        <p className="text-xs text-text-muted mt-1">
                          下载大小 <span className="font-mono text-text-main font-medium">{info.size}</span>，运行时约占 <span className="font-mono text-text-main font-medium">{info.mem}</span> 内存。
                          仅需下载一次，之后完全离线使用。
                        </p>
                      </div>
                      {dlPhase === 'done' ? (
                        <span className="shrink-0 px-4 py-2 rounded-full text-[13px] font-semibold bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green flex items-center gap-2">
                          <CheckCircle size={14} weight="fill" /> {didDownload.current ? '下载完成' : '已下载'}
                        </span>
                      ) : dlPhase === 'error' ? (
                        <button type="button" onClick={handleDownload}
                          className="shrink-0 px-4 py-2 rounded-full text-[13px] font-semibold bg-brand-green text-[#0d0d0d] hover:opacity-90 transition-opacity cursor-pointer flex items-center gap-2">
                          <DownloadSimple size={14} /> 重新下载
                        </button>
                      ) : dlPhase === 'checking' ? (
                        <span className="shrink-0 px-4 py-2 text-[13px] text-text-muted flex items-center gap-2">
                          <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                        </span>
                      ) : dlPhase === 'not_downloaded' ? (
                        <button type="button" onClick={handleDownload}
                          className="shrink-0 px-4 py-2 rounded-full text-[13px] font-semibold bg-brand-green text-[#0d0d0d] hover:opacity-90 transition-opacity cursor-pointer flex items-center gap-2">
                          <DownloadSimple size={14} /> 下载模型
                        </button>
                      ) : null}
                    </div>

                    {/* ── Progress bar (downloading / installing) ── */}
                    {dlPhase === 'downloading' && (
                      <div className="space-y-1.5">
                        <p className="text-xs text-text-muted font-medium">正在从 HuggingFace 下载模型文件...</p>
                        <div className="w-full h-2 bg-bg-main rounded-full overflow-hidden">
                          <div className="h-full w-1/2 rounded-full bg-brand-green animate-pulse"
                            style={{ animation: 'indeterminate 1.5s ease-in-out infinite' }} />
                        </div>
                        <p className="text-[11px] text-text-muted">首次下载约 {info.size}，请耐心等待</p>
                        <style>{`
                          @keyframes indeterminate {
                            0% { width: 0%; margin-left: 0%; }
                            50% { width: 60%; margin-left: 20%; }
                            100% { width: 0%; margin-left: 100%; }
                          }
                        `}</style>
                      </div>
                    )}
                    {dlPhase === 'installing' && (
                      <div className="space-y-1.5">
                        <p className="text-xs text-text-muted font-medium">正在加载模型到内存...</p>
                        <div className="w-full h-2 bg-bg-main rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-700 ease-out"
                            style={{ width: `${dlPct}%`, backgroundColor: '#3772cf' }} />
                        </div>
                        <p className="text-[11px] text-text-muted">
                          模型文件已下载，正在初始化 Whisper 引擎...
                        </p>
                      </div>
                    )}

                    {/* ── Done ── */}
                    {dlPhase === 'done' && (
                      <p className="text-xs text-brand-green-hover dark:text-brand-green">
                        语音模型已就绪，可正常使用语音识别功能
                      </p>
                    )}

                    {/* ── Error ── */}
                    {dlPhase === 'error' && (
                      <div className="bg-[#d45656]/5 border border-[#d45656]/20 rounded-lg px-3 py-2">
                        <p className="text-xs text-[#d45656] font-medium mb-0.5">下载失败</p>
                        <p className="text-[11px] text-[#d45656]/80 font-mono leading-relaxed break-all">
                          {dlError || '未知错误'}
                        </p>
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* ── Language ────────────────────────────────── */}
              <Field label="识别语言"
                hint="选择语音消息的主要语言。混合模式可同时识别中英文">
                <Select value={form.voice_asr_language || 'zh'}
                  onChange={v => update('voice_asr_language', v)} options={[
                  { value: 'zh', desc: '仅中文', hint: '普通话 · 推荐中文群聊' },
                  { value: 'zh-en', desc: '中英混合', hint: '同时识别中英文' },
                  { value: 'auto', desc: '自动检测', hint: '让模型自行判断语种' },
                ]} />
              </Field>

              {/* ── Simplified Chinese ───────────────────────── */}
              <div className="flex items-center justify-between">
                <div className="flex-1 mr-8">
                  <p className="text-[14px] text-text-main font-medium">繁简转换</p>
                  <p className="text-sm text-text-muted mt-1.5">
                    Whisper 有时输出繁体字，自动转为简体
                  </p>
                </div>
                <Toggle enabled={form.voice_asr_to_simplified !== false} onChange={v => update('voice_asr_to_simplified', v)} />
              </div>

            </motion.div>
          )}
        </AnimatePresence>
      </div>
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

      <Field label="微信后端" hint="Windows 推荐 WCDB；macOS 推荐 WeFlow 直读并用辅助功能发送">
        <Select value={form.wechat_backend} onChange={v => update('wechat_backend', v)} options={[
          { value: 'wcdb', desc: 'WCDB', hint: '推荐 · 原生数据库直读' },
          { value: 'mac_hybrid', desc: 'macOS WeFlow', hint: '推荐 · WeFlow 直读 + 辅助功能发送' },
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
      {/* ── Summarization ── */}
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">总结功能</p>
            <p className="text-sm text-text-muted mt-1.5">@机器人 或 触发关键词时自动总结群聊内容</p>
          </div>
          <Toggle enabled={form.summarize_enabled} onChange={v => update('summarize_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.summarize_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-bg-raised rounded-lg space-y-4">
              <ParamRow label="回溯时长" hint={"触发总结时，至少拉取最近 N 小时的消息（默认 8，范围 1-72）"}>
                <Input type="number" value={String(form.fallback_window_hours || 8)}
                  onChange={v => update('fallback_window_hours', Math.max(1, Math.min(72, parseInt(v) || 8)))} />
              </ParamRow>

              {/* ── Trigger Keywords (chip input) ── */}
              <div>
                <p className="text-[14px] text-text-main font-medium">触发关键词</p>
                <p className="text-xs text-text-muted mt-0.5 mb-2">
                  群成员发送包含任一关键词的消息时触发总结。至少保留 1 个关键词。
                </p>
                <div className="flex flex-wrap gap-2 mb-2">
                  {(form.trigger_keywords || []).map((kw, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                      {kw}
                      <button type="button"
                        disabled={(form.trigger_keywords || []).length <= 1}
                        onClick={() => {
                          const next = (form.trigger_keywords || []).filter((_, idx) => idx !== i)
                          update('trigger_keywords', next)
                        }}
                        className={`ml-0.5 leading-none text-base transition-colors ${
                          (form.trigger_keywords || []).length <= 1
                            ? 'text-text-muted cursor-not-allowed'
                            : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'
                        }`}>&times;</button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input type="text" id="new-keyword-input"
                    placeholder="输入新关键词，回车添加"
                    className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all duration-200"
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        const val = e.target.value.trim()
                        if (val && !(form.trigger_keywords || []).includes(val)) {
                          update('trigger_keywords', [...(form.trigger_keywords || []), val])
                          e.target.value = ''
                        }
                      }
                    }} />
                  <button type="button"
                    onClick={() => {
                      const input = document.getElementById('new-keyword-input')
                      if (!input) return
                      const val = input.value.trim()
                      if (val && !(form.trigger_keywords || []).includes(val)) {
                        update('trigger_keywords', [...(form.trigger_keywords || []), val])
                        input.value = ''
                      }
                    }}
                    className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">
                    添加
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Fun: Draw Lots ── */}
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">趣味抽签</p>
            <p className="text-sm text-text-muted mt-1.5">@机器人说"抽签"，随机返回运势签文（大吉/中吉/小吉/末吉/凶）</p>
          </div>
          <Toggle enabled={form.fun_enabled} onChange={v => update('fun_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.fun_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-bg-raised rounded-lg space-y-3">
              <LotsEditor />
            </motion.div>
          )}
        </AnimatePresence>
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

      {/* ── Welcome New Member ── */}
      <WelcomeSection form={form} update={update} />

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

function FeishuSection({ form, update }) {
  const keywords = Array.isArray(form.feishu_export_trigger_keywords)
    ? form.feishu_export_trigger_keywords
    : String(form.feishu_export_trigger_keywords || '')
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
  const mode = form.feishu_export_mode || 'knowledge'
  const modeLabel = mode === 'bitable' ? '多维表格' : mode === 'docx' ? '文档' : '电子表格'

  function addKeyword(value) {
    const val = value.trim()
    if (val && !keywords.includes(val)) {
      update('feishu_export_trigger_keywords', [...keywords, val])
    }
  }

  function removeKeyword(index) {
    if (keywords.length <= 1) return
    update('feishu_export_trigger_keywords', keywords.filter((_, i) => i !== index))
  }

  function clampWindow(value) {
    return Math.max(1, Math.min(168, parseInt(value) || 8))
  }

  return (
    <div>
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">飞书知识库</p>
            <p className="text-sm text-text-muted mt-1.5">自动创建多维表格，把群聊沉淀为摘要、待办、需求和日常记录</p>
          </div>
          <Toggle enabled={form.feishu_export_enabled} onChange={v => update('feishu_export_enabled', v)} />
        </div>
        <AnimatePresence>
          {form.feishu_export_enabled && (
            <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
              className="mt-3 p-4 bg-bg-raised rounded-lg space-y-4">
              <Field label="飞书应用凭证" hint="使用企业自建应用的 App ID 和 App Secret">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input value={form.feishu_app_id || ''} onChange={v => update('feishu_app_id', v)} placeholder="cli_xxxxxxxxxxxxxxxx" />
                  <Input type="password" value={form.feishu_app_secret || ''} onChange={v => update('feishu_app_secret', v)} placeholder="App Secret" />
                </div>
              </Field>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <ParamRow label="沉淀模式" hint="推荐自动知识库；已有资产写入保留为高级兼容模式">
                  <Select value={mode} onChange={v => update('feishu_export_mode', v)} options={[
                    { value: 'knowledge', desc: '自动知识库', hint: '自动建表并分类沉淀' },
                    { value: 'bitable', desc: '已有多维表格', hint: '高级：写入指定表' },
                    { value: 'spreadsheet', desc: '已有电子表格', hint: '高级：追加一行摘要' },
                    { value: 'docx', desc: '文档', hint: '高级：创建摘要文档' },
                  ]} />
                </ParamRow>
                <ParamRow label="同步窗口" hint="拉取触发前 N 小时消息，范围 1-168">
                  <Input type="number" value={String(form.feishu_export_window_hours || 8)}
                    onChange={v => update('feishu_export_window_hours', clampWindow(v))} />
                </ParamRow>
              </div>

              {mode === 'knowledge' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <ParamRow label="知识库名称" hint="首次同步时自动创建这个多维表格">
                    <Input value={form.feishu_knowledge_base_name || 'webot 群聊沉淀'}
                      onChange={v => update('feishu_knowledge_base_name', v)} placeholder="webot 群聊沉淀" />
                  </ParamRow>
                  <ParamRow label="飞书文件夹 Token" hint="可选；留空则创建到应用默认位置">
                    <Input value={form.feishu_knowledge_folder_token || ''}
                      onChange={v => update('feishu_knowledge_folder_token', v)} placeholder="fldxxxxxxxxxxxx" />
                  </ParamRow>
                  <ParamRow label="自动沉淀" hint="开启后聊天达到阈值会无感写入飞书">
                    <Toggle enabled={form.feishu_auto_sync_enabled} onChange={v => update('feishu_auto_sync_enabled', v)} />
                  </ParamRow>
                  <ParamRow label="自动阈值" hint="最近窗口内至少 N 条消息才自动沉淀">
                    <Input type="number" value={String(form.feishu_auto_sync_min_messages || 20)}
                      onChange={v => update('feishu_auto_sync_min_messages', Math.max(1, Math.min(500, parseInt(v) || 20)))} />
                  </ParamRow>
                  <ParamRow label="自动冷却" hint="同一群两次自动沉淀的最短间隔（秒）">
                    <Input type="number" value={String(form.feishu_auto_sync_cooldown_sec || 1800)}
                      onChange={v => update('feishu_auto_sync_cooldown_sec', Math.max(60, Math.min(86400, parseInt(v) || 1800)))} />
                  </ParamRow>
                </div>
              )}

              <div>
                <p className="text-[14px] text-text-main font-medium">飞书触发词</p>
                <p className="text-xs text-text-muted mt-0.5 mb-2">
                  手动兜底命令。@机器人后的文本包含任一触发词时，会立即沉淀最近群聊。
                </p>
                <div className="flex flex-wrap gap-2 mb-2">
                  {keywords.map((kw, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                      {kw}
                      <button type="button"
                        disabled={keywords.length <= 1}
                        onClick={() => removeKeyword(i)}
                        className={`ml-0.5 leading-none text-base transition-colors ${
                          keywords.length <= 1
                            ? 'text-text-muted cursor-not-allowed'
                            : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'
                        }`}>&times;</button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input type="text" id="new-feishu-keyword-input"
                    placeholder="输入新触发词，回车添加"
                    className="flex-1 bg-bg-main border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all duration-200"
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addKeyword(e.target.value)
                        e.target.value = ''
                      }
                    }} />
                  <button type="button"
                    onClick={() => {
                      const input = document.getElementById('new-feishu-keyword-input')
                      if (!input) return
                      addKeyword(input.value)
                      input.value = ''
                    }}
                    className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">
                    添加
                  </button>
                </div>
              </div>

              {mode !== 'knowledge' && (
              <div className="border-t border-border-main/50 pt-4">
                <p className="text-[14px] text-text-main font-medium mb-3">高级兼容：{modeLabel}参数</p>
                {mode === 'spreadsheet' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <ParamRow label="Spreadsheet Token" hint="飞书电子表格 URL 中的 spreadsheetToken">
                      <Input value={form.feishu_spreadsheet_token || ''} onChange={v => update('feishu_spreadsheet_token', v)} placeholder="shtcnxxxxxxxxxxxx" />
                    </ParamRow>
                    <ParamRow label="写入范围" hint="追加写入的 sheet 范围">
                      <Input value={form.feishu_spreadsheet_range || 'Sheet1!A:H'} onChange={v => update('feishu_spreadsheet_range', v)} placeholder="Sheet1!A:H" />
                    </ParamRow>
                  </div>
                )}
                {mode === 'bitable' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <ParamRow label="Bitable App Token" hint="多维表格 URL 中的 app_token">
                      <Input value={form.feishu_bitable_app_token || ''} onChange={v => update('feishu_bitable_app_token', v)} placeholder="base_xxxxxxxxxxxx" />
                    </ParamRow>
                    <ParamRow label="Table ID" hint="目标数据表 table_id">
                      <Input value={form.feishu_bitable_table_id || ''} onChange={v => update('feishu_bitable_table_id', v)} placeholder="tblxxxxxxxxxxxx" />
                    </ParamRow>
                  </div>
                )}
                {mode === 'docx' && (
                  <ParamRow label="Folder Token" hint="可选。填写后文档会创建到指定飞书文件夹">
                    <Input value={form.feishu_doc_folder_token || ''} onChange={v => update('feishu_doc_folder_token', v)} placeholder="fldxxxxxxxxxxxx" />
                  </ParamRow>
                )}
              </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}

// ── Lots Editor (抽签配置编辑器) ─────────────────────────────────────────

function LotsEditor() {
  const [data, setData] = useState(null)        // {weights, levels} | null = loading
  const [loadError, setLoadError] = useState('')
  const [expanded, setExpanded] = useState(null) // which level index is expanded
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [dirty, setDirty] = useState(false)      // unsaved changes

  // Load lots config on mount
  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('http://127.0.0.1:7327/api/lots')
        const d = await res.json()
        if (d.ok && d.config) {
          setData(d.config)
        } else {
          setLoadError(d.error || '加载失败')
        }
      } catch {
        setLoadError('无法连接服务器')
      }
    }
    load()
  }, [])

  function updateWeight(index, value) {
    const num = Math.max(1, Math.min(100, parseInt(value) || 1))
    setData(prev => {
      const next = { ...prev }
      next.weights = [...prev.weights]
      next.weights[index] = num
      return next
    })
    setDirty(true)
  }

  function updateLevelField(index, field, value) {
    setData(prev => {
      const next = { ...prev }
      next.levels = prev.levels.map((lvl, i) =>
        i === index ? { ...lvl, [field]: value } : lvl
      )
      return next
    })
    setDirty(true)
  }

  function updatePhrases(index, text) {
    const phrases = text.split('\n').filter(line => line.trim() !== '')
    setData(prev => {
      const next = { ...prev }
      next.levels = prev.levels.map((lvl, i) =>
        i === index ? { ...lvl, phrases: phrases.length > 0 ? phrases : ['(空)'] } : lvl
      )
      return next
    })
    setDirty(true)
  }

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    setSaved(false)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/lots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      const d = await res.json()
      if (d.ok) {
        setSaved(true)
        setDirty(false)
        setTimeout(() => setSaved(false), 3000)
      } else {
        setSaveError(d.error || '保存失败')
        setTimeout(() => setSaveError(''), 5000)
      }
    } catch {
      setSaveError('无法连接到服务器')
      setTimeout(() => setSaveError(''), 5000)
    }
    setSaving(false)
  }

  async function handleRestoreDefaults() {
    setSaving(true)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/lots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weights: [], levels: [] }), // empty → server uses defaults
      })
      const d = await res.json()
      if (d.ok) {
        // Reload to get defaults
        const reload = await fetch('http://127.0.0.1:7327/api/lots')
        const rd = await reload.json()
        if (rd.ok && rd.config) {
          setData(rd.config)
          setDirty(false)
          setSaved(true)
          setTimeout(() => setSaved(false), 3000)
        }
      } else {
        setSaveError(d.error || '恢复失败')
        setTimeout(() => setSaveError(''), 5000)
      }
    } catch {
      setSaveError('无法连接到服务器')
      setTimeout(() => setSaveError(''), 5000)
    }
    setSaving(false)
  }

  // Loading / Error states
  if (loadError) {
    return (
      <div className="text-xs text-[#d45656] bg-[#d45656]/5 border border-[#d45656]/20 rounded-xl px-4 py-3">
        抽签配置加载失败：{loadError}
      </div>
    )
  }
  if (!data) {
    return (
      <div className="text-xs text-text-muted py-2 flex items-center gap-2">
        <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        加载签文配置中...
      </div>
    )
  }

  const totalWeight = data.weights.reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-text-muted">
          自定义各等级签文与权重。当前总权重：<span className="font-semibold text-text-main">{totalWeight}</span>
          （各等级概率 = 权重 ÷ 总权重）
        </p>
      </div>

      {data.levels.map((level, i) => {
        const isOpen = expanded === i
        const probability = totalWeight > 0 ? ((data.weights[i] / totalWeight) * 100).toFixed(1) : '0.0'
        return (
          <div key={i} className="bg-bg-main/60 border border-border-main/70 rounded-xl overflow-hidden transition-all">
            {/* Summary row — click to expand/collapse */}
            <button
              type="button"
              onClick={() => setExpanded(isOpen ? null : i)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-bg-raised/50 transition-colors cursor-pointer text-left"
            >
              <span className="text-lg">{level.emoji || '❓'}</span>
              <span className="text-sm font-semibold text-text-main flex-1">{level.name}</span>
              <span className="text-xs text-text-muted font-mono bg-bg-raised border border-border-main px-2 py-0.5 rounded-full">
                权重 {data.weights[i]} · {probability}%
              </span>
              <span className="text-xs text-text-muted font-mono bg-bg-raised border border-border-main px-2 py-0.5 rounded-full">
                {level.phrases.length} 条签文
              </span>
              <span className={`text-text-muted text-xs transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}>›</span>
            </button>

            {/* Expanded detail */}
            {isOpen && (
              <div className="px-4 pb-4 pt-1 border-t border-border-main/40 space-y-3 bg-bg-raised/30">
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-text-muted font-medium mb-1">等级名称</label>
                    <input
                      type="text"
                      value={level.name}
                      onChange={e => updateLevelField(i, 'name', e.target.value)}
                      className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-text-muted font-medium mb-1">Emoji</label>
                    <input
                      type="text"
                      value={level.emoji || ''}
                      onChange={e => updateLevelField(i, 'emoji', e.target.value)}
                      className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-text-muted font-medium mb-1">权重 (1-100)</label>
                    <input
                      type="number"
                      min="1" max="100"
                      value={data.weights[i]}
                      onChange={e => updateWeight(i, e.target.value)}
                      className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all font-mono"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-[11px] text-text-muted font-medium mb-1">
                    签文列表（每行一条，共 {level.phrases.length} 条）
                  </label>
                  <textarea
                    value={level.phrases.join('\n')}
                    onChange={e => updatePhrases(i, e.target.value)}
                    rows={Math.max(6, Math.min(level.phrases.length + 2, 16))}
                    className="w-full bg-bg-main border border-border-main rounded-xl p-3 text-[13px] text-text-main leading-relaxed focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all font-mono resize-y"
                  />
                </div>
              </div>
            )}
          </div>
        )
      })}

      {/* Action buttons */}
      <div className="flex items-center gap-3 pt-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className={`px-5 py-2 rounded-full text-[13px] font-semibold transition-all cursor-pointer flex items-center gap-2 ${
            saved
              ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green'
              : dirty
                ? 'bg-brand-green text-[#0d0d0d] hover:opacity-90'
                : 'bg-bg-main border border-border-main text-text-muted hover:text-text-main'
          }`}
        >
          {saving ? (
            <><svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> 保存中</>
          ) : saved ? (
            <><CheckCircle size={14} weight="fill" /> 已保存</>
          ) : (
            <><FloppyDisk size={14} /> {dirty ? '保存抽签配置' : '保存'}</>
          )}
        </button>
        <button
          type="button"
          onClick={handleRestoreDefaults}
          disabled={saving}
          className="px-4 py-2 rounded-full text-[12px] text-text-muted hover:text-[#d45656] border border-border-main hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium"
        >
          恢复默认签文
        </button>
        {saveError && (
          <span className="text-xs text-[#d45656] font-mono">{saveError}</span>
        )}
      </div>
    </div>
  )
}

const sectionTitles = { ai: 'AI 后端配置', voice: '语音识别配置', identity: '机器人身份', data: '数据路径', sandbox: '提示词沙箱' }
const sectionAccents = { ai: '#18E299', voice: '#10b981', identity: '#3772cf', data: '#18E299', sandbox: '#8b5cf6' }

// ── Data Path Section (微信数据目录配置) ──────────────────────────────

function DataPathSection({ form, update, detectedDataDir }) {
  const [browseOpen, setBrowseOpen] = useState(false)
  const [browsePath, setBrowsePath] = useState('')
  const [browseEntries, setBrowseEntries] = useState([])
  const [browseLoading, setBrowseLoading] = useState(false)
  const [browseError, setBrowseError] = useState('')
  const [browseInput, setBrowseInput] = useState('')
  const [detectResult, setDetectResult] = useState(null)
  const [detecting, setDetecting] = useState(false)
  const [detectError, setDetectError] = useState('')

  // ── Browse API ────────────────────────────────────────────────

  async function loadBrowseDir(path) {
    setBrowseLoading(true)
    setBrowseError('')
    setDetectResult(null)
    try {
      const params = path ? `?path=${encodeURIComponent(path)}` : ''
      const res = await fetch(`http://127.0.0.1:7327/api/browse${params}`)
      const d = await res.json()
      if (d.ok) {
        setBrowsePath(d.current_path || '')
        setBrowseInput(d.current_path || '')
        setBrowseEntries(d.entries || [])
      } else {
        setBrowseError(d.error || '无法读取目录')
      }
    } catch {
      setBrowseError('无法连接到服务器')
    }
    setBrowseLoading(false)
  }

  function openBrowse() {
    const initialPath = form.wechat_data_dir || detectedDataDir || ''
    setBrowseInput(initialPath)
    setBrowseOpen(true)
    loadBrowseDir(initialPath)
  }

  function handleBrowseGo() {
    const trimmed = browseInput.trim()
    if (trimmed) {
      setBrowseError('')
      loadBrowseDir(trimmed)
    }
  }

  function handleBrowseInputKeyDown(e) {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleBrowseGo()
    }
  }

  function navigateUp() {
    const parent = browsePath.split('\\').slice(0, -1).join('\\')
    if (parent.length >= 1) {
      loadBrowseDir(parent)
    }
  }

  function navigateTo(entryPath) {
    loadBrowseDir(entryPath)
  }

  function selectCurrentPath() {
    update('wechat_data_dir', browsePath)
    setBrowseOpen(false)
    setDetectResult(null)
  }

  // ── Detect API ────────────────────────────────────────────────

  async function handleDetect() {
    const path = (form.wechat_data_dir || '').trim()
    if (!path) {
      setDetectError('请先输入或选择目录路径')
      setTimeout(() => setDetectError(''), 4000)
      return
    }
    setDetecting(true)
    setDetectError('')
    setDetectResult(null)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/wechat-data-dir/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      const d = await res.json()
      if (d.ok) {
        setDetectResult(d)
      } else {
        setDetectError(d.error || '检测失败')
        setTimeout(() => setDetectError(''), 5000)
      }
    } catch {
      setDetectError('无法连接到服务器')
      setTimeout(() => setDetectError(''), 5000)
    }
    setDetecting(false)
  }

  const hasCustomPath = (form.wechat_data_dir || '').trim().length > 0

  return (
    <div>
      <Field label="微信数据目录"
        hint="微信聊天记录存储的父目录（包含 wxid_* 文件夹）。留空则自动从 Documents 检测。">
        <div className="flex items-start gap-2">
          <div className="flex-1 relative">
            <input
              type="text"
              value={form.wechat_data_dir || ''}
              onChange={v => { update('wechat_data_dir', v); setDetectResult(null) }}
              placeholder={detectedDataDir || '自动检测中...'}
              className="w-full bg-bg-raised border border-border-main rounded-full pl-5 pr-5 py-2.5 text-[14px] text-text-main
                         placeholder:text-text-muted/65 font-mono tabular-nums
                         focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15
                         transition-all duration-200
                         hover:border-text-muted/30 dark:hover:border-text-muted/40"
            />
            {hasCustomPath && (
              <button
                type="button"
                onClick={() => { update('wechat_data_dir', ''); setDetectResult(null); setDetectError('') }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted/60 hover:text-[#d45656] text-lg leading-none transition-colors cursor-pointer"
                title="清除自定义路径"
              >&times;</button>
            )}
          </div>
          <button
            type="button"
            onClick={openBrowse}
            className="shrink-0 px-4 py-2.5 bg-bg-main border border-border-main rounded-full text-[13px] text-text-main font-medium hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer"
          >
            浏览...
          </button>
          {hasCustomPath && (
            <button
              type="button"
              onClick={handleDetect}
              disabled={detecting}
              className="shrink-0 px-4 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-[13px] text-brand-green-hover dark:text-brand-green font-semibold hover:bg-brand-green/10 transition-colors cursor-pointer disabled:opacity-50"
            >
              {detecting ? (
                <span className="flex items-center gap-1.5">
                  <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  检测中
                </span>
              ) : '检测'}</button>
          )}
        </div>
      </Field>

      {/* Detection result */}
      {detectResult && (
        <div className={`mt-3 p-4 rounded-2xl border ${
          detectResult.found
            ? 'bg-brand-green-light border-brand-green/20'
            : 'bg-[#c37d0d]/5 border-[#c37d0d]/20'
        }`}>
          {detectResult.found ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <CheckCircle size={18} weight="fill" className="text-brand-green-hover dark:text-brand-green" />
                <span className="text-sm font-semibold text-brand-green-hover dark:text-brand-green">{detectResult.message}</span>
              </div>
              {detectResult.accounts.map((acct, i) => (
                <div key={i} className="flex items-center gap-3 text-xs font-mono bg-bg-main/60 border border-border-main rounded-xl px-3 py-2">
                  <span className="text-text-main font-semibold">{acct.wxid}</span>
                  <span className="text-text-muted">·</span>
                  <span className={acct.has_session_db ? 'text-brand-green-hover dark:text-brand-green' : 'text-[#d45656]'}>
                    {acct.has_session_db ? '✓ session.db 已就绪' : '✗ 未找到 session.db'}
                  </span>
                </div>
              ))}
              <p className="text-[11px] text-text-muted mt-1">确认无误后点击下方「保存配置」并重启机器人即可生效</p>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Warning size={18} weight="fill" className="text-[#c37d0d]" />
              <span className="text-sm text-[#c37d0d]">{detectResult.message}</span>
            </div>
          )}
        </div>
      )}

      {detectError && (
        <div className="mt-3 flex items-center gap-2 px-4 py-2.5 bg-[#d45656]/5 border border-[#d45656]/20 rounded-full text-sm text-[#d45656]">
          <Warning size={16} weight="fill" className="text-[#d45656]" />
          <span>{detectError}</span>
        </div>
      )}

      {detectedDataDir && !hasCustomPath && (
        <div className="mt-3 flex items-center gap-2 px-3 py-2 bg-brand-green-light border border-brand-green/20 rounded-full text-xs text-brand-green-hover dark:text-brand-green font-medium">
          <CheckCircle size={14} weight="fill" />
          <span className="truncate font-mono">自动检测: {detectedDataDir}</span>
        </div>
      )}
      {!detectedDataDir && !hasCustomPath && (
        <p className="text-xs text-text-muted mt-3 leading-relaxed">
          ⚠ 未检测到默认微信数据目录，请手动指定包含 <code className="bg-bg-raised px-1.5 py-0.5 rounded font-mono text-[11px]">wxid_*</code> 文件夹的父目录
        </p>
      )}
      {hasCustomPath && (
        <p className="text-xs text-text-muted mt-3 leading-relaxed">
          💡 已设置自定义路径。留空则恢复自动检测（{detectedDataDir || '默认 Documents 目录'}）
        </p>
      )}

      {/* ── Directory Browser Modal ────────────────────────────────── */}
      {browseOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0d0d0d]/60 backdrop-blur-sm" onClick={() => setBrowseOpen(false)}>
          <div
            className="bg-bg-card border border-border-main rounded-2xl shadow-2xl w-[520px] max-h-[520px] flex flex-col overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-border-main/60">
              <h4 className="text-sm font-semibold text-text-main">选择微信数据目录</h4>
              <button
                type="button"
                onClick={() => setBrowseOpen(false)}
                className="text-text-muted hover:text-text-main transition-colors cursor-pointer leading-none text-lg"
              >&times;</button>
            </div>

            {/* Path input (paste-able) */}
            <div className="px-5 py-3 border-b border-border-main/40">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={browseInput}
                  onChange={e => setBrowseInput(e.target.value)}
                  onKeyDown={handleBrowseInputKeyDown}
                  placeholder="粘贴或输入路径，回车跳转..."
                  className="flex-1 bg-bg-raised border border-border-main rounded-full px-4 py-2 text-[13px] text-text-main placeholder:text-text-muted/55 font-mono
                             focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15
                             transition-all duration-200 hover:border-text-muted/30"
                />
                <button
                  type="button"
                  onClick={handleBrowseGo}
                  disabled={!browseInput.trim()}
                  className="shrink-0 px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-full text-[13px] text-brand-green-hover dark:text-brand-green font-semibold hover:bg-brand-green/10 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default"
                >
                  跳转
                </button>
              </div>
            </div>

            {/* Path breadcrumb */}
            <div className="px-5 py-2.5 bg-bg-raised/50 border-b border-border-main/40">
              <div className="flex items-center gap-1.5 text-xs font-mono text-text-muted">
                <button
                  type="button"
                  onClick={navigateUp}
                  disabled={!browsePath || browsePath.length <= 3}
                  className="text-text-muted hover:text-text-main disabled:opacity-30 disabled:cursor-default cursor-pointer transition-colors"
                  title="上级目录"
                >↑</button>
                <span className="truncate">{browsePath || '此电脑'}</span>
              </div>
            </div>

            {/* Entry list */}
            <div className="flex-1 overflow-y-auto px-2 py-1.5">
              {browseLoading ? (
                <div className="flex items-center justify-center py-12">
                  <svg className="animate-spin h-5 w-5 text-text-muted" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                </div>
              ) : browseError ? (
                <div className="p-4 text-xs text-[#d45656] text-center">{browseError}</div>
              ) : browseEntries.length === 0 ? (
                <div className="p-4 text-xs text-text-muted text-center">此目录为空</div>
              ) : (
                browseEntries.filter(e => e.is_dir).map((entry, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => navigateTo(entry.path)}
                    className="w-full text-left px-3 py-2 rounded-xl text-[13px] text-text-main hover:bg-bg-raised transition-colors cursor-pointer flex items-center gap-2.5 font-mono"
                  >
                    <span className="text-base shrink-0">📁</span>
                    <span className="truncate">{entry.name}</span>
                  </button>
                ))
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-3.5 border-t border-border-main/60 flex items-center justify-between">
              <p className="text-[11px] text-text-muted truncate max-w-[340px] font-mono">
                当前: {browsePath || '—'}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setBrowseOpen(false)}
                  className="px-4 py-2 rounded-full border border-border-main bg-bg-main text-xs text-text-muted hover:text-text-main transition-colors cursor-pointer font-medium"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={selectCurrentPath}
                  className="px-4 py-2 rounded-full bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] text-xs font-semibold hover:opacity-90 transition-opacity cursor-pointer"
                >
                  选择此目录
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Welcome Section (欢迎新人配置) ──────────────────────────────────────

function WelcomeSection({ form, update }) {
  const [templates, setTemplates] = useState([])
  const [groupMapping, setGroupMapping] = useState({})
  const [defaultTemplate, setDefaultTemplate] = useState('tpl_default')
  const [activeTab, setActiveTab] = useState(0)
  const [groups, setGroups] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const textareaRef = useRef(null)

  // Load templates + groups on mount
  useEffect(() => {
    async function load() {
      try {
        const [tplRes, grpRes] = await Promise.all([
          fetch('http://127.0.0.1:7327/api/welcome/templates'),
          fetch('http://127.0.0.1:7327/api/nicknames/groups'),
        ])
        const tplData = await tplRes.json()
        const grpData = await grpRes.json()

        if (tplData.ok && tplData.data) {
          setTemplates(tplData.data.templates || [])
          setGroupMapping(tplData.data.group_mapping || {})
          setDefaultTemplate(tplData.data.default_template || 'tpl_default')
        }
        if (grpData.ok) {
          setGroups(grpData.groups || [])
        }
      } catch {}
      setLoaded(true)
    }
    load()
  }, [])

  // ── Template CRUD helpers ───────────────────────────────────

  function updateTemplate(index, field, value) {
    setTemplates(prev => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  function addTemplate() {
    const id = 'tpl_' + Date.now()
    setTemplates(prev => [...prev, { id, name: '新模板', message: '欢迎 @{new_member} 加入群聊！🎉' }])
    setActiveTab(templates.length)
  }

  function deleteTemplate(index) {
    if (templates.length <= 1) return
    setTemplates(prev => {
      const next = prev.filter((_, i) => i !== index)
      // Update group mappings that referenced the deleted template
      const deletedId = prev[index].id
      if (deletedId === defaultTemplate) {
        setDefaultTemplate(next[0]?.id || 'tpl_default')
      }
      setGroupMapping(prevMapping => {
        const nextMapping = { ...prevMapping }
        for (const [chatId, tplId] of Object.entries(nextMapping)) {
          if (tplId === deletedId) {
            delete nextMapping[chatId]
          }
        }
        return nextMapping
      })
      return next
    })
    if (activeTab >= index) {
      setActiveTab(Math.max(0, activeTab - 1))
    }
  }

  // ── Cursor-position variable insertion ───────────────────────

  function insertVariable() {
    const ta = textareaRef.current
    if (!ta) return
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const msg = templates[activeTab]?.message || ''
    const newText = msg.slice(0, start) + '{new_member}' + msg.slice(end)
    updateTemplate(activeTab, 'message', newText)
    requestAnimationFrame(() => {
      ta.focus()
      ta.setSelectionRange(start + 13, start + 13)
    })
  }

  // ── Group mapping helpers ────────────────────────────────────

  function updateGroupMapping(chatId, templateId) {
    setGroupMapping(prev => {
      if (templateId === '__default__') {
        // "使用默认" → remove from mapping
        const next = { ...prev }
        delete next[chatId]
        return next
      }
      return { ...prev, [chatId]: templateId }
    })
  }

  function resetGroupMapping(chatId) {
    setGroupMapping(prev => {
      const next = { ...prev }
      delete next[chatId]
      return next
    })
  }

  // ── Save ─────────────────────────────────────────────────────

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    setSaved(false)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/welcome/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          templates,
          group_mapping: groupMapping,
          default_template: defaultTemplate,
        }),
      })
      const d = await res.json()
      if (d.ok) {
        setSaved(true)
        setTimeout(() => setSaved(false), 3000)
      } else {
        setSaveError(d.error || '保存失败')
        setTimeout(() => setSaveError(''), 5000)
      }
    } catch {
      setSaveError('无法连接到服务器')
      setTimeout(() => setSaveError(''), 5000)
    }
    setSaving(false)
  }

  // ── Build group assignment data ──────────────────────────────

  // Groups with explicit assignments
  const assignedGroups = groups.filter(g => groupMapping.hasOwnProperty(g.chat_id))
  // Groups without explicit assignments (use default)
  const unassignedGroups = groups.filter(g => !groupMapping.hasOwnProperty(g.chat_id))

  const currentTemplate = templates[activeTab] || {}
  const templateOptions = [
    ...templates.map(t => ({ value: t.id, desc: t.name, hint: '' })),
    { value: '__disabled__', desc: '关闭欢迎', hint: '该群不发送欢迎消息' },
  ]
  const groupTemplateOptions = [
    { value: '__default__', desc: '使用默认模板', hint: '' },
    ...templateOptions,
  ]

  if (!loaded) {
    return (
      <div className="py-4 border-b border-border-main/50">
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-8">
            <p className="text-[15px] text-text-main font-medium">欢迎新人</p>
            <p className="text-sm text-text-muted mt-1.5">检测到新成员加入群聊时，自动发送欢迎消息</p>
          </div>
          <Toggle enabled={form.welcome_enabled} onChange={v => update('welcome_enabled', v)} />
        </div>
      </div>
    )
  }

  return (
    <div className="py-4 border-b border-border-main/50">
      <div className="flex items-center justify-between">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-text-main font-medium">欢迎新人</p>
          <p className="text-sm text-text-muted mt-1.5">检测到新成员加入群聊时，自动发送欢迎消息</p>
        </div>
        <Toggle enabled={form.welcome_enabled} onChange={v => update('welcome_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.welcome_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="mt-3 p-4 bg-bg-raised rounded-lg space-y-4">

            {/* ── Template tabs ──────────────────────────────── */}
            <div>
              <p className="text-[13px] text-text-main font-medium mb-2">欢迎词模板</p>
              <div className="flex flex-wrap items-center gap-1.5 mb-3">
                {templates.map((tpl, i) => (
                  <span
                    key={tpl.id}
                    onClick={() => setActiveTab(i)}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[13px] font-medium transition-colors cursor-pointer select-none ${
                      i === activeTab
                        ? 'bg-brand-green text-[#0d0d0d]'
                        : 'bg-bg-main border border-border-main text-text-muted hover:text-text-main hover:border-text-muted/40'
                    }`}
                  >
                    {tpl.name}
                    {templates.length > 1 && (
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); deleteTemplate(i) }}
                        className={`ml-0.5 leading-none text-base transition-colors cursor-pointer ${
                          i === activeTab
                            ? 'text-[#0d0d0d]/60 hover:text-[#d45656]'
                            : 'text-text-muted/50 hover:text-[#d45656]'
                        }`}
                        title="删除模板"
                      >&times;</button>
                    )}
                  </span>
                ))}
                <button
                  type="button"
                  onClick={addTemplate}
                  className="px-3 py-1.5 rounded-lg text-[13px] font-medium bg-bg-main border border-dashed border-border-main text-text-muted hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer"
                >
                  + 新建
                </button>
              </div>

              {/* ── Template editor ──────────────────────────── */}
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] text-text-muted font-medium mb-1">模板名称</label>
                  <input
                    type="text"
                    value={currentTemplate.name || ''}
                    onChange={e => updateTemplate(activeTab, 'name', e.target.value)}
                    className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-2 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
                  />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-text-muted font-medium">
                      欢迎词内容（<code className="bg-bg-main px-1 rounded font-mono text-[11px]">{'{new_member}'}</code> 代表新成员 ID）
                    </label>
                    <button
                      type="button"
                      onClick={insertVariable}
                      className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors cursor-pointer"
                      title="在光标位置插入新成员ID变量"
                    >
                      + 插入新成员 ID
                    </button>
                  </div>
                  <textarea
                    ref={textareaRef}
                    value={currentTemplate.message || ''}
                    onChange={e => updateTemplate(activeTab, 'message', e.target.value)}
                    rows={3}
                    className="w-full bg-bg-main border border-border-main rounded-xl p-3 text-[13px] text-text-main leading-relaxed focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all resize-y font-mono"
                    placeholder="欢迎 @{new_member} 加入群聊！🎉"
                  />
                </div>
              </div>
            </div>

            {/* ── Group assignment ───────────────────────────── */}
            <div className="border-t border-border-main/40 pt-4">
              <p className="text-[13px] text-text-main font-medium mb-2">群聊分配</p>
              <p className="text-[11px] text-text-muted mb-3">
                未单独配置的群聊使用默认模板。设为「关闭欢迎」则不发送。
              </p>

              {/* Default template selector */}
              <div className="flex items-center gap-3 mb-3 px-3 py-2 bg-bg-main/60 rounded-xl border border-border-main/50">
                <span className="text-[12px] text-text-muted shrink-0">默认模板</span>
                <span className="text-[11px] text-text-muted/60 flex-1">未单独配置的群聊使用此模板</span>
                <div className="w-40">
                  <SmallSelect
                    value={defaultTemplate}
                    onChange={v => setDefaultTemplate(v)}
                    options={templates.map(t => ({ value: t.id, desc: t.name }))}
                  />
                </div>
              </div>

              {/* Explicit group assignments */}
              {assignedGroups.map(g => (
                <div key={g.chat_id} className="flex items-center gap-3 mb-2 px-3 py-2 bg-bg-main/60 rounded-xl border border-border-main/50">
                  <span className="text-[12px] text-text-main truncate flex-1 font-mono" title={g.group_name || g.chat_id}>
                    {g.group_name || g.chat_id}
                  </span>
                  <div className="w-40">
                    <SmallSelect
                      value={groupMapping[g.chat_id]}
                      onChange={v => updateGroupMapping(g.chat_id, v)}
                      options={groupTemplateOptions}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => resetGroupMapping(g.chat_id)}
                    className="text-text-muted/50 hover:text-[#d45656] text-sm leading-none cursor-pointer transition-colors shrink-0"
                    title="恢复为默认模板"
                  >&times;</button>
                </div>
              ))}

              {/* Add group assignment — dropdown picker */}
              {unassignedGroups.length > 0 && (
                <AddGroupPicker
                  unassignedGroups={unassignedGroups}
                  defaultTemplate={defaultTemplate}
                  onAdd={(chatId, templateId) => updateGroupMapping(chatId, templateId)}
                />
              )}
            </div>

            {/* ── Save button ───────────────────────────────── */}
            <div className="flex items-center gap-3 pt-1">
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className={`px-4 py-2 rounded-full text-[13px] font-semibold transition-all cursor-pointer flex items-center gap-2 ${
                  saved
                    ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green'
                    : 'bg-brand-green text-[#0d0d0d] hover:opacity-90'
                }`}
              >
                {saving ? (
                  <><svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> 保存中</>
                ) : saved ? (
                  <><CheckCircle size={14} weight="fill" /> 已保存</>
                ) : (
                  <><FloppyDisk size={14} /> 保存模板配置</>
                )}
              </button>
              {saveError && (
                <span className="text-xs text-[#d45656] font-mono">{saveError}</span>
              )}
              <span className="text-[11px] text-text-muted">
                模板配置独立保存，无需重启机器人
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── AddGroupPicker — dropdown to pick an unassigned group ──────────

function AddGroupPicker({ unassignedGroups, defaultTemplate, onAdd }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    function handleClick(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus()
      setSearch('')
    }
  }, [open])

  const filtered = unassignedGroups.filter(g => {
    if (!search.trim()) return true
    const q = search.trim().toLowerCase()
    return (g.group_name || g.chat_id).toLowerCase().includes(q)
  })

  function handleSelect(chatId) {
    onAdd(chatId, defaultTemplate)
    setOpen(false)
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="px-3 py-2 rounded-xl text-[12px] text-text-muted bg-bg-main border border-dashed border-border-main hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer w-full text-left"
      >
        + 为群聊单独配置（{unassignedGroups.length} 个群聊未配置）
      </button>
      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-bg-card border border-border-main rounded-xl shadow-lg overflow-hidden">
          {/* Search input */}
          <div className="px-3 py-2 border-b border-border-main/40">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索群聊名称..."
              className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[12px] text-text-main placeholder:text-text-muted/55 focus:outline-none focus:border-brand-green transition-colors"
            />
          </div>
          {/* Group list */}
          <div className="max-h-48 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-[12px] text-text-muted text-center">
                {search.trim() ? '无匹配群聊' : '所有群聊已配置'}
              </div>
            ) : (
              filtered.map(g => (
                <button
                  key={g.chat_id}
                  type="button"
                  onClick={() => handleSelect(g.chat_id)}
                  className="w-full text-left px-3 py-2 text-[12px] text-text-main hover:bg-bg-raised transition-colors cursor-pointer flex items-center justify-between"
                >
                  <span className="truncate font-mono" title={g.group_name || g.chat_id}>
                    {g.group_name || g.chat_id}
                  </span>
                  <span className="text-[10px] text-text-muted shrink-0 ml-2">
                    {g.member_count ? `${g.member_count} 人` : ''}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Small Select (for group assignment dropdowns) ─────────────────

function SmallSelect({ value, onChange, options }) {
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
        className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[12px] text-text-main text-left focus:outline-none focus:border-brand-green transition-colors cursor-pointer hover:border-text-muted/30 flex items-center justify-between"
      >
        <span className="truncate">{selected ? selected.desc : value}</span>
        <span className={`text-text-muted text-xs transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>&#8250;</span>
      </button>
      {open && (
        <motion.div
          initial={{ opacity: 0, y: -2 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute z-50 left-0 right-0 mt-1 bg-bg-card border border-border-main rounded-xl shadow-lg overflow-hidden max-h-48 overflow-y-auto"
        >
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-3 py-2 text-[12px] transition-colors cursor-pointer ${
                value === opt.value
                  ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green font-semibold'
                  : 'text-text-main hover:bg-bg-raised'
              }`}
            >
              {opt.desc}
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}

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
    summarize_enabled: true, fallback_window_hours: 8, trigger_keywords: [],
    welcome_enabled: false,
    feishu_export_enabled: false, feishu_app_id: '', feishu_app_secret: '',
    feishu_export_mode: 'knowledge', feishu_export_window_hours: 8,
    feishu_auto_sync_enabled: false, feishu_auto_sync_min_messages: 20,
    feishu_auto_sync_cooldown_sec: 1800,
    feishu_knowledge_base_name: 'webot 群聊沉淀', feishu_knowledge_folder_token: '',
    feishu_export_trigger_keywords: ['同步到飞书', '导出到飞书', '写到飞书', '沉淀到飞书'],
    feishu_spreadsheet_token: '', feishu_spreadsheet_range: 'Sheet1!A:H',
    feishu_bitable_app_token: '', feishu_bitable_table_id: '',
    feishu_doc_folder_token: '',
    log_level: 'INFO', wechat_data_dir: '',
    voice_asr_enabled: false, voice_asr_backend: 'local_whisper', voice_asr_language: 'zh',
    voice_openai_api_key: '', voice_openai_base_url: '', voice_local_model: 'small',
    voice_asr_to_simplified: true,
  })

  async function handleExportConfig() {
    try {
      const res = await fetch('http://127.0.0.1:7327/api/config/export')
      if (!res.ok) throw new Error('导出请求失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const downloadAnchor = document.createElement('a')
      downloadAnchor.setAttribute("href", url)
      downloadAnchor.setAttribute("download", `webot-config-${new Date().toISOString().slice(0, 10)}.json`)
      document.body.appendChild(downloadAnchor)
      downloadAnchor.click()
      downloadAnchor.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      setSaveError('导出失败：' + e.message)
      setTimeout(() => setSaveError(''), 5000)
    }
  }

  async function handleImportConfig(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async (event) => {
      try {
        const parsed = JSON.parse(event.target.result)
        const expectedKeys = ['ai_backend', 'deepseek_model', 'wechat_backend']
        const hasKeys = expectedKeys.some(k => k in parsed)
        if (!hasKeys) {
          throw new Error('无效的配置文件格式')
        }
        // Update local form state immediately for UI feedback
        setForm(prev => ({ ...prev, ...parsed }))
        // Persist to server
        const res = await fetch('http://127.0.0.1:7327/api/config/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(parsed),
        })
        const data = await res.json()
        if (data.ok) {
          setImportSuccess(true)
          setSaved(false)
          setSaveError('')
          setTimeout(() => setImportSuccess(false), 5000)
        } else {
          throw new Error(data.error || '写入失败')
        }
      } catch (err) {
        setSaveError('导入失败：' + err.message)
        setTimeout(() => setSaveError(''), 5000)
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  // Detected default data dir (auto-detected, shown as placeholder)
  const [detectedDataDir, setDetectedDataDir] = useState('')

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
          if (data.detected_data_dir) {
            setDetectedDataDir(data.detected_data_dir)
          }
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
          summarize_enabled: form.summarize_enabled,
          fallback_window_hours: form.fallback_window_hours,
          trigger_keywords: form.trigger_keywords,
          welcome_enabled: form.welcome_enabled,
          feishu_export_enabled: form.feishu_export_enabled,
          feishu_app_id: form.feishu_app_id,
          feishu_app_secret: form.feishu_app_secret,
          feishu_export_mode: form.feishu_export_mode,
          feishu_export_window_hours: form.feishu_export_window_hours,
          feishu_auto_sync_enabled: form.feishu_auto_sync_enabled,
          feishu_auto_sync_min_messages: form.feishu_auto_sync_min_messages,
          feishu_auto_sync_cooldown_sec: form.feishu_auto_sync_cooldown_sec,
          feishu_knowledge_base_name: form.feishu_knowledge_base_name,
          feishu_knowledge_folder_token: form.feishu_knowledge_folder_token,
          feishu_export_trigger_keywords: form.feishu_export_trigger_keywords,
          feishu_spreadsheet_token: form.feishu_spreadsheet_token,
          feishu_spreadsheet_range: form.feishu_spreadsheet_range,
          feishu_bitable_app_token: form.feishu_bitable_app_token,
          feishu_bitable_table_id: form.feishu_bitable_table_id,
          feishu_doc_folder_token: form.feishu_doc_folder_token,
          log_level: form.log_level,
          wechat_data_dir: form.wechat_data_dir,
          voice_asr_enabled: form.voice_asr_enabled,
          voice_asr_backend: form.voice_asr_backend,
          voice_asr_language: form.voice_asr_language,
          voice_openai_api_key: form.voice_openai_api_key,
          voice_openai_base_url: form.voice_openai_base_url,
          voice_local_model: form.voice_local_model,
          voice_asr_to_simplified: form.voice_asr_to_simplified,
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
                {activeSection === 'voice' && <VoiceSection form={form} update={update} />}
                {activeSection === 'identity' && <IdentitySection form={form} update={update} />}
                {activeSection === 'data' && <DataPathSection form={form} update={update} detectedDataDir={detectedDataDir} />}
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
