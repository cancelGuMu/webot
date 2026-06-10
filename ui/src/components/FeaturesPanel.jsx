import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, Warning, FloppyDisk, Info } from '@phosphor-icons/react'
import { Field, Toggle, Select, Input } from './SharedComponents'
import WelcomeSection from './WelcomeEditor'

const pageTransition = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -12 },
}

const paramPanel = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: { opacity: 0, y: 20, transition: { duration: 0.2 } },
}

const sectionTitles = {
  summarize: '总结功能', todo: '群聊待办', feishu: '飞书同步', fun: '趣味抽签',
  proactive: '主动发言', sticky: '粘性提及', welcome: '欢迎新人', log: '日志级别',
}
const sectionAccents = {
  summarize: '#18E299', todo: '#e8794b', feishu: '#3772cf', fun: '#c37d0d',
  proactive: '#10b981', sticky: '#8b5cf6', welcome: '#f59e0b', log: '#6b7280',
}

// ── Helper ──────────────────────────────────────────────────────────

function ParamRow({ label, hint, children }) {
  return (
    <div>
      <p className="text-[14px] text-text-main font-medium">{label}</p>
      <p className="text-xs text-text-muted mt-0.5 mb-2">{hint}</p>
      {children}
    </div>
  )
}

// ── Summarize ───────────────────────────────────────────────────────

function SummarizeSection({ form, update }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-text-main font-medium">总结功能</p>
          <p className="text-sm text-text-muted mt-1.5">@机器人 或 触发关键词时自动总结群聊内容</p>
        </div>
        <Toggle enabled={form.summarize_enabled} onChange={v => update('summarize_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.summarize_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="p-4 bg-bg-raised rounded-lg space-y-4">
            <ParamRow label="回溯时长" hint="触发总结时，至少拉取最近 N 小时的消息（默认 8，范围 1-72）">
              <Input type="number" value={String(form.fallback_window_hours || 8)}
                onChange={v => update('fallback_window_hours', Math.max(1, Math.min(72, parseInt(v) || 8)))} />
            </ParamRow>
            <div>
              <p className="text-[14px] text-text-main font-medium">触发关键词</p>
              <p className="text-xs text-text-muted mt-0.5 mb-2">群成员发送包含任一关键词的消息时触发总结。至少保留 1 个关键词。</p>
              <div className="flex flex-wrap gap-2 mb-2">
                {(form.trigger_keywords || []).map((kw, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                    {kw}
                    <button type="button" disabled={(form.trigger_keywords || []).length <= 1}
                      onClick={() => { const next = (form.trigger_keywords || []).filter((_, idx) => idx !== i); update('trigger_keywords', next) }}
                      className={`ml-0.5 leading-none text-base transition-colors ${(form.trigger_keywords || []).length <= 1 ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input type="text" id="kw-input" placeholder="输入新关键词，回车添加"
                  className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); const val = e.target.value.trim(); if (val && !(form.trigger_keywords || []).includes(val)) { update('trigger_keywords', [...(form.trigger_keywords || []), val]); e.target.value = '' } } }} />
                <button type="button" onClick={() => { const el = document.getElementById('kw-input'); if (!el) return; const val = el.value.trim(); if (val && !(form.trigger_keywords || []).includes(val)) { update('trigger_keywords', [...(form.trigger_keywords || []), val]); el.value = '' } }}
                  className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">添加</button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Todo ────────────────────────────────────────────────────────────

function TodoSection({ form, update }) {
  const groups = Array.isArray(form.todo_groups) ? form.todo_groups : ['*']
  const addKeywords = Array.isArray(form.todo_add_keywords) ? form.todo_add_keywords : []
  const completeKeywords = Array.isArray(form.todo_complete_keywords) ? form.todo_complete_keywords : []
  const deleteKeywords = Array.isArray(form.todo_delete_keywords) ? form.todo_delete_keywords : []

  function addGroup(value) { const v = value.trim(); if (v && !groups.includes(v)) { update('todo_groups', groups.includes('*') ? [v] : [...groups, v]) } }
  function removeGroup(index) { if (groups.length <= 1) return; update('todo_groups', groups.filter((_, i) => i !== index)) }

  function KeywordChips({ keywords, updateKey, minItems = 1 }) {
    return (
      <div>
        <div className="flex flex-wrap gap-2 mb-2">
          {(keywords || []).map((kw, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
              {kw}
              <button type="button" disabled={keywords.length <= minItems}
                onClick={() => { const next = keywords.filter((_, idx) => idx !== i); update(updateKey, next) }}
                className={`ml-0.5 leading-none text-base transition-colors ${keywords.length <= minItems ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input type="text" placeholder="输入新触发词，回车添加"
            className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); const val = e.target.value.trim(); if (val && !keywords.includes(val)) { update(updateKey, [...keywords, val]); e.target.value = '' } } }} />
          <button type="button" onClick={() => { const el = document.querySelector(`[data-kw-input="${updateKey}"]`); if (!el) return; const val = el.value.trim(); if (val && !keywords.includes(val)) { update(updateKey, [...keywords, val]); el.value = '' } }}
            className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">添加</button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-text-main font-medium">群聊待办</p>
          <p className="text-sm text-text-muted mt-1.5">@机器人发送触发词，管理群聊待办事项。支持添加、完成、删除、恢复。</p>
        </div>
        <Toggle enabled={form.todo_enabled} onChange={v => update('todo_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.todo_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="p-4 bg-bg-raised rounded-lg space-y-5">
            {/* 生效群聊范围 */}
            <div>
              <p className="text-[14px] text-text-main font-medium">生效群聊范围</p>
              <p className="text-xs text-text-muted mt-0.5 mb-2">选择哪些群聊启用待办功能，未选中的群不响应待办命令</p>
              <div className="flex flex-wrap gap-2 mb-2">
                {(groups || []).map((g, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                    {g === '*' ? '全部群聊' : g}
                    <button type="button" disabled={groups.length <= 1}
                      onClick={() => removeGroup(i)}
                      className={`ml-0.5 leading-none text-base transition-colors ${groups.length <= 1 ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input type="text" data-todo-group-input placeholder="输入群聊名称，回车添加"
                  className="flex-1 bg-bg-raised border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addGroup(e.target.value); e.target.value = '' } }} />
                <button type="button" onClick={() => { const el = document.querySelector('[data-todo-group-input]'); if (el) { addGroup(el.value); el.value = '' } }}
                  className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">添加</button>
              </div>
            </div>

            {/* 参数设置 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ParamRow label="每群待办上限" hint="单个群最多待办数（1-200）">
                <Input type="number" value={String(form.todo_max_per_group || 50)}
                  onChange={v => update('todo_max_per_group', Math.max(1, Math.min(200, parseInt(v) || 50)))} />
              </ParamRow>
              <ParamRow label="已完成保留天数" hint="超期自动清理（0=永久）">
                <Input type="number" value={String(form.todo_completed_retention_days || 30)}
                  onChange={v => update('todo_completed_retention_days', Math.max(0, parseInt(v) || 0))} />
              </ParamRow>
              <ParamRow label="已删除保留天数" hint="超期自动清理（0=永久）">
                <Input type="number" value={String(form.todo_deleted_retention_days || 30)}
                  onChange={v => update('todo_deleted_retention_days', Math.max(0, parseInt(v) || 0))} />
              </ParamRow>
            </div>

            {/* 添加待办触发词 */}
            <div>
              <p className="text-[14px] text-text-main font-medium">添加待办触发词</p>
              <p className="text-xs text-text-muted mt-0.5 mb-2">群成员 @机器人后发送触发词 + 待办内容，即可添加</p>
              <KeywordChips keywords={addKeywords} updateKey="todo_add_keywords" />
            </div>

            {/* 完成待办触发词 */}
            <div>
              <p className="text-[14px] text-text-main font-medium">完成待办触发词</p>
              <p className="text-xs text-text-muted mt-0.5 mb-2">群成员 @机器人后发送触发词 + 编号，即可标记完成</p>
              <KeywordChips keywords={completeKeywords} updateKey="todo_complete_keywords" />
            </div>

            {/* 删除待办触发词 */}
            <div>
              <p className="text-[14px] text-text-main font-medium">删除待办触发词</p>
              <p className="text-xs text-text-muted mt-0.5 mb-2">群成员 @机器人后发送触发词 + 编号，即可移至已删除</p>
              <KeywordChips keywords={deleteKeywords} updateKey="todo_delete_keywords" />
            </div>

            {/* 使用提示 */}
            <div className="p-3 bg-bg-main/60 border border-border-main rounded-xl">
              <p className="text-xs text-text-muted leading-relaxed">
                💡 <strong>群内使用提示：</strong><br/>
                @机器人 <code>查看待办</code> · <code>记一下 xxx</code> · <code>搞定 N</code>
                · <code>删掉 N</code> · <code>恢复待办 N</code>（管理员）<br/>
                <span className="text-text-muted/60">查看待办、已完成列表、已删除列表、清空等命令为固定触发词，无需配置。</span>
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Feishu ──────────────────────────────────────────────────────────

function FeishuSection({ form, update }) {
  const keywords = Array.isArray(form.feishu_export_trigger_keywords)
    ? form.feishu_export_trigger_keywords
    : String(form.feishu_export_trigger_keywords || '').split(',').map(s => s.trim()).filter(Boolean)
  const mode = form.feishu_export_mode || 'knowledge'
  const modeLabel = mode === 'bitable' ? '多维表格' : mode === 'docx' ? '文档' : '电子表格'

  function addKeyword(value) { const val = value.trim(); if (val && !keywords.includes(val)) update('feishu_export_trigger_keywords', [...keywords, val]) }
  function removeKeyword(index) { if (keywords.length <= 1) return; update('feishu_export_trigger_keywords', keywords.filter((_, i) => i !== index)) }

  return (
    <div>
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
            className="mt-2 p-4 bg-bg-raised rounded-lg space-y-3">
            <Field label="飞书应用凭证" hint="使用企业自建应用的 App ID 和 App Secret">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input value={form.feishu_app_id || ''} onChange={v => update('feishu_app_id', v)} placeholder="cli_xxxxxxxxxxxxxxxx" />
                <Input type="password" value={form.feishu_app_secret || ''} onChange={v => update('feishu_app_secret', v)} placeholder="App Secret" />
              </div>
            </Field>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ParamRow label="沉淀模式" hint="推荐自动知识库">
                <Select value={mode} onChange={v => update('feishu_export_mode', v)} options={[
                  { value: 'knowledge', desc: '自动知识库', hint: '自动建表并分类沉淀' },
                  { value: 'bitable', desc: '已有多维表格', hint: '高级：写入指定表' },
                  { value: 'spreadsheet', desc: '已有电子表格', hint: '高级：追加一行摘要' },
                  { value: 'docx', desc: '文档', hint: '高级：创建摘要文档' },
                ]} />
              </ParamRow>
              <ParamRow label="同步窗口" hint="拉取触发前 N 小时消息，范围 1-168">
                <Input type="number" value={String(form.feishu_export_window_hours || 8)}
                  onChange={v => update('feishu_export_window_hours', Math.max(1, Math.min(168, parseInt(v) || 8)))} />
              </ParamRow>
            </div>
            {mode === 'knowledge' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <ParamRow label="知识库名称" hint="首次同步时自动创建">
                  <Input value={form.feishu_knowledge_base_name || 'webot 群聊沉淀'} onChange={v => update('feishu_knowledge_base_name', v)} placeholder="webot 群聊沉淀" />
                </ParamRow>
                <ParamRow label="飞书文件夹 Token" hint="可选；留空则创建到应用默认位置">
                  <Input value={form.feishu_knowledge_folder_token || ''} onChange={v => update('feishu_knowledge_folder_token', v)} placeholder="fldxxxxxxxxxxxx" />
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
              <p className="text-xs text-text-muted mt-0.5 mb-2">手动兜底命令。@机器人后的文本包含任一触发词时，立即沉淀最近群聊。</p>
              <div className="flex flex-wrap gap-2 mb-2">
                {keywords.map((kw, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green">
                    {kw}
                    <button type="button" disabled={keywords.length <= 1} onClick={() => removeKeyword(i)}
                      className={`ml-0.5 leading-none text-base transition-colors ${keywords.length <= 1 ? 'text-text-muted cursor-not-allowed' : 'text-brand-green-hover/60 hover:text-[#d45656] cursor-pointer'}`}>&times;</button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input type="text" id="feishu-kw-input" placeholder="输入新触发词，回车添加"
                  className="flex-1 bg-bg-main border border-border-main rounded-lg px-3 py-2 text-[14px] text-text-main placeholder:text-text-muted/65 focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all"
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addKeyword(e.target.value); e.target.value = '' } }} />
                <button type="button" onClick={() => { const el = document.getElementById('feishu-kw-input'); if (!el) return; addKeyword(el.value); el.value = '' }}
                  className="px-4 py-2 bg-brand-green-light border border-brand-green/20 rounded-lg text-[13px] text-brand-green-hover dark:text-brand-green hover:bg-brand-green/10 transition-colors font-medium cursor-pointer">添加</button>
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
  )
}

// ── Fun: Draw Lots ──────────────────────────────────────────────────

function FunSection({ form, update }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-text-main font-medium">趣味抽签</p>
          <p className="text-sm text-text-muted mt-1.5">@机器人说"抽签"，随机返回运势签文（大吉/中吉/小吉/末吉/凶）</p>
        </div>
        <Toggle enabled={form.fun_enabled} onChange={v => update('fun_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.fun_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="p-4 bg-bg-raised rounded-lg space-y-3">
            <LotsEditor />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Proactive ───────────────────────────────────────────────────────

function ProactiveSection({ form, update }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-text-main font-medium">主动发言</p>
          <p className="text-sm text-text-muted mt-1.5">无需 @提及，根据聊天活跃度自动参与对话</p>
        </div>
        <Toggle enabled={form.proactive_enabled} onChange={v => update('proactive_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.proactive_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="p-4 bg-bg-raised rounded-lg space-y-3">
            <p className="text-xs text-text-muted leading-relaxed">
              机器人统计最近 <strong>速率窗口</strong> 秒内的群聊消息速率（条/分钟），与下方四个阈值比较，决定发言频率：
            </p>
            <div className="grid grid-cols-2 gap-3">
              <ParamRow label="速率窗口" hint="统计消息速率的时间范围（秒），默认 120 = 2 分钟">
                <Input type="number" value={String(form.proactive_rate_window_sec || 120)}
                  onChange={v => update('proactive_rate_window_sec', parseInt(v) || 120)} />
              </ParamRow>
              <ParamRow label="安静阈值" hint="速率低于此值不发言（默认 1.5 条/分）">
                <Input type="number" value={String(form.proactive_rate_quiet ?? 1.5)}
                  onChange={v => update('proactive_rate_quiet', parseFloat(v) || 1.5)} />
              </ParamRow>
              <ParamRow label="随口阈值" hint="超过此值偶尔插话（默认 4.0 条/分）">
                <Input type="number" value={String(form.proactive_rate_casual ?? 4.0)}
                  onChange={v => update('proactive_rate_casual', parseFloat(v) || 4.0)} />
              </ParamRow>
              <ParamRow label="活跃阈值" hint="超过此值频繁参与（默认 6.5 条/分）">
                <Input type="number" value={String(form.proactive_rate_lively ?? 6.5)}
                  onChange={v => update('proactive_rate_lively', parseFloat(v) || 6.5)} />
              </ParamRow>
              <ParamRow label="爆发阈值" hint="超过此值火力全开（默认 8.5 条/分）">
                <Input type="number" value={String(form.proactive_rate_burst ?? 8.5)}
                  onChange={v => update('proactive_rate_burst', parseFloat(v) || 8.5)} />
              </ParamRow>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Sticky Mention ──────────────────────────────────────────────────

function StickySection({ form, update }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 mr-8">
          <p className="text-[15px] text-text-main font-medium">粘性提及</p>
          <p className="text-sm text-text-muted mt-1.5">@机器人后无需等待回复即可继续说，机器人会追踪后续消息</p>
        </div>
        <Toggle enabled={form.sticky_mention_enabled} onChange={v => update('sticky_mention_enabled', v)} />
      </div>
      <AnimatePresence>
        {form.sticky_mention_enabled && (
          <motion.div variants={paramPanel} initial="initial" animate="animate" exit="exit"
            className="p-4 bg-bg-raised rounded-lg">
            <ParamRow label="追踪超时" hint="用户发送空 @消息后，等待后续消息的最长时间">
              <Select value={String(form.sticky_mention_ttl_sec || 60) + ' 秒'}
                onChange={v => update('sticky_mention_ttl_sec', parseInt(v))}
                options={[
                  { value: '30 秒', desc: '快速响应 (30 秒)', hint: '30 秒后自动失效' },
                  { value: '60 秒', desc: '默认 (60 秒)', hint: '60 秒后自动失效' },
                  { value: '120 秒', desc: '宽松 (120 秒)', hint: '120 秒后自动失效' },
                  { value: '300 秒', desc: '最长时间 (300 秒)', hint: '300 秒后自动失效' },
                ]} />
            </ParamRow>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Welcome (imported from ConfigPanel) ─────────────────────────────
// WelcomeSection, AddGroupPicker, SmallSelect are too large to inline.
// We import them lazily from ConfigPanel.

// ── Log Level ───────────────────────────────────────────────────────

function LogSection({ form, update }) {
  return (
    <div>
      <Field label="日志级别" hint="记录机器人运行日志的详细程度">
        <Select value={form.log_level} onChange={v => update('log_level', v)} options={[
          { value: 'DEBUG', desc: '调试信息', hint: '排查故障时使用' },
          { value: 'INFO', desc: '常规信息', hint: '日常使用（推荐）' },
          { value: 'WARNING', desc: '仅警告', hint: '长期稳定运行时使用' },
          { value: 'ERROR', desc: '仅错误', hint: '只关心故障时使用' },
        ]} />
      </Field>
    </div>
  )
}

// ── Lots Editor (抽签配置编辑器) ────────────────────────────────────

function LotsEditor() {
  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('http://127.0.0.1:7327/api/lots')
        const d = await res.json()
        if (d.ok && d.config) setData(d.config)
        else setLoadError(d.error || '加载失败')
      } catch { setLoadError('无法连接服务器') }
    }
    load()
  }, [])

  function updateWeight(index, value) {
    const num = Math.max(1, Math.min(100, parseInt(value) || 1))
    setData(prev => { const next = { ...prev }; next.weights = [...prev.weights]; next.weights[index] = num; return next })
    setDirty(true)
  }

  function updateLevelField(index, field, value) {
    setData(prev => { const next = { ...prev }; next.levels = prev.levels.map((lvl, i) => i === index ? { ...lvl, [field]: value } : lvl); return next })
    setDirty(true)
  }

  function updatePhrases(index, text) {
    const phrases = text.split('\n').filter(line => line.trim() !== '')
    setData(prev => { const next = { ...prev }; next.levels = prev.levels.map((lvl, i) => i === index ? { ...lvl, phrases: phrases.length > 0 ? phrases : ['(空)'] } : lvl); return next })
    setDirty(true)
  }

  async function handleSave() {
    setSaving(true); setSaveError(''); setSaved(false)
    try {
      const res = await fetch('http://127.0.0.1:7327/api/lots', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      const d = await res.json()
      if (d.ok) { setSaved(true); setDirty(false); setTimeout(() => setSaved(false), 3000) }
      else { setSaveError(d.error || '保存失败'); setTimeout(() => setSaveError(''), 5000) }
    } catch { setSaveError('无法连接到服务器'); setTimeout(() => setSaveError(''), 5000) }
    setSaving(false)
  }

  async function handleRestoreDefaults() {
    setSaving(true)
    try {
      await fetch('http://127.0.0.1:7327/api/lots', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ weights: [], levels: [] }) })
      const reload = await fetch('http://127.0.0.1:7327/api/lots'); const rd = await reload.json()
      if (rd.ok && rd.config) { setData(rd.config); setDirty(false); setSaved(true); setTimeout(() => setSaved(false), 3000) }
    } catch { setSaveError('恢复失败'); setTimeout(() => setSaveError(''), 5000) }
    setSaving(false)
  }

  if (loadError) return <div className="text-xs text-[#d45656] bg-[#d45656]/5 border border-[#d45656]/20 rounded-xl px-4 py-3">抽签配置加载失败：{loadError}</div>
  if (!data) return <div className="text-xs text-text-muted py-2 flex items-center gap-2"><svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>加载签文配置中...</div>

  const totalWeight = data.weights.reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-text-muted">自定义各等级签文与权重。当前总权重：<span className="font-semibold text-text-main">{totalWeight}</span>（各等级概率 = 权重 ÷ 总权重）</p>
      </div>
      {data.levels.map((level, i) => {
        const isOpen = expanded === i
        const probability = totalWeight > 0 ? ((data.weights[i] / totalWeight) * 100).toFixed(1) : '0.0'
        return (
          <div key={i} className="bg-bg-main/60 border border-border-main/70 rounded-xl overflow-hidden transition-all">
            <button type="button" onClick={() => setExpanded(isOpen ? null : i)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-bg-raised/50 transition-colors cursor-pointer text-left">
              <span className="text-lg">{level.emoji || '❓'}</span>
              <span className="text-sm font-semibold text-text-main flex-1">{level.name}</span>
              <span className="text-xs text-text-muted font-mono bg-bg-raised border border-border-main px-2 py-0.5 rounded-full">权重 {data.weights[i]} · {probability}%</span>
              <span className="text-xs text-text-muted font-mono bg-bg-raised border border-border-main px-2 py-0.5 rounded-full">{level.phrases.length} 条签文</span>
              <span className={`text-text-muted text-xs transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}>›</span>
            </button>
            {isOpen && (
              <div className="px-4 pb-4 pt-1 border-t border-border-main/40 space-y-3 bg-bg-raised/30">
                <div className="grid grid-cols-3 gap-3">
                  <div><label className="block text-[11px] text-text-muted font-medium mb-1">等级名称</label><input type="text" value={level.name} onChange={e => updateLevelField(i, 'name', e.target.value)} className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all font-mono" /></div>
                  <div><label className="block text-[11px] text-text-muted font-medium mb-1">Emoji</label><input type="text" value={level.emoji || ''} onChange={e => updateLevelField(i, 'emoji', e.target.value)} className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all" /></div>
                  <div><label className="block text-[11px] text-text-muted font-medium mb-1">权重 (1-100)</label><input type="number" min="1" max="100" value={data.weights[i]} onChange={e => updateWeight(i, e.target.value)} className="w-full bg-bg-main border border-border-main rounded-lg px-3 py-1.5 text-[13px] text-text-main focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all font-mono" /></div>
                </div>
                <div><label className="block text-[11px] text-text-muted font-medium mb-1">签文列表（每行一条，共 {level.phrases.length} 条）</label><textarea value={level.phrases.join('\n')} onChange={e => updatePhrases(i, e.target.value)} rows={Math.max(6, Math.min(level.phrases.length + 2, 16))} className="w-full bg-bg-main border border-border-main rounded-xl p-3 text-[13px] text-text-main leading-relaxed focus:outline-none focus:border-brand-green focus:ring-1 focus:ring-brand-green/15 transition-all font-mono resize-y" /></div>
              </div>
            )}
          </div>
        )
      })}
      <div className="flex items-center gap-3 pt-2">
        <button type="button" onClick={handleSave} disabled={saving}
          className={`px-5 py-2 rounded-full text-[13px] font-semibold transition-all cursor-pointer flex items-center gap-2 ${saved ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green' : dirty ? 'bg-brand-green text-[#0d0d0d] hover:opacity-90' : 'bg-bg-main border border-border-main text-text-muted hover:text-text-main'}`}>
          {saving ? <><svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> 保存中</> : saved ? <><CheckCircle size={14} weight="fill" /> 已保存</> : <><FloppyDisk size={14} /> {dirty ? '保存抽签配置' : '保存'}</>}
        </button>
        <button type="button" onClick={handleRestoreDefaults} disabled={saving}
          className="px-4 py-2 rounded-full text-[12px] text-text-muted hover:text-[#d45656] border border-border-main hover:border-[#d45656]/20 hover:bg-[#d45656]/5 transition-colors cursor-pointer font-medium">恢复默认签文</button>
        {saveError && <span className="text-xs text-[#d45656] font-mono">{saveError}</span>}
      </div>
    </div>
  )
}

// ── Main FeaturesPanel ──────────────────────────────────────────────

export default function FeaturesPanel({ activeSection, onNavigate }) {
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [form, setForm] = useState({
    summarize_enabled: true, fallback_window_hours: 8, trigger_keywords: [],
    fun_enabled: true,
    proactive_enabled: false, proactive_rate_window_sec: 120,
    proactive_rate_quiet: 1.5, proactive_rate_casual: 4.0,
    proactive_rate_lively: 6.5, proactive_rate_burst: 8.5,
    sticky_mention_enabled: true, sticky_mention_ttl_sec: 60,
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
    todo_enabled: true, todo_groups: ['*'],
    todo_max_per_group: 50, todo_completed_retention_days: 30, todo_deleted_retention_days: 30,
    todo_add_keywords: ['记一下', '添加待办', '新建待办', '帮我记', '待办'],
    todo_complete_keywords: ['搞定', '做完了', '完成', '完成了', 'done'],
    todo_delete_keywords: ['删掉', '删除', '取消', '不要了'],
    log_level: 'INFO',
  })

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('http://127.0.0.1:7327/api/load-config')
        const data = await res.json()
        if (data.ok && data.config) setForm(prev => ({ ...prev, ...data.config }))
      } catch {}
      setLoaded(true)
    }
    load()
  }, [])

  function update(key, value) { setForm(prev => ({ ...prev, [key]: value })); setSaved(false); setSaveError('') }

  async function handleSave() {
    setSaved(false); setSaveError('')
    try {
      const res = await fetch('http://127.0.0.1:7327/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          summarize_enabled: form.summarize_enabled, fallback_window_hours: form.fallback_window_hours,
          trigger_keywords: form.trigger_keywords,
          fun_enabled: form.fun_enabled,
          proactive_enabled: form.proactive_enabled, proactive_rate_window_sec: form.proactive_rate_window_sec,
          proactive_rate_quiet: form.proactive_rate_quiet, proactive_rate_casual: form.proactive_rate_casual,
          proactive_rate_lively: form.proactive_rate_lively, proactive_rate_burst: form.proactive_rate_burst,
          sticky_mention_enabled: form.sticky_mention_enabled, sticky_mention_ttl_sec: form.sticky_mention_ttl_sec,
          welcome_enabled: form.welcome_enabled,
          feishu_export_enabled: form.feishu_export_enabled, feishu_app_id: form.feishu_app_id,
          feishu_app_secret: form.feishu_app_secret, feishu_export_mode: form.feishu_export_mode,
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
          todo_enabled: form.todo_enabled,
          todo_groups: form.todo_groups,
          todo_max_per_group: form.todo_max_per_group,
          todo_completed_retention_days: form.todo_completed_retention_days,
          todo_deleted_retention_days: form.todo_deleted_retention_days,
          todo_add_keywords: form.todo_add_keywords,
          todo_complete_keywords: form.todo_complete_keywords,
          todo_delete_keywords: form.todo_delete_keywords,
          log_level: form.log_level,
        }),
      })
      const data = await res.json()
      if (data.ok) { setSaved(true); setTimeout(() => setSaved(false), 3000) }
      else { setSaveError(data.error || '保存失败'); setTimeout(() => setSaveError(''), 5000) }
    } catch { setSaveError('无法连接到服务器，请确认机器人已启动'); setTimeout(() => setSaveError(''), 5000) }
  }

  return (
    <div className="max-w-2xl">
      <AnimatePresence>
        {saved && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-brand-green-light border border-brand-green/20 rounded-full text-sm text-brand-green-hover dark:text-brand-green font-medium shadow-sm">
            <CheckCircle size={18} weight="fill" /> 配置已保存。需要重启机器人才能生效。
          </motion.div>
        )}
        {saveError && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
            className="mb-4 flex items-center gap-2 px-5 py-2.5 bg-[#d45656]/5 border border-[#d45656]/20 rounded-full text-sm text-[#d45656] font-medium shadow-sm">
            <Warning size={18} weight="fill" /> {saveError}
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
                {activeSection === 'summarize' && <SummarizeSection form={form} update={update} />}
                {activeSection === 'todo' && <TodoSection form={form} update={update} />}
                {activeSection === 'feishu' && <FeishuSection form={form} update={update} />}
                {activeSection === 'fun' && <FunSection form={form} update={update} />}
                {activeSection === 'proactive' && <ProactiveSection form={form} update={update} />}
                {activeSection === 'sticky' && <StickySection form={form} update={update} />}
                {activeSection === 'welcome' && <WelcomeSection form={form} update={update} />}
                {activeSection === 'log' && <LogSection form={form} update={update} />}
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      {activeSection !== 'log' && activeSection !== 'fun' && (
        <div className="mt-8 flex items-center gap-4">
          <motion.button whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }} onClick={handleSave}
            className={`w-48 py-2.5 rounded-full text-[14px] font-semibold tracking-wide shadow-sm transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer ${saved ? 'bg-brand-green-light border border-brand-green/20 text-brand-green-hover dark:text-brand-green font-semibold' : 'bg-[#0d0d0d] dark:bg-white text-white dark:text-[#0d0d0d] border border-[#0d0d0d] dark:border-border-main hover:opacity-90'}`}>
            {saved ? <><CheckCircle size={18} weight="fill" /> 已保存</> : <><FloppyDisk size={18} /> 保存配置</>}
          </motion.button>
          {saved ? (
            <span className="flex items-center gap-1.5 text-xs text-[#c37d0d] bg-[#c37d0d]/10 border border-[#c37d0d]/20 px-4 py-1.5 rounded-full font-medium">
              <Info size={14} /> 配置已更新，重启机器人后生效
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-text-muted bg-bg-raised border border-border-main px-4 py-1.5 rounded-full font-medium">
              <Info size={14} /> 保存将应用所有模块的修改，重启后生效
            </span>
          )}
        </div>
      )}
    </div>
  )
}
