import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Check, Spinner } from '@phosphor-icons/react'

const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
}

export default function NicknameEditor() {
  const [groups, setGroups] = useState([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [members, setMembers] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState({}) // {wxid: true} while saving
  const [error, setError] = useState('')

  // Load group list on mount
  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('http://127.0.0.1:7327/api/nicknames/groups')
        const data = await res.json()
        if (data.ok) {
          setGroups(data.groups || [])
          if (data.groups?.length > 0) {
            setSelectedGroup(data.groups[0].chat_id)
          }
        }
      } catch (e) {
        setError('无法连接到服务器')
      }
    }
    load()
  }, [])

  // Load members when group changes
  useEffect(() => {
    if (!selectedGroup) return
    setLoading(true)
    setError('')
    async function load() {
      try {
        const res = await fetch(`http://127.0.0.1:7327/api/nicknames?chat_id=${encodeURIComponent(selectedGroup)}`)
        const data = await res.json()
        if (data.ok) {
          setMembers(data.members || [])
        } else {
          setError(data.error || '加载失败')
        }
      } catch {
        setError('加载群成员失败')
      }
      setLoading(false)
    }
    load()
  }, [selectedGroup])

  // Save nickname on blur
  async function saveNickname(wxid, nickname) {
    setSaving(prev => ({ ...prev, [wxid]: true }))
    try {
      await fetch('http://127.0.0.1:7327/api/nicknames', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wxid, nickname }),
      })
      // Update local state
      setMembers(prev => prev.map(m => m.wxid === wxid ? { ...m, nickname } : m))
    } catch {
      // silently fail, user can retry
    }
    setSaving(prev => ({ ...prev, [wxid]: false }))
  }

  const selected = groups.find(g => g.chat_id === selectedGroup)

  return (
    <motion.div variants={pageTransition} initial="initial" animate="animate" className="max-w-4xl">
      <div className="flex items-center gap-2 mb-6">
        <div className="w-1 h-5 rounded-full bg-[#c37d0d]" />
        <h3 className="text-base font-semibold tracking-tight text-text-main">群友昵称</h3>
      </div>

      <div className="bg-bg-card border border-border-main rounded-2xl shadow-[rgba(0,0,0,0.03)_0px_2px_4px] dark:shadow-none p-7">
        <p className="text-sm text-text-muted mb-5">为群友设置显示昵称。AI 回复中会自动将微信 ID（wxid_xxx）替换为这里设置的昵称。</p>

        {/* Group selector */}
        <div className="mb-5">
          <label className="block text-[13px] font-medium text-text-muted mb-1.5">选择群聊</label>
          <select
            value={selectedGroup}
            onChange={e => setSelectedGroup(e.target.value)}
            className="w-full bg-bg-raised border border-border-main rounded-lg px-4 py-2.5 text-[15px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
          >
            {groups.map(g => (
              <option key={g.chat_id} value={g.chat_id}>
                {g.group_name}（{g.member_count} 人）
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 bg-[#d45656]/5 border border-[#d45656]/20 rounded-lg text-sm text-[#d45656]">{error}</div>
        )}

        {/* Member table */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size={24} weight="bold" className="animate-spin text-brand-green" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-main/50 text-left">
                  <th className="pb-3 pr-4 font-medium text-text-muted w-[180px]">群内显示名</th>
                  <th className="pb-3 pr-4 font-medium text-text-muted w-[200px]">微信 ID</th>
                  <th className="pb-3 font-medium text-text-muted">自定义昵称</th>
                </tr>
              </thead>
              <tbody>
                {members.map(m => (
                  <tr key={m.wxid} className="border-b border-border-main/40 last:border-0">
                    <td className="py-2.5 pr-4 text-text-main">{m.display_name || m.wxid}</td>
                    <td className="py-2.5 pr-4 text-text-muted font-mono text-xs">{m.wxid}</td>
                    <td className="py-2.5">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          defaultValue={m.nickname || ''}
                          placeholder="留空使用显示名"
                          onBlur={e => {
                            const val = e.target.value.trim()
                            if (val !== (m.nickname || '')) {
                              saveNickname(m.wxid, val)
                            }
                          }}
                          className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-1.5 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
                        />
                        {saving[m.wxid] && <Spinner size={16} weight="bold" className="animate-spin text-text-muted shrink-0" />}
                        {m.nickname && !saving[m.wxid] && <Check size={16} weight="bold" className="text-brand-green-hover dark:text-brand-green shrink-0" />}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {members.length === 0 && !loading && (
              <p className="text-center text-sm text-text-muted/65 py-8">
                {selected ? '该群暂无消息记录' : '请选择一个群聊'}
              </p>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}
