import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, FloppyDisk } from '@phosphor-icons/react'
import { Toggle } from './SharedComponents'

const paramPanel = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, y: 20, transition: { duration: 0.2 } },
}

// ── AddGroupPicker ──────────────────────────────────────────────────

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

  useEffect(() => { if (open && inputRef.current) { inputRef.current.focus(); setSearch('') } }, [open])

  const filtered = unassignedGroups.filter(g => {
    if (!search.trim()) return true
    const q = search.trim().toLowerCase()
    return (g.group_name || g.chat_id).toLowerCase().includes(q)
  })

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(!open)}
        className="px-3 py-2 rounded-xl text-[12px] text-text-muted bg-bg-main border border-dashed border-border-main hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer w-full text-left">
        + 为群聊单独配置（{unassignedGroups.length} 个群聊未配置）
      </button>
      {open && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-bg-card border border-border-main rounded-xl shadow-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-border-main/40">
            <input ref={inputRef} type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="搜索群聊名称..."
              className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[12px] text-text-main placeholder:text-text-muted/55 focus:outline-none focus:border-brand-green transition-colors" />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="px-3 py-4 text-[12px] text-text-muted text-center">{search.trim() ? '无匹配群聊' : '所有群聊已配置'}</div>
            ) : filtered.map(g => (
              <button key={g.chat_id} type="button" onClick={() => { onAdd(g.chat_id, defaultTemplate); setOpen(false) }}
                className="w-full text-left px-3 py-2 text-[12px] text-text-main hover:bg-bg-raised transition-colors cursor-pointer flex items-center justify-between">
                <span className="truncate font-mono" title={g.group_name || g.chat_id}>{g.group_name || g.chat_id}</span>
                <span className="text-[10px] text-text-muted shrink-0 ml-2">{g.member_count ? `${g.member_count} 人` : ''}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── SmallSelect ─────────────────────────────────────────────────────

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
      <button type="button" onClick={() => setOpen(!open)}
        className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[12px] text-text-main text-left focus:outline-none focus:border-brand-green transition-colors cursor-pointer hover:border-text-muted/30 flex items-center justify-between">
        <span className="truncate">{selected ? selected.desc : value}</span>
        <span className={`text-text-muted text-xs transition-transform duration-200 ${open ? 'rotate-90' : ''}`}>&#8250;</span>
      </button>
      {open && (
        <motion.div initial={{ opacity: 0, y: -2 }} animate={{ opacity: 1, y: 0 }}
          className="absolute z-50 left-0 right-0 mt-1 bg-bg-card border border-border-main rounded-xl shadow-lg overflow-hidden max-h-48 overflow-y-auto">
          {options.map(opt => (
            <button key={opt.value} type="button" onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-3 py-2 text-[12px] transition-colors cursor-pointer ${value === opt.value ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green font-semibold' : 'text-text-main hover:bg-bg-raised'}`}>
              {opt.desc}
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}

// ── WelcomeSection ──────────────────────────────────────────────────

export default function WelcomeSection({ form, update }) {
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
        if (grpData.ok) setGroups(grpData.groups || [])
      } catch {}
      setLoaded(true)
    }
    load()
  }, [])

  function updateTemplate(index, field, value) {
    setTemplates(prev => { const next = [...prev]; next[index] = { ...next[index], [field]: value }; return next })
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
      const deletedId = prev[index].id
      if (deletedId === defaultTemplate) setDefaultTemplate(next[0]?.id || 'tpl_default')
      setGroupMapping(prevMapping => {
        const nextMapping = { ...prevMapping }
        for (const [chatId, tplId] of Object.entries(nextMapping)) {
          if (tplId === deletedId) delete nextMapping[chatId]
        }
        return nextMapping
      })
      return next
    })
    if (activeTab >= index) setActiveTab(Math.max(0, activeTab - 1))
  }

  function insertVariable() {
    const ta = textareaRef.current
    if (!ta) return
    const start = ta.selectionStart, end = ta.selectionEnd
    const msg = templates[activeTab]?.message || ''
    updateTemplate(activeTab, 'message', msg.slice(0, start) + '{new_member}' + msg.slice(end))
    requestAnimationFrame(() => { ta.focus(); ta.setSelectionRange(start + 13, start + 13) })
  }

  function updateGroupMapping(chatId, templateId) {
    setGroupMapping(prev => {
      if (templateId === '__default__') { const next = { ...prev }; delete next[chatId]; return next }
      return { ...prev, [chatId]: templateId }
    })
  }

  function resetGroupMapping(chatId) {
    setGroupMapping(prev => { const next = { ...prev }; delete next[chatId]; return next })
  }

  async function handleSave() {
    setSaving(true); setSaveError(''); setSaved(false)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/welcome/templates', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ templates, group_mapping: groupMapping, default_template: defaultTemplate }),
      })
      const d = await res.json()
      if (d.ok) { setSaved(true); setTimeout(() => setSaved(false), 3000) }
      else { setSaveError(d.error || '保存失败'); setTimeout(() => setSaveError(''), 5000) }
    } catch { setSaveError('无法连接到服务器'); setTimeout(() => setSaveError(''), 5000) }
    setSaving(false)
  }

  const assignedGroups = groups.filter(g => groupMapping.hasOwnProperty(g.chat_id))
  const unassignedGroups = groups.filter(g => !groupMapping.hasOwnProperty(g.chat_id))
  const currentTemplate = templates[activeTab] || {}
  const templateOptions = [...templates.map(t => ({ value: t.id, desc: t.name, hint: '' })), { value: '__disabled__', desc: '关闭欢迎', hint: '该群不发送欢迎消息' }]
  const groupTemplateOptions = [{ value: '__default__', desc: '使用默认模板', hint: '' }, ...templateOptions]

  if (!loaded) {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex-1 mr-8"><p className="text-[15px] text-text-main font-medium">欢迎新人</p><p className="text-sm text-text-muted mt-1.5">检测到新成员加入群聊时，自动发送欢迎消息</p></div>
          <Toggle enabled={form.welcome_enabled} onChange={v => update('welcome_enabled', v)} />
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="flex-1 mr-8"><p className="text-[15px] text-text-main font-medium">欢迎新人</p><p className="text-sm text-text-muted mt-1.5">检测到新成员加入群聊时，自动发送欢迎消息</p></div>
        <Toggle enabled={form.welcome_enabled} onChange={v => update('welcome_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.welcome_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="mt-3 p-4 bg-bg-raised rounded-lg space-y-4">
            <div>
              <p className="text-[13px] text-text-main font-medium mb-2">欢迎词模板</p>
              <div className="flex flex-wrap items-center gap-1.5 mb-3">
                {templates.map((tpl, i) => (
                  <span key={tpl.id} onClick={() => setActiveTab(i)}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[13px] font-medium transition-colors cursor-pointer select-none ${i === activeTab ? 'bg-brand-green text-[#0d0d0d]' : 'bg-bg-main border border-border-main text-text-muted hover:text-text-main hover:border-text-muted/40'}`}>
                    {tpl.name}
                    {templates.length > 1 && (
                      <button type="button" onClick={e => { e.stopPropagation(); deleteTemplate(i) }}
                        className={`ml-0.5 leading-none text-base transition-colors cursor-pointer ${i === activeTab ? 'text-[#0d0d0d]/60 hover:text-[#d45656]' : 'text-text-muted/50 hover:text-[#d45656]'}`} title="删除模板">&times;</button>
                    )}
                  </span>
                ))}
                <button type="button" onClick={addTemplate}
                  className="px-3 py-1.5 rounded-lg text-[13px] font-medium bg-bg-main border border-dashed border-border-main text-text-muted hover:border-brand-green hover:text-brand-green-hover transition-colors cursor-pointer">+ 新建</button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] text-text-muted font-medium mb-1">模板名称</label>
                  <input type="text" value={currentTemplate.name || ''} onChange={e => updateTemplate(activeTab, 'name', e.target.value)}
                    className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-2 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all" />
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-text-muted font-medium">欢迎词内容（<code className="bg-bg-main px-1 rounded font-mono text-[11px]">{'{new_member}'}</code> 代表新成员 ID）</label>
                    <button type="button" onClick={insertVariable}
                      className="px-2.5 py-1 rounded-full text-[11px] font-medium bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors cursor-pointer" title="在光标位置插入新成员ID变量">+ 插入新成员 ID</button>
                  </div>
                  <textarea ref={textareaRef} value={currentTemplate.message || ''} onChange={e => updateTemplate(activeTab, 'message', e.target.value)}
                    rows={3} className="w-full bg-bg-main border border-border-main rounded-xl p-3 text-[13px] text-text-main leading-relaxed focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all resize-y font-mono"
                    placeholder="欢迎 @{new_member} 加入群聊！🎉" />
                </div>
              </div>
            </div>
            <div className="border-t border-border-main/40 pt-4">
              <p className="text-[13px] text-text-main font-medium mb-2">群聊分配</p>
              <p className="text-[11px] text-text-muted mb-3">未单独配置的群聊使用默认模板。设为「关闭欢迎」则不发送。</p>
              <div className="flex items-center gap-3 mb-3 px-3 py-2 bg-bg-main/60 rounded-xl border border-border-main/50">
                <span className="text-[12px] text-text-muted shrink-0">默认模板</span>
                <span className="text-[11px] text-text-muted/60 flex-1">未单独配置的群聊使用此模板</span>
                <div className="w-40"><SmallSelect value={defaultTemplate} onChange={v => setDefaultTemplate(v)} options={templates.map(t => ({ value: t.id, desc: t.name }))} /></div>
              </div>
              {assignedGroups.map(g => (
                <div key={g.chat_id} className="flex items-center gap-3 mb-2 px-3 py-2 bg-bg-main/60 rounded-xl border border-border-main/50">
                  <span className="text-[12px] text-text-main truncate flex-1 font-mono" title={g.group_name || g.chat_id}>{g.group_name || g.chat_id}</span>
                  <div className="w-40"><SmallSelect value={groupMapping[g.chat_id]} onChange={v => updateGroupMapping(g.chat_id, v)} options={groupTemplateOptions} /></div>
                  <button type="button" onClick={() => resetGroupMapping(g.chat_id)}
                    className="text-text-muted/50 hover:text-[#d45656] text-sm leading-none cursor-pointer transition-colors shrink-0" title="恢复为默认模板">&times;</button>
                </div>
              ))}
              {unassignedGroups.length > 0 && <AddGroupPicker unassignedGroups={unassignedGroups} defaultTemplate={defaultTemplate} onAdd={(chatId, templateId) => updateGroupMapping(chatId, templateId)} />}
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button type="button" onClick={handleSave} disabled={saving}
                className={`px-4 py-2 rounded-full text-[13px] font-semibold transition-all cursor-pointer flex items-center gap-2 ${saved ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green' : 'bg-brand-green text-[#0d0d0d] hover:opacity-90'}`}>
                {saving ? <><svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> 保存中</> : saved ? <><CheckCircle size={14} weight="fill" /> 已保存</> : <><FloppyDisk size={14} /> 保存模板配置</>}
              </button>
              {saveError && <span className="text-xs text-[#d45656] font-mono">{saveError}</span>}
              <span className="text-[11px] text-text-muted">模板配置独立保存，无需重启机器人</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
