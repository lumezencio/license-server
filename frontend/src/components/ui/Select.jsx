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
        <label className="block text-sm font-semibold text-white mb-2">
          {label}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/70" />
        )}
        <motion.select
          whileFocus={{ scale: 1.005 }}
          {...props}
          className={`
            w-full ${Icon ? 'pl-12' : 'pl-4'} pr-4 py-3
            bg-white/10 backdrop-blur-sm border ${error ? 'border-red-400' : 'border-white/30'}
            rounded-xl text-white font-medium
            focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
            focus:bg-white/15
            transition-all
            appearance-none cursor-pointer
            ${props.className || ''}
          `}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-slate-800 text-white">
              {opt.label}
            </option>
          ))}
        </motion.select>
        <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
          <svg className="w-5 h-5 text-white/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {error && (
        <p className="mt-1 text-sm font-semibold text-red-300">{error}</p>
      )}
    </div>
  );
}
