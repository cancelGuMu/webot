import { motion } from 'framer-motion'
import { Database, Brain, Clock, ChatCircle, Pulse } from '@phosphor-icons/react'

const spring = { type: 'spring', stiffness: 100, damping: 20 }

function MetricCard({ icon: Icon, label, value, sub, accent = 'green' }) {
  const accents = {
    green:  { bg: '#EDF3EC', text: '#346538', border: '#C5DAC2' },
    blue:   { bg: '#E1F3FE', text: '#1F6C9F', border: '#B8DEF7' },
    amber:  { bg: '#FBF3DB', text: '#956400', border: '#F0DCAC' },
    rose:   { bg: '#FDEBEC', text: '#9F2F2D', border: '#F5C6C8' },
  }
  const a = accents[accent]

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={spring}
      whileHover={{ y: -2 }}
      className="bg-white border border-[#EAEAEA] rounded-xl p-7 transition-shadow duration-300 hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
    >
      <div className="flex items-start justify-between mb-4">
        <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: a.bg }}>
          <Icon size={20} weight="fill" style={{ color: a.text }} />
        </div>
      </div>
      <div className="space-y-1">
        <p className="text-sm text-[#787774] font-medium">{label}</p>
        <p className="text-3xl font-semibold tracking-tight font-mono text-[#1F1F1F]">{value}</p>
        {sub && <p className="text-xs text-[#B8B8B6]">{sub}</p>}
      </div>
    </motion.div>
  )
}

function LiveIndicator({ label, ok }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-[#EAEAEA] last:border-0">
      <div className="relative flex-shrink-0">
        <div
          className="w-2.5 h-2.5 rounded-full"
          style={{ backgroundColor: ok ? '#346538' : '#9F2F2D' }}
        />
        {ok && (
          <motion.div
            animate={{ scale: [1, 2, 1], opacity: [0.3, 0, 0.3] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="absolute inset-0 w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: '#346538' }}
          />
        )}
      </div>
      <span className="text-sm text-[#5F5F5C] flex-1">{label}</span>
      <span
        className="text-xs font-semibold font-mono px-2 py-0.5 rounded-full"
        style={{
          backgroundColor: ok ? '#EDF3EC' : '#FDEBEC',
          color: ok ? '#346538' : '#9F2F2D',
        }}
      >
        {ok ? '正常' : '异常'}
      </span>
    </div>
  )
}

const backendLabels = { wcdb: '本地数据库直读', direct: 'UIA 窗口读取' }
const aiLabels = { deepseek: 'DeepSeek', claude: 'Claude' }

export default function Dashboard({ status }) {
  const uptimeMin = Math.floor(status.uptime_sec / 60)
  const uptimeStr = uptimeMin < 60
    ? `${uptimeMin} 分钟`
    : `${Math.floor(uptimeMin / 60)} 小时 ${uptimeMin % 60} 分钟`
  const lastApi = status.last_api_call_sec_ago > 0
    ? `${Math.floor(status.last_api_call_sec_ago)} 秒前`
    : '暂无调用'

  return (
    <div className="space-y-10 max-w-6xl">
      <div className="grid grid-cols-3 gap-5">
        <MetricCard icon={ChatCircle} accent="green" label="已处理消息" value={status.messages_processed.toLocaleString()} sub={status.running ? '机器人运行中' : '机器人已停止'} />
        <MetricCard icon={Clock} accent="blue" label="运行时长" value={uptimeStr} sub={status.running ? '自上次启动' : '—'} />
        <MetricCard icon={Brain} accent="amber" label="最近 API 调用" value={lastApi} sub={`${aiLabels[status.ai_backend] || status.ai_backend || '—'} / ${backendLabels[status.wechat_backend] || status.wechat_backend || '—'}`} />
      </div>

      <div className="grid grid-cols-5 gap-5">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.1 }} className="bg-white border border-[#EAEAEA] rounded-xl p-7 col-span-3">
          <div className="flex items-center gap-2 mb-4">
            <Pulse size={16} weight="fill" className="text-[#346538]" />
            <h3 className="text-sm font-medium tracking-tight text-[#1F1F1F]">系统状态</h3>
          </div>
          <LiveIndicator label="数据库连接" ok={status.db_ok} />
          <LiveIndicator label="微信后端" ok={!!status.wechat_backend} />
          <LiveIndicator label="AI 后端" ok={!!status.ai_backend} />
          <LiveIndicator label="机器人进程" ok={status.running} />
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: 0.15 }} className="bg-white border border-[#EAEAEA] rounded-xl p-7 col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Database size={16} weight="fill" className="text-[#787774]" />
            <h3 className="text-sm font-medium tracking-tight text-[#1F1F1F]">后端信息</h3>
          </div>
          <div className="space-y-4">
            {[
              ['微信后端', backendLabels[status.wechat_backend] || status.wechat_backend || '—'],
              ['AI 后端', aiLabels[status.ai_backend] || status.ai_backend || '—'],
              ['日志文件', 'data/bot.log'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between items-center">
                <span className="text-xs text-[#787774]">{k}</span>
                <span className="text-xs font-mono text-[#5F5F5C]">{v}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="text-xs text-[#B8B8B6] font-mono">
        {status.timestamp ? `最近更新: ${status.timestamp}` : '等待首次状态更新...'}
      </motion.div>
    </div>
  )
}
