import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, ArrowRight, Spinner, XCircle, Warning } from '@phosphor-icons/react'
import { Field, Toggle, Select, Input, spring } from './SharedComponents'

const API = 'http://127.0.0.1:7327'

// ── Step 1: Key Extraction & Diagnostics ──────────────────────────────

export function Step1Prepare({ data, updateData, onDone }) {
  const [phase, setPhase] = useState('idle') // idle | extracting | done | timeout | error
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [isManual, setIsManual] = useState(false)
  const [manualKey, setManualKey] = useState(data.key || '')
  const [manualWxid, setManualWxid] = useState(data.wxid || '')
  const [manualDbPath, setManualDbPath] = useState(data.db_path || '')

  // Pre-flight diagnostics state
  const [diagnostics, setDiagnostics] = useState(null)
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(true)
  const [diagnosticsError, setDiagnosticsError] = useState('')

  async function fetchDiagnostics() {
    setDiagnosticsLoading(true)
    setDiagnosticsError('')
    try {
      const res = await fetch(`${API}/api/onboarding/diagnose`)
      const d = await res.json()
      if (d.ok) {
        setDiagnostics(d.diagnostics)
      } else {
        setDiagnosticsError(d.error || '获取诊断信息失败')
      }
    } catch {
      setDiagnosticsError('无法连接服务器，请确保机器人后端已启动')
    }
    setDiagnosticsLoading(false)
  }

  useEffect(() => {
    fetchDiagnostics()
  }, [])

  const isManualValid =
    manualKey.trim().length === 64 &&
    /^[0-9a-fA-F]+$/.test(manualKey.trim()) &&
    manualWxid.trim().length > 0 &&
    manualDbPath.trim().length > 0;

  async function handleExtract() {
    setBusy(true)
    setPhase('extracting')
    setMsg('')
    try {
      const startRes = await fetch(`${API}/api/onboarding/step1`, { method: 'POST' })
      const start = await startRes.json()
      if (!start.ok) {
        setPhase('error')
        setMsg(start.message || '启动失败')
        setBusy(false)
        return
      }

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
        } catch {}
      }, 1000)
    } catch {
      setPhase('error')
      setMsg('无法连接服务器')
      setBusy(false)
    }
  }

  function handleManualSubmit() {
    updateData({
      key: manualKey.trim(),
      wxid: manualWxid.trim(),
      db_path: manualDbPath.trim()
    })
    onDone()
  }

  function renderChecklist() {
    if (diagnosticsLoading) {
      return (
        <div className="flex flex-col items-center justify-center py-12 space-y-3 bg-bg-raised border border-border-main rounded-2xl">
          <Spinner size={28} weight="bold" className="animate-spin text-brand-green" />
          <p className="text-sm text-text-muted font-mono">正在分析本地系统就绪状态...</p>
        </div>
      )
    }

    if (diagnosticsError) {
      return (
        <div className="p-6 bg-[#d45656]/10 border border-[#d45656]/20 rounded-2xl text-sm text-[#d45656] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <XCircle size={20} weight="fill" />
            <span>{diagnosticsError}</span>
          </div>
          <button
            onClick={fetchDiagnostics}
            className="px-4 py-2 bg-[#d45656]/20 hover:bg-[#d45656]/30 rounded-full text-xs font-semibold cursor-pointer transition-colors text-[#d45656]"
          >
            重新连接
          </button>
        </div>
      )
    }

    if (!diagnostics) return null

    const items = [
      {
        key: 'python',
        title: 'Python 运行环境',
        desc: diagnostics.python.value,
        ok: diagnostics.python.ok,
        critical: true,
      },
      {
        key: 'requirements',
        title: 'Python 依赖库 (requirements.txt)',
        desc: diagnostics.requirements.ok
          ? diagnostics.requirements.value
          : `缺少依赖: ${diagnostics.requirements.missing.join(', ')}`,
        ok: diagnostics.requirements.ok,
        critical: true,
        help: !diagnostics.requirements.ok ? '请打开终端运行: pip install -r requirements.txt' : null,
      },
      {
        key: 'wechat',
        title: '微信电脑端状态',
        desc: diagnostics.wechat.value,
        ok: diagnostics.wechat.ok,
        critical: false,
        help: !diagnostics.wechat.ok ? '自动捕获密钥需要微信处于登录状态。若微信已登录但检测为未运行，请检查微信版本。' : null,
      },
      {
        key: 'env',
        title: '本地环境配置文件 (.env)',
        desc: diagnostics.env.value,
        ok: diagnostics.env.ok,
        critical: false,
      },
      {
        key: 'db',
        title: '本地数据库读写权限',
        desc: diagnostics.db.value,
        ok: diagnostics.db.ok,
        critical: true,
      }
    ]

    return (
      <div className="space-y-4">
        <div className="bg-bg-raised border border-border-main rounded-2xl divide-y divide-border-main/40">
          {items.map(item => (
            <div key={item.key} className="p-4 flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-main">{item.title}</span>
                  {!item.ok && item.critical && (
                    <span className="text-[10px] bg-[#d45656]/15 text-[#d45656] px-2.5 py-0.5 rounded-full border border-[#d45656]/30 font-bold">
                      阻塞项
                    </span>
                  )}
                </div>
                <p className={`text-xs ${item.ok ? 'text-text-muted' : 'text-[#c37d0d]'} font-mono`}>
                  {item.desc}
                </p>
                {item.help && (
                  <p className="text-[11px] text-text-muted bg-bg-main/45 p-2 rounded-2xl border border-border-main/30 font-mono mt-2 select-all leading-normal">
                    {item.help}
                  </p>
                )}
              </div>
              <div className="shrink-0 flex items-center h-5">
                {item.ok ? (
                  <CheckCircle size={20} weight="fill" className="text-brand-green" />
                ) : item.critical ? (
                  <XCircle size={20} weight="fill" className="text-[#d45656]" />
                ) : (
                  <div className="w-5 h-5 rounded-full bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
                    <span className="text-[#c37d0d] text-xs font-mono font-bold">!</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-between items-center bg-bg-raised/30 px-4 py-3 rounded-2xl border border-border-main/40">
          <span className="text-xs text-text-muted">环境诊断能保障自动提取及数据库访问正常。</span>
          <button
            onClick={fetchDiagnostics}
            className="text-xs text-brand-green-hover dark:text-brand-green hover:underline transition-colors font-medium flex items-center gap-1 cursor-pointer font-semibold"
          >
            重新检测
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-4.5 rounded-full bg-brand-green" />
          <h3 className="text-base font-semibold tracking-tight text-text-main">环境准备与密钥</h3>
        </div>
        <button
          onClick={() => setIsManual(!isManual)}
          className="text-xs text-brand-green-hover dark:text-brand-green hover:underline cursor-pointer font-medium"
        >
          {isManual ? '返回环境诊断' : '无法获取？手动配置'}
        </button>
      </div>

      <div className="bg-bg-card rounded-2xl p-1 space-y-6">
        {isManual ? (
          <div className="space-y-5">
            <p className="text-[14px] text-text-muted leading-relaxed">
              您在此可手动填写微信解密密钥和相关环境信息。
            </p>
            <Field label="微信解密密钥 (64位十六进制)" hint="从内存中提取或通过工具获取的64位 hex 密钥" error={manualKey && (manualKey.trim().length !== 64 || !/^[0-9a-fA-F]+$/.test(manualKey.trim())) ? '密钥格式不正确，必须为64位16进制字符' : null}>
              <Input
                type="password"
                value={manualKey}
                onChange={setManualKey}
                placeholder="例如：68a1f28b4c2..."
              />
            </Field>
            <Field label="微信账号 ID (wxid)" hint="当前微信账号的内部 ID (以 wxid_ 开头，或自定义微信号)">
              <Input
                value={manualWxid}
                onChange={setManualWxid}
                placeholder="例如：wxid_xxxxxxxxxxxxxx"
              />
            </Field>
            <Field label="聊天数据库路径 (db_path)" hint="微信本地 session.db 或 MSG.db 的绝对路径">
              <Input
                value={manualDbPath}
                onChange={setManualDbPath}
                placeholder="例如：C:\Users\Username\Documents\WeChat Files\wxid_...\db_storage\session\session.db"
              />
            </Field>
            <motion.button
              whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
              onClick={handleManualSubmit}
              disabled={!isManualValid}
              className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer ${
                isManualValid
                  ? 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] hover:opacity-95'
                  : 'bg-bg-raised text-text-muted/65 border border-border-main cursor-not-allowed'
              }`}
            >
              <ArrowRight size={18} /> 保存并下一步
            </motion.button>
          </div>
        ) : (
          <>
            {phase === 'idle' && (
              <div className="space-y-6">
                <p className="text-[14px] text-text-muted leading-relaxed">
                  微信机器人需要从微信获取加密密钥以读取聊天记录。自动获取过程无侵入，不会影响微信正常使用。
                </p>

                {renderChecklist()}

                <div className="pt-4 border-t border-border-main/40 flex items-center gap-4">
                  <motion.button
                    whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
                    onClick={handleExtract}
                    disabled={diagnosticsLoading || (diagnostics && !diagnostics.wechat.ok)}
                    className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer ${
                      diagnostics && diagnostics.wechat.ok
                        ? 'bg-brand-green text-[#0d0d0d] hover:opacity-90 animate-pulse'
                        : 'bg-bg-raised text-text-muted/65 border border-border-main cursor-not-allowed'
                    }`}
                  >
                    开始自动获取
                  </motion.button>
                  {diagnostics && !diagnostics.wechat.ok && (
                    <span className="text-xs text-[#c37d0d] bg-[#c37d0d]/10 border border-[#c37d0d]/20 px-4 py-2 rounded-full font-medium">
                      请登录微信电脑端，否则无法自动获取
                    </span>
                  )}
                </div>
              </div>
            )}

            {phase === 'extracting' && (
              <div className="space-y-6">
                <p className="text-[14px] text-text-muted leading-relaxed">
                  正在尝试挂钩微信进程，提取 WCDB 数据库加密密钥，请勿关闭微信。
                </p>
                <div className="bg-bg-raised border border-border-main rounded-2xl p-6 flex items-start gap-4">
                  <Spinner size={24} weight="bold" className="animate-spin text-brand-green shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-text-main">自动密钥捕获中...</p>
                    <p className="text-xs text-text-muted font-mono">{msg || '等待微信窗口激活并解密...'}</p>
                  </div>
                </div>
                {/* Mini-terminal keeps dark layout for developer style */}
                <div className="bg-[#0d0d0d] dark:bg-[#141414] border border-border-main rounded-2xl p-4 font-mono text-xs text-zinc-400 space-y-1">
                  <div className="flex justify-between border-b border-white/5 pb-1 mb-2 text-zinc-500 font-semibold">
                    <span>捕获状态监控</span>
                    <span>ACTIVE</span>
                  </div>
                  <div>[1] 正在启动 keyhook.dll 进程注入...</div>
                  {msg.includes('waiting_exit') && <div className="text-[#c37d0d]">[!] 检测到微信在运行，请先退出微信以便重新挂钩...</div>}
                  {msg.includes('waiting_login') && <div className="text-brand-green">[+] 微信已重新挂钩，请在弹出的微信界面进行登录...</div>}
                  {msg && <div className="text-zinc-300">&gt; {msg}</div>}
                </div>
                <button
                  onClick={() => setPhase('idle')}
                  className="px-4 py-2 bg-bg-raised hover:bg-bg-card text-xs text-text-muted hover:text-text-main rounded-full border border-border-main cursor-pointer transition-colors"
                >
                  取消并返回
                </button>
              </div>
            )}

            {phase === 'timeout' && (
              <div className="space-y-6">
                <div className="bg-[#d45656]/5 border border-[#d45656]/20 rounded-2xl p-6 flex items-start gap-4 text-[#d45656]">
                  <XCircle size={24} weight="fill" className="text-[#d45656] shrink-0" />
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-[#d45656]">获取密钥超时</p>
                    <p className="text-xs text-text-muted">{msg || '密钥捕获超时，请确保您成功登录了微信。'}</p>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleExtract}
                    className="px-4 py-2 bg-brand-green text-[#0d0d0d] hover:opacity-90 text-sm font-semibold rounded-full cursor-pointer transition-colors"
                  >
                    重试自动获取
                  </button>
                  <button
                    onClick={() => setPhase('idle')}
                    className="px-4 py-2 bg-bg-raised hover:bg-bg-card text-sm text-text-muted rounded-full border border-border-main cursor-pointer transition-colors"
                  >
                    返回诊断
                  </button>
                </div>
              </div>
            )}

            {phase === 'error' && (
              <div className="space-y-6">
                <div className="bg-[#d45656]/5 border border-[#d45656]/20 rounded-2xl p-6 flex items-start gap-4 text-[#d45656]">
                  <XCircle size={24} weight="fill" className="text-[#d45656] shrink-0" />
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-[#d45656]">自动提取失败</p>
                    <p className="text-xs text-text-muted">{msg}</p>
                  </div>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={handleExtract}
                    className="px-4 py-2 bg-brand-green text-[#0d0d0d] hover:opacity-90 text-sm font-semibold rounded-full cursor-pointer transition-colors"
                  >
                    重新获取
                  </button>
                  <button
                    onClick={() => setPhase('idle')}
                    className="px-4 py-2 bg-bg-raised hover:bg-bg-card text-sm text-text-muted rounded-full border border-border-main cursor-pointer transition-colors"
                  >
                    返回诊断
                  </button>
                </div>
              </div>
            )}

            {phase === 'done' && (
              <div className="space-y-5">
                <div className="bg-brand-green-light border border-brand-green/20 rounded-2xl p-5 flex items-center gap-3">
                  <CheckCircle size={24} weight="fill" className="text-brand-green-hover dark:text-brand-green" />
                  <div>
                    <p className="text-sm font-semibold text-brand-green-hover dark:text-brand-green">密钥自动获取成功</p>
                    <p className="text-xs text-text-muted">系统配置已就绪</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-bg-raised border border-border-main rounded-2xl p-4">
                    <p className="text-xs text-text-muted mb-1 font-semibold">微信账号 wxid</p>
                    <p className="text-sm font-mono text-text-main truncate font-bold">{data.wxid || '—'}</p>
                  </div>
                  <div className="bg-bg-raised border border-border-main rounded-2xl p-4">
                    <p className="text-xs text-text-muted mb-1 font-semibold">数据库文件</p>
                    <p className="text-xs font-mono text-text-main truncate">{data.db_path ? data.db_path.split('\\').slice(-2).join('\\') : '—'}</p>
                  </div>
                </div>
              </div>
            )}
          </>
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
        <div className="w-1.5 h-4.5 rounded-full bg-brand-green" />
        <h3 className="text-base font-semibold tracking-tight text-text-main">微信配置</h3>
      </div>

      <div className="space-y-6 mt-4">
        {/* Read-only info from step 1 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-bg-raised border border-border-main rounded-2xl p-4">
            <p className="text-xs text-text-muted font-semibold mb-1">检测到的微信账号</p>
            <p className="text-sm font-mono font-bold text-text-main truncate">{data.wxid || '未检测到'}</p>
          </div>
          <div className="bg-bg-raised border border-border-main rounded-2xl p-4">
            <p className="text-xs text-text-muted font-semibold mb-1">数据路径</p>
            <p className="text-xs font-mono text-text-muted truncate" title={data.db_path}>{data.db_path || '—'}</p>
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
          className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 ${
            valid
              ? 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] hover:opacity-95'
              : 'bg-bg-raised text-text-muted/65 border border-border-main cursor-not-allowed'
          }`}
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
        <div className="w-1.5 h-4.5 rounded-full bg-[#3772cf]" />
        <h3 className="text-base font-semibold tracking-tight text-text-main">AI 后端配置</h3>
      </div>

      <div className="space-y-6 mt-4">
        <Field label="AI 服务商" hint="推荐 DeepSeek，中文群聊效果更好">
          <Select value={data.ai_backend || 'deepseek'} onChange={v => updateData({ ai_backend: v })} options={[
            { value: 'deepseek', desc: 'DeepSeek', hint: '推荐 · 中文效果好' },
            { value: 'claude', desc: 'Claude', hint: 'Anthropic' },
          ]} />
        </Field>

        {isDeepSeek ? (
          <>
            <Field label="DeepSeek API Key" hint="在 platform.deepseek.com/api_keys 注册获取">
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
          className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 ${
            valid
              ? 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] hover:opacity-95'
              : 'bg-bg-raised text-text-muted/65 border border-border-main cursor-not-allowed'
          }`}
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
    setDone(true)
    setTimeout(onComplete, 1200)
    setBusy(false)
  }

  if (done) {
    return (
      <motion.div initial={{opacity:0,scale:0.95}} animate={{opacity:1,scale:1}} transition={spring}
        className="flex flex-col items-center justify-center py-16">
        <motion.div initial={{scale:0}} animate={{scale:1}} transition={{delay:0.1,...spring}}
          className="w-20 h-20 rounded-full bg-brand-green/10 border border-brand-green/20 flex items-center justify-center mb-6 shadow-sm">
          <CheckCircle size={38} weight="fill" className="text-brand-green" />
        </motion.div>
        <h2 className="text-lg font-bold text-text-main mb-2">配置就绪</h2>
        <p className="text-sm text-text-muted font-medium">正在启动夜航控制台仪表盘...</p>
      </motion.div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1.5 h-4.5 rounded-full bg-brand-green" />
        <h3 className="text-base font-semibold tracking-tight text-text-main">功能设置</h3>
      </div>

      <div className="space-y-4 mt-4">
        <div className="divide-y divide-border-main/40">
          <ToggleRow label="趣味抽签" desc={'@机器人说「抽签」，随机返回运势签文（大吉/中吉/小吉/末吉/凶）'} enabled={data.fun_enabled ?? true}
            onChange={v => updateData({ fun_enabled: v })} />
          <ToggleRow label="主动发言" desc="根据群聊活跃度自动参与对话" enabled={data.proactive_enabled ?? false}
            onChange={v => updateData({ proactive_enabled: v })} />
          <ToggleRow label="粘性提及" desc="@机器人后无需等待，机器人会追踪后续消息" enabled={data.sticky_mention_enabled ?? true}
            onChange={v => updateData({ sticky_mention_enabled: v })} />
        </div>

        <div className="mt-8 pt-4">
          <motion.button
            whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }}
            onClick={handleFinish}
            disabled={busy}
            className="w-56 py-2.5 rounded-full text-[14px] font-semibold tracking-wide transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer bg-brand-green text-[#0d0d0d] hover:opacity-90 animate-pulse"
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
    <div className="flex items-center justify-between py-4 border-b border-border-main/40 last:border-0">
      <div className="flex-1 mr-8">
        <p className="text-[14px] text-text-main font-semibold">{label}</p>
        <p className="text-xs text-text-muted mt-1">{desc}</p>
      </div>
      <Toggle enabled={enabled} onChange={onChange} />
    </div>
  )
}
