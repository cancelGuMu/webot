import { useState, useEffect } from 'react'
import { CheckCircle, FloppyDisk } from '@phosphor-icons/react'

export default function LotsEditor() {
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
