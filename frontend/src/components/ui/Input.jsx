import { motion } from 'framer-motion';

// Tipos de input que NÃO devem ser convertidos para maiúsculo
const NO_UPPERCASE_TYPES = ['email', 'password', 'url', 'search', 'number', 'date', 'time', 'datetime-local'];

export default function Input({
  label,
  icon: Icon,
  error,
  className = '',
  uppercase = true,
  onChange,
  type = 'text',
  ...props
}) {
  // Determina se deve aplicar uppercase
  const shouldUppercase = uppercase && !NO_UPPERCASE_TYPES.includes(type);

  // Handler que converte para maiúsculo
  const handleChange = (e) => {
    if (shouldUppercase && e.target.value) {
      e.target.value = e.target.value.toUpperCase();
    }
    if (onChange) {
      onChange(e);
    }
  };

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
        <motion.input
          whileFocus={{ scale: 1.002 }}
          type={type}
          onChange={handleChange}
          {...props}
          style={shouldUppercase ? { textTransform: 'uppercase' } : undefined}
          className={`
            w-full ${Icon ? 'pl-11' : 'pl-4'} pr-4 py-3
            bg-[var(--ds-bg-input)] border ${error ? 'border-[var(--ds-red)]' : 'border-[var(--ds-border)]'}
            rounded-lg text-[var(--ds-text-primary)] font-medium placeholder-[var(--ds-text-muted)]
            focus:outline-none focus:border-[var(--ds-border-focus)] focus:ring-2 focus:ring-[var(--ds-cyan)]/20
            hover:border-[var(--ds-border-hover)]
            transition-all duration-200
            ${props.className || ''}
          `}
        />
      </div>
      {error && (
        <p className="mt-1 text-[var(--ds-font-size-xs)] font-medium text-[var(--ds-red)]">{error}</p>
      )}
    </div>
  );
}
