import { Loader2 } from 'lucide-react';

export default function LoadingSpinner({ size = 'md', className = '' }) {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
    xl: 'w-16 h-16',
  };

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <Loader2 className={`${sizes[size]} animate-spin text-[var(--ds-cyan)]`} />
    </div>
  );
}

export function FullPageLoader() {
  return (
    <div className="fixed inset-0 bg-[var(--ds-bg-page)]/95 flex items-center justify-center z-50">
      <div className="text-center">
        <LoadingSpinner size="xl" />
        <p className="mt-4 text-[var(--ds-text-secondary)] font-medium">Carregando...</p>
      </div>
    </div>
  );
}
