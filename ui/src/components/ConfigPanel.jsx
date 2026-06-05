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
  return (
    <div>
      <Field label="机器人微信昵称" hint="用于检测 @提及">
        <Input value={form.bot_display_name} onChange={v => update('bot_display_name', v)} placeholder="例如：群聊小助手" />
      </Field>
      <Field label="目标群聊" hint="输入 * 表示自动发现所有群聊，指定群名可用逗号分隔">
        <Input value={form.wechat_groups} onChange={v => update('wechat_groups', v)} placeholder="* = 所有群聊" />
      </Field>
      <Field label="微信后端" hint="当前使用本地数据库直读模式（无需外部进程）">
        <Select value={form.wechat_backend} onChange={v => update('wechat_backend', v)} options={[
          { value: 'wcdb', desc: 'WCDB', hint: '推荐 · 原生数据库直读' },
        ]} />
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
      <div className="flex items-center justify-between py-4 border-b border-[#F0F0EE]">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-[#1F1F1F] font-medium">粘性提及</p>
          <p className="text-sm text-[#B8B8B6] mt-1.5">@机器人后无需等待回复即可继续说，机器人会追踪后续消息</p>
        </div>
        <Toggle enabled={form.sticky_mention_enabled} onChange={v => update('sticky_mention_enabled', v)} />
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
  const [saveError, setSaveError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [form, setForm] = useState({
    ai_backend: 'deepseek', deepseek_api_key: '', deepseek_model: 'deepseek-v4-flash',
    anthropic_api_key: '', summarize_model: 'claude-haiku-4-5-20251001',
    bot_display_name: '', wechat_backend: 'wcdb', wechat_groups: '*',
    proactive_enabled: false, vulgar_guard_enabled: true,
    sticky_mention_enabled: true,
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
          proactive_enabled: form.proactive_enabled,
          vulgar_guard_enabled: form.vulgar_guard_enabled,
          sticky_mention_enabled: form.sticky_mention_enabled,
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
