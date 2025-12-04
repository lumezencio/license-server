import { motion } from 'framer-motion';

export default function Badge({ children, variant = 'default', size = 'md', className = '' }) {
  const variants = {
    default: 'bg-gradient-to-r from-slate-500/20 to-slate-600/20 border-slate-400/30 text-slate-200',
    success: 'bg-gradient-to-r from-emerald-500/20 to-green-600/20 border-emerald-400/30 text-emerald-200',
    warning: 'bg-gradient-to-r from-amber-500/20 to-yellow-600/20 border-amber-400/30 text-amber-200',
    danger: 'bg-gradient-to-r from-rose-500/20 to-red-600/20 border-rose-400/30 text-rose-200',
    info: 'bg-gradient-to-r from-blue-500/20 to-cyan-600/20 border-blue-400/30 text-blue-200',
    purple: 'bg-gradient-to-r from-purple-500/20 to-violet-600/20 border-purple-400/30 text-purple-200',
    pending: 'bg-gradient-to-r from-gray-500/20 to-gray-600/20 border-gray-400/30 text-gray-200',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
    lg: 'px-4 py-1.5 text-base',
  };

  return (
    <motion.span
      whileHover={{ scale: 1.05 }}
      className={`
        inline-flex items-center gap-1
        ${variants[variant]}
        ${sizes[size]}
        border backdrop-blur-sm
        rounded-full font-medium
        transition-all duration-300
        shadow-lg
        ${className}
      `}
    >
      {children}
    </motion.span>
  );
}
