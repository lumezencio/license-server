import { motion } from 'framer-motion';

export default function Select({
  label,
  icon: Icon,
  error,
  options = [],
  className = '',
  ...props
}) {
  return (
    <div className={className}>
      {label && (
        <label className="block text-[var(--ds-font-size-xs)] font-medium text-[var(--ds-text-muted)] uppercase tracking-wide mb-1.5">
          {label}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--ds-text-secondary)]" />
        )}
        <motion.select
          whileFocus={{ scale: 1.002 }}
          {...props}
          className={`
            w-full ${Icon ? 'pl-11' : 'pl-4'} pr-10 py-3
            bg-[var(--ds-bg-input)] border ${error ? 'border-[var(--ds-red)]' : 'border-[var(--ds-border)]'}
            rounded-lg text-[var(--ds-text-primary)] font-medium
            focus:outline-none focus:border-[var(--ds-border-focus)] focus:ring-2 focus:ring-[var(--ds-cyan)]/20
            hover:border-[var(--ds-border-hover)]
            transition-all duration-200
            appearance-none cursor-pointer
            ${props.className || ''}
          `}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-[#0d1221] text-white">
              {opt.label}
            </option>
          ))}
        </motion.select>
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
          <svg className="w-5 h-5 text-[var(--ds-text-secondary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {error && (
        <p className="mt-1 text-[var(--ds-font-size-xs)] font-medium text-[var(--ds-red)]">{error}</p>
      )}
    </div>
  );
}
