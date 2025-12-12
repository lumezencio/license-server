import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

export default function Modal({ isOpen, onClose, title, children, size = 'lg', icon: Icon }) {
  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-2xl',
    lg: 'max-w-4xl',
    xl: 'max-w-6xl',
    full: 'max-w-[95vw]',
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[9999]"
          />

          {/* Modal Container - Responsivo */}
          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-4 md:items-center">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              onClick={(e) => e.stopPropagation()}
              className={`
                ${sizes[size]} w-full
                relative overflow-hidden
                rounded-t-xl sm:rounded-xl
                bg-[var(--ds-bg-card)]
                border border-[var(--ds-border)]
                shadow-[0_20px_60px_rgba(0,0,0,0.8)]
                max-h-[90vh] sm:max-h-[85vh]
                flex flex-col
                mt-auto sm:mt-0
              `}
            >
              {/* Background Pattern */}
              <div
                className="absolute inset-0 pointer-events-none opacity-30"
                style={{
                  backgroundImage: 'radial-gradient(circle, rgba(148, 163, 184, 0.08) 1px, transparent 1px)',
                  backgroundSize: '24px 24px',
                }}
              />

              {/* Header - Fixo */}
              <div className="relative flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-[var(--ds-border)] bg-black/20 flex-shrink-0">
                <h2 className="flex items-center gap-2 sm:gap-3 text-base sm:text-lg font-bold text-[var(--ds-text-primary)]">
                  {Icon && (
                    <span className="flex items-center justify-center w-8 h-8 sm:w-10 sm:h-10 rounded-lg bg-[var(--ds-cyan)]/10 border border-[var(--ds-cyan)]/30">
                      <Icon className="w-4 h-4 sm:w-5 sm:h-5 text-[var(--ds-cyan)]" />
                    </span>
                  )}
                  <span className="truncate">{title}</span>
                </h2>
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-white/10 rounded-lg transition-all duration-200 hover:rotate-90 flex-shrink-0"
                >
                  <X className="w-5 h-5 text-[var(--ds-text-secondary)] hover:text-[var(--ds-text-primary)]" />
                </button>
              </div>

              {/* Content - Scroll */}
              <div className="relative flex-1 overflow-y-auto p-4 sm:p-6 overscroll-contain">
                {children}
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
