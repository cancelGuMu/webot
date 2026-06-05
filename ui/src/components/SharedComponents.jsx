import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Warning } from '@phosphor-icons/react'

export const spring = { type: 'spring', stiffness: 200, damping: 25 }

export function Field({ label, hint, error, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <label className="block text-[15px] font-medium text-[#1F1F1F] mb-1.5">{label}</label>
      {children}
      {hint && !error && <p className="text-xs text-[#B8B8B6] mt-1.5">{hint}</p>}
      {error && <p className="text-xs text-[#9F2F2D] flex items-center gap-1 mt-1.5"><Warning size={12} />{error}</p>}
    </div>
  )
}

export function Toggle({ enabled, onChange }) {
  const w = 64, d = 24, mx = 5, my = 3
  const travel = w - d - mx * 2

  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      onClick={() => onChange(!enabled)}
      className="relative rounded-full shrink-0 transition-colors duration-300"
      style={{
        width: w, height: d + my * 2,
        backgroundColor: enabled ? 'rgb(52 101 56 / 0.12)' : '#EBEBE9',
        border: enabled ? '1px solid rgb(52 101 56 / 0.28)' : '1px solid #D4D4D2',
      }}
    >
      <span
        className="absolute text-[11px] font-semibold select-none pointer-events-none"
        style={{ left: mx + 2, top: '50%', transform: 'translateY(-50%)', color: '#346538', opacity: enabled ? 1 : 0, transition: 'opacity 0.15s' }}
      >ON</span>
      <span
        className="absolute text-[11px] font-semibold select-none pointer-events-none"
        style={{ right: mx + 2, top: '50%', transform: 'translateY(-50%)', color: '#B0B0AE', opacity: enabled ? 0 : 1, transition: 'opacity 0.15s' }}
      >OFF</span>
      <motion.div
        animate={{ x: enabled ? travel : 0 }}
        transition={spring}
        className="absolute rounded-full"
        style={{
          top: my, left: mx,
          width: d, height: d,
          backgroundColor: enabled ? '#346538' : '#B0B0AE',
        }}
      />
    </motion.button>
  )
}

export function Select({ value, onChange, options }) {
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
        className="w-full bg-[#F9F9F8] border border-[#E0E0DE] rounded-lg pl-4 pr-10 py-2.5 text-[15px] text-[#1F1F1F]
                   focus:outline-none focus:border-[#C5DAC2] focus:ring-1 focus:ring-[#346538]/15
                   transition-all duration-200 cursor-pointer text-left
                   hover:border-[#D0D0CE]"
      >
        {selected ? `${selected.value}  ·  ${selected.desc}` : value}
      </button>
      <span
        className="absolute right-3 top-1/2 pointer-events-none select-none text-[#B8B8B6] text-lg font-mono transition-all duration-200"
        style={{ transform: open ? 'translateY(-55%) rotate(90deg)' : 'translateY(-55%) rotate(0deg)' }}
      >&#8250;</span>

      {open && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute z-50 left-0 right-0 mt-1 bg-white border border-[#EAEAEA] rounded-lg shadow-[0_4px_16px_rgba(0,0,0,0.06)] overflow-hidden"
        >
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-4 py-2.5 text-[15px] transition-colors flex items-center gap-3 font-mono
                ${value === opt.value ? 'bg-[#EDF3EC] text-[#346538]' : 'text-[#1F1F1F] hover:bg-[#F7F6F3]'}`}
            >
              <span className="w-[72px] shrink-0 font-semibold">{opt.value}</span>
              <span className="w-[4px] shrink-0 text-[#D0D0CE]">·</span>
              <span className="w-[80px] shrink-0">{opt.desc}</span>
              <span className="w-[4px] shrink-0 text-[#D0D0CE]">·</span>
              <span className="text-[#787774] truncate">{opt.hint}</span>
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}

export function Input({ type = 'text', value, onChange, placeholder }) {
  return (
    <motion.input
      whileFocus={{ scale: 1.003 }}
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full bg-[#F9F9F8] border border-[#E0E0DE] rounded-lg px-4 py-2.5 text-[15px] text-[#1F1F1F]
                 placeholder:text-[#C8C8C6] font-mono tabular-nums
                 focus:outline-none focus:border-[#C5DAC2] focus:ring-1 focus:ring-[#346538]/15
                 transition-all duration-200
                 hover:border-[#D0D0CE]"
    />
  )
}
