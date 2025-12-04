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
        <label className="block text-sm font-semibold text-white mb-2">
          {label}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-white/70" />
        )}
        <motion.input
          whileFocus={{ scale: 1.005 }}
          type={type}
          onChange={handleChange}
          {...props}
          style={shouldUppercase ? { textTransform: 'uppercase' } : undefined}
          className={`
            w-full ${Icon ? 'pl-12' : 'pl-4'} pr-4 py-3
            bg-white/10 backdrop-blur-sm border ${error ? 'border-red-400' : 'border-white/30'}
            rounded-xl text-white font-medium placeholder-white/50
            focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
            focus:bg-white/15
            transition-all
            ${props.className || ''}
          `}
        />
      </div>
      {error && (
        <p className="mt-1 text-sm font-semibold text-red-300">{error}</p>
      )}
    </div>
  );
}
