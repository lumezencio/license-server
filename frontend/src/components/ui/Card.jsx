import { motion } from 'framer-motion';

export default function Card({ children, className = '', hover = true, ...props }) {
  return (
    <motion.div
      whileHover={hover ? { scale: 1.005, y: -2 } : {}}
      className={`
        bg-[var(--ds-bg-card)]
        border border-[var(--ds-border)]
        rounded-xl
        shadow-xl shadow-black/20
        overflow-hidden
        transition-all duration-300
        hover:border-[var(--ds-border-hover)]
        ${className}
      `}
      {...props}
    >
      {children}
    </motion.div>
  );
}

export function CardHeader({ children, className = '' }) {
  return (
    <div className={`px-5 py-4 border-b border-[var(--ds-border)] ${className}`}>
      {children}
    </div>
  );
}

export function CardContent({ children, className = '' }) {
  return (
    <div className={`p-5 ${className}`}>
      {children}
    </div>
  );
}
