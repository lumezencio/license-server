import { motion } from 'framer-motion';

export default function Badge({ children, variant = 'default', size = 'md', className = '' }) {
  const variants = {
    default: 'bg-slate-500/20 border-slate-400/30 text-slate-300',
    success: 'bg-[var(--ds-green)]/20 border-[var(--ds-green)]/30 text-[var(--ds-green)]',
    warning: 'bg-[var(--ds-yellow)]/20 border-[var(--ds-yellow)]/30 text-[var(--ds-yellow)]',
    danger: 'bg-[var(--ds-red)]/20 border-[var(--ds-red)]/30 text-[var(--ds-red)]',
    info: 'bg-[var(--ds-cyan)]/20 border-[var(--ds-cyan)]/30 text-[var(--ds-cyan)]',
    purple: 'bg-[var(--ds-purple)]/20 border-[var(--ds-purple)]/30 text-[var(--ds-purple)]',
    pending: 'bg-gray-500/20 border-gray-400/30 text-gray-300',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-xs',
    lg: 'px-4 py-1.5 text-sm',
  };

  return (
    <motion.span
      whileHover={{ scale: 1.03 }}
      className={`
        inline-flex items-center gap-1
        ${variants[variant]}
        ${sizes[size]}
        border
        rounded-full font-medium
        transition-all duration-200
        ${className}
      `}
    >
      {children}
    </motion.span>
  );
}
