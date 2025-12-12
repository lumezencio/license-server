import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  icon: Icon,
  loading = false,
  disabled = false,
  className = '',
  ...props
}) {
  const variants = {
    primary: 'bg-[var(--ds-cyan)] hover:bg-[var(--ds-cyan-hover)] text-[var(--ds-bg-page)] shadow-lg shadow-cyan-500/20',
    secondary: 'bg-transparent border border-[var(--ds-border)] hover:border-[var(--ds-cyan)] text-[var(--ds-text-primary)] hover:text-[var(--ds-cyan)]',
    success: 'bg-[var(--ds-green)] hover:brightness-110 text-[var(--ds-bg-page)] shadow-lg shadow-green-500/20',
    danger: 'bg-[var(--ds-red)] hover:brightness-110 text-white shadow-lg shadow-red-500/20',
    warning: 'bg-[var(--ds-yellow)] hover:brightness-110 text-[var(--ds-bg-page)] shadow-lg shadow-yellow-500/20',
    ghost: 'bg-white/5 hover:bg-white/10 border border-[var(--ds-border)] text-[var(--ds-text-primary)]',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-sm h-9',
    md: 'px-5 py-2.5 text-sm h-11',
    lg: 'px-6 py-3 text-base h-12',
  };

  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.02, y: disabled ? 0 : -1 }}
      whileTap={{ scale: disabled ? 1 : 0.98 }}
      disabled={disabled || loading}
      className={`
        ${variants[variant]}
        ${sizes[size]}
        rounded-lg font-semibold
        flex items-center justify-center gap-2
        transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        relative overflow-hidden
        ${className}
      `}
      {...props}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {!loading && Icon && <Icon className="w-4 h-4" />}
      <span className="relative z-10">{children}</span>
    </motion.button>
  );
}
