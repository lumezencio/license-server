import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import AppBackground from '../AppBackground';

export default function Modal({ isOpen, onClose, title, children, size = 'lg' }) {
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
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[9999]"
          />

          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              onClick={(e) => e.stopPropagation()}
              className={`
                ${sizes[size]} w-full
                relative overflow-hidden
                rounded-2xl border border-white/20
                shadow-[0_20px_60px_rgba(0,0,0,0.7)]
                max-h-[85vh]
                flex flex-col
              `}
            >
              <div className="absolute inset-0 rounded-2xl overflow-hidden">
                <AppBackground patternOpacity={0.15} />
              </div>

              <div className="relative flex items-center justify-between px-6 py-4 border-b border-white/10 bg-black/20 backdrop-blur-sm flex-shrink-0">
                <h2 className="text-xl font-bold text-white">
                  {title}
                </h2>
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-white" />
                </button>
              </div>

              <div className="relative flex-1 overflow-y-auto p-6">
                {children}
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
