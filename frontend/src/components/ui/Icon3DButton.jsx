import React from 'react';
import { motion } from 'framer-motion';

const Icon3DButton = ({
  icon: IconComponent,
  onClick,
  label,
  className = '',
  disabled = false,
  type = 'button',
  variant = 'primary',
  size = 'default'
}) => {

  const DEPTH = 4;

  const colors = {
    primary: {
      gradient: 'linear-gradient(180deg, #3b82f6 0%, #2563eb 100%)',
      shadowColor: '#1e40af',
      ring: 'focus:ring-blue-500',
      border: '1px solid #1e40af',
    },
    secondary: {
      gradient: 'linear-gradient(180deg, #6b7280 0%, #4b5563 100%)',
      shadowColor: '#374151',
      ring: 'focus:ring-gray-500',
      border: '1px solid #374151',
    },
    success: {
      gradient: 'linear-gradient(180deg, #22c55e 0%, #16a34a 100%)',
      shadowColor: '#166534',
      ring: 'focus:ring-green-500',
      border: '1px solid #166534',
    },
    danger: {
      gradient: 'linear-gradient(180deg, #ef4444 0%, #dc2626 100%)',
      shadowColor: '#991b1b',
      ring: 'focus:ring-red-500',
      border: '1px solid #991b1b',
    },
    purple: {
      gradient: 'linear-gradient(180deg, #a78bfa 0%, #8b5cf6 100%)',
      shadowColor: '#6d28d9',
      ring: 'focus:ring-purple-500',
      border: '1px solid #6d28d9',
    },
    cyan: {
      gradient: 'linear-gradient(180deg, #22d3ee 0%, #06b6d4 100%)',
      shadowColor: '#0e7490',
      ring: 'focus:ring-cyan-500',
      border: '1px solid #0e7490',
    },
    gold: {
      gradient: 'linear-gradient(180deg, #f59e0b 0%, #d97706 100%)',
      shadowColor: '#b45309',
      ring: 'focus:ring-amber-500',
      border: '1px solid #b45309',
    },
    amber: {
      gradient: 'linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%)',
      shadowColor: '#b45309',
      ring: 'focus:ring-amber-500',
      border: '1px solid #b45309',
    },
  };

  const ambientShadow = '0px 5px 15px rgba(0, 0, 0, 0.3)';

  const sizes = {
    small: 'px-3 py-1.5 text-sm',
    default: 'px-5 py-2.5 text-base',
    large: 'px-8 py-4 text-lg',
    iconOnly: 'px-2.5 py-2 text-base',
  };

  const variantStyles = colors[variant] || colors.primary;
  const sizeStyles = sizes[size] || sizes.default;

  const disabledStyles = 'bg-gray-500 cursor-not-allowed text-gray-300 shadow-inner border border-gray-600';
  const buttonStyles = disabled ? disabledStyles : 'text-white border-t border-white/25';

  const isIconOnly = size === 'iconOnly' || (!label && IconComponent);
  const finalSizeStyles = isIconOnly ? sizes.iconOnly : sizeStyles;

  const borderRadius = 'rounded-lg';

  const initialShadowDepth = `0px ${DEPTH}px 0px ${variantStyles.shadowColor}`;
  const initialBoxShadow = !disabled ? `${initialShadowDepth}, ${ambientShadow}` : 'none';

  const renderIcon = () => {
    if (!IconComponent) return null;

    if (React.isValidElement(IconComponent)) {
      return <span className={label ? "mr-2" : ""}>{IconComponent}</span>;
    }

    if (typeof IconComponent === 'function' || IconComponent.$$typeof) {
      const Icon = IconComponent;
      return <span className={label ? "mr-2" : ""}><Icon className="w-4 h-4" /></span>;
    }

    return null;
  };

  return (
    <motion.button
      initial={{ y: 0, boxShadow: initialBoxShadow }}
      whileHover={!disabled ? {
        y: -1,
        boxShadow: `${initialShadowDepth}, 0px 8px 25px rgba(0, 0, 0, 0.4)`
      } : {}}
      whileTap={!disabled ? {
        y: DEPTH / 2,
        boxShadow: `0px ${DEPTH / 2}px 0px ${variantStyles.shadowColor}, 0px 3px 10px rgba(0, 0, 0, 0.2)`
      } : {}}
      transition={{ duration: 0.1 }}
      onClick={onClick}
      disabled={disabled}
      type={type}
      className={`flex items-center justify-center font-semibold ${borderRadius} transform focus:outline-none focus:ring-2 focus:ring-offset-2 ${variantStyles.ring} ${buttonStyles} ${finalSizeStyles} ${className}`}
      style={{
        background: !disabled ? variantStyles.gradient : undefined,
        border: !disabled ? variantStyles.border : undefined,
        textShadow: !disabled ? '0px 1px 2px rgba(0,0,0,0.3)' : 'none',
      }}
    >
      {renderIcon()}
      {label}
    </motion.button>
  );
};

export default Icon3DButton;
