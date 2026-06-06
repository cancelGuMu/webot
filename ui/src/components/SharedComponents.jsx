import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Warning, Eye, EyeSlash } from '@phosphor-icons/react'

export const spring = { type: 'spring', stiffness: 200, damping: 25 }

export function Field({ label, hint, error, children }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <label className="block text-[14px] font-semibold text-text-main mb-1.5">{label}</label>
      {children}
      <AnimatePresence initial={false} mode="wait">
        {error ? (
          <motion.p
            key="error"
            initial={{ opacity: 0, height: 0, y: -4 }}
            animate={{ opacity: 1, height: 'auto', y: 0 }}
            exit={{ opacity: 0, height: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="text-xs text-[#d45656] flex items-center gap-1 mt-1.5 overflow-hidden"
          >
            <Warning size={12} />{error}
          </motion.p>
        ) : hint ? (
          <motion.p
            key="hint"
            initial={{ opacity: 0, height: 0, y: -4 }}
            animate={{ opacity: 1, height: 'auto', y: 0 }}
            exit={{ opacity: 0, height: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="text-xs text-text-muted mt-1.5 overflow-hidden"
          >
            {hint}
          </motion.p>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

export function Toggle({ enabled, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={`relative w-11 h-6 rounded-full shrink-0 transition-colors duration-200 border cursor-pointer outline-none focus:ring-2 focus:ring-brand-green/20
        ${enabled ? 'bg-brand-green-light border-brand-green/30' : 'bg-bg-raised border-border-main'}`}
    >
      <motion.span
        layout
        transition={{ type: 'spring', stiffness: 500, damping: 28 }}
        className="absolute top-0.5 left-0.5 w-4.5 h-4.5 rounded-full shadow-sm"
        animate={{
          x: enabled ? 20 : 0,
          backgroundColor: enabled ? '#18E299' : 'rgba(136, 136, 136, 0.6)',
        }}
      />
    </button>
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
        className="w-full bg-bg-raised border border-border-main rounded-full px-5 py-2.5 text-[14px] text-text-main
                   focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15
                   transition-all duration-200 cursor-pointer text-left
                   hover:border-text-muted/30 dark:hover:border-text-muted/40"
      >
        {selected ? `${selected.value}  ·  ${selected.desc}` : value}
      </button>
      <span
        className="absolute right-5 top-1/2 pointer-events-none select-none text-text-muted text-lg font-mono transition-all duration-200"
        style={{ transform: open ? 'translateY(-55%) rotate(90deg)' : 'translateY(-55%) rotate(0deg)' }}
      >&#8250;</span>

      {open && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute z-50 left-0 right-0 mt-1.5 bg-bg-card border border-border-main rounded-2xl shadow-xl overflow-hidden"
        >
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={`w-full text-left px-5 py-2.5 text-[14px] transition-colors flex items-center gap-3 font-mono cursor-pointer
                ${value === opt.value ? 'bg-brand-green-light text-brand-green-hover dark:text-brand-green font-semibold' : 'text-text-main hover:bg-bg-raised'}`}
            >
              <span className="w-[72px] shrink-0 font-semibold">{opt.value}</span>
              <span className="w-[4px] shrink-0 opacity-40 text-text-muted">·</span>
              <span className="w-[80px] shrink-0">{opt.desc}</span>
              <span className="w-[4px] shrink-0 opacity-40 text-text-muted">·</span>
              <span className="text-text-muted truncate">{opt.hint}</span>
            </button>
          ))}
        </motion.div>
      )}
    </div>
  )
}

export function Input({ type = 'text', value, onChange, placeholder }) {
  const [showPassword, setShowPassword] = useState(false)
  const isPassword = type === 'password'

  return (
    <div className="relative w-full flex items-center">
      <motion.input
        whileFocus={{ scale: 1.001 }}
        type={isPassword ? (showPassword ? 'text' : 'password') : type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full bg-bg-raised border border-border-main rounded-full pl-5 ${isPassword ? 'pr-12' : 'pr-5'} py-2.5 text-[14px] text-text-main
                   placeholder:text-text-muted/65 font-mono tabular-nums
                   focus:outline-none focus:border-brand-green focus:ring-2 focus:ring-brand-green/15
                   transition-all duration-200
                   hover:border-text-muted/30 dark:hover:border-text-muted/40`}
      />
      {isPassword && (
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className="absolute right-4 text-text-muted hover:text-text-main focus:outline-none transition-colors cursor-pointer"
        >
          {showPassword ? <EyeSlash size={18} /> : <Eye size={18} />}
        </button>
      )}
    </div>
  )
}
