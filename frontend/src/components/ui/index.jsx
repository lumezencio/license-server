// ============================================
// DESIGN SYSTEM - LICENSE SERVER
// Componentes UI Reutilizaveis
// ============================================

import React, { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { Loader2, Package } from 'lucide-react';

// ============================================
// CORES E ESTILOS BASE
// ============================================
const DS = {
  colors: {
    bgPage: '#070b14',
    bgCard: '#0d1221',
    bgInput: '#0f172a',
    cyan: '#06b6d4',
    cyanHover: '#0891b2',
    blue: '#3b82f6',
    purple: '#8b5cf6',
    green: '#22c55e',
    red: '#ef4444',
    yellow: '#eab308',
    orange: '#f97316',
    textPrimary: '#ffffff',
    textSecondary: '#94a3b8',
    textMuted: '#64748b',
    border: 'rgba(148, 163, 184, 0.2)',
    borderHover: 'rgba(148, 163, 184, 0.4)',
  },
  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    xl: '16px',
  },
  space: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
  }
};

// ============================================
// FORM SECTION
// ============================================
export const FormSection = ({
  title,
  children,
  variant = 'default',
  icon: Icon,
  className = ''
}) => {
  const titleColor = variant === 'alert' ? DS.colors.orange : DS.colors.cyan;

  return (
    <fieldset
      className={`ds-section ${variant === 'alert' ? 'ds-section--alert' : ''} ${className}`}
      style={{
        border: `1px solid ${DS.colors.border}`,
        borderRadius: DS.radius.lg,
        padding: '20px',
        marginBottom: DS.space.lg,
        background: DS.colors.bgCard,
      }}
    >
      <legend
        className="ds-section__title"
        style={{
          color: titleColor,
          fontSize: '12px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '0 10px',
          marginLeft: '8px',
        }}
      >
        <span style={{
          width: '3px',
          height: '12px',
          background: titleColor,
          borderRadius: '2px',
          flexShrink: 0,
        }} />
        {Icon && (
          <span style={{ width: '14px', height: '14px', flexShrink: 0, display: 'flex', alignItems: 'center' }}>
            <Icon style={{ width: '14px', height: '14px' }} />
          </span>
        )}
        {title}
      </legend>
      {children}
    </fieldset>
  );
};

// ============================================
// FORM GRID
// ============================================
export const FormGrid = ({
  children,
  cols = 1,
  variant = 'default',
  className = ''
}) => {
  const getGridColumns = () => {
    if (variant === 'cliente') return '200px 1fr 180px';
    if (variant === 'credito') return 'repeat(4, 1fr)';
    if (variant === 'endereco') return '1fr 120px 1fr';
    if (variant === 'cidade') return '1fr 80px 140px 1fr';
    return `repeat(${cols}, 1fr)`;
  };

  return (
    <div
      className={`ds-grid ds-grid--${cols} ${className}`}
      style={{
        display: 'grid',
        gridTemplateColumns: getGridColumns(),
        gap: DS.space.md,
      }}
    >
      {children}
    </div>
  );
};

// ============================================
// FORM FIELD
// ============================================
export const FormField = ({
  label,
  required = false,
  error,
  hint,
  children,
  className = ''
}) => (
  <div className={`ds-field ${className}`} style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
    {label && (
      <label
        className={`ds-label ${required ? 'ds-label--required' : ''}`}
        style={{
          color: DS.colors.textMuted,
          fontSize: '11px',
          fontWeight: 500,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        {label}
        {required && <span style={{ color: DS.colors.red }}> *</span>}
      </label>
    )}
    {children}
    {error && <span className="ds-error" style={{ color: DS.colors.red, fontSize: '11px', marginTop: '4px' }}>{error}</span>}
    {hint && !error && <span className="ds-hint" style={{ color: DS.colors.textMuted, fontSize: '11px', marginTop: '4px' }}>{hint}</span>}
  </div>
);

// ============================================
// FORM INPUT
// ============================================
export const FormInput = forwardRef(({
  variant = 'default',
  error = false,
  className = '',
  style,
  ...props
}, ref) => {
  const getTextColor = () => {
    if (variant === 'positive') return DS.colors.green;
    if (variant === 'negative') return DS.colors.red;
    if (variant === 'warning') return DS.colors.yellow;
    return DS.colors.textPrimary;
  };

  return (
    <input
      ref={ref}
      className={`ds-input ${error ? 'ds-input--error' : ''} ${className}`}
      style={{
        background: DS.colors.bgInput,
        border: `1px solid ${error ? DS.colors.red : DS.colors.border}`,
        borderRadius: DS.radius.md,
        padding: '12px 14px',
        height: '44px',
        color: getTextColor(),
        fontSize: '14px',
        fontFamily: variant === 'money' || variant === 'positive' || variant === 'negative' ? "'JetBrains Mono', monospace" : 'inherit',
        textAlign: variant === 'money' ? 'right' : 'left',
        width: '100%',
        outline: 'none',
        transition: 'all 0.2s ease',
        ...style,
      }}
      {...props}
    />
  );
});
FormInput.displayName = 'FormInput';

// ============================================
// FORM SELECT
// ============================================
export const FormSelect = forwardRef(({
  options = [],
  placeholder,
  className = '',
  ...props
}, ref) => (
  <select
    ref={ref}
    className={`ds-select ${className}`}
    style={{
      background: DS.colors.bgInput,
      border: `1px solid ${DS.colors.border}`,
      borderRadius: DS.radius.md,
      padding: '12px 40px 12px 14px',
      height: '44px',
      color: DS.colors.textPrimary,
      fontSize: '14px',
      width: '100%',
      cursor: 'pointer',
      outline: 'none',
      appearance: 'none',
      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`,
      backgroundRepeat: 'no-repeat',
      backgroundPosition: 'right 12px center',
      backgroundSize: '20px',
    }}
    {...props}
  >
    {placeholder && <option value="" disabled>{placeholder}</option>}
    {options.map((opt) => (
      <option key={opt.value} value={opt.value}>{opt.label}</option>
    ))}
  </select>
));
FormSelect.displayName = 'FormSelect';

// ============================================
// FORM TEXTAREA
// ============================================
export const FormTextarea = forwardRef(({
  error = false,
  className = '',
  ...props
}, ref) => (
  <textarea
    ref={ref}
    className={`ds-textarea ${className}`}
    style={{
      background: DS.colors.bgInput,
      border: `1px solid ${error ? DS.colors.red : DS.colors.border}`,
      borderRadius: DS.radius.md,
      padding: '12px 14px',
      color: DS.colors.textPrimary,
      fontSize: '14px',
      width: '100%',
      minHeight: '100px',
      resize: 'vertical',
      outline: 'none',
      fontFamily: 'inherit',
    }}
    {...props}
  />
));
FormTextarea.displayName = 'FormTextarea';

// ============================================
// FORM SEARCH
// ============================================
export const FormSearch = ({
  placeholder = 'Digite para buscar...',
  value,
  onChange,
  onSearch,
  shortcutKey,
  disabled = false,
  className = ''
}) => (
  <div className={`ds-search ${className}`} style={{ display: 'flex', gap: DS.space.sm, alignItems: 'center' }}>
    <input
      type="text"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      onKeyDown={(e) => e.key === 'Enter' && onSearch?.()}
      disabled={disabled}
      style={{
        flex: 1,
        background: DS.colors.bgInput,
        border: `1px solid ${DS.colors.border}`,
        borderRadius: DS.radius.md,
        padding: '12px 14px',
        height: '44px',
        color: DS.colors.textPrimary,
        fontSize: '14px',
        outline: 'none',
      }}
    />
    <button
      onClick={onSearch}
      disabled={disabled}
      type="button"
      style={{
        background: DS.colors.cyan,
        border: 'none',
        borderRadius: DS.radius.md,
        width: '44px',
        height: '44px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'all 0.2s ease',
      }}
    >
      <svg style={{ width: '18px', height: '18px', color: DS.colors.bgPage }} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
        <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
      </svg>
    </button>
    {shortcutKey && (
      <kbd style={{
        background: 'rgba(255, 255, 255, 0.1)',
        padding: '4px 10px',
        borderRadius: DS.radius.sm,
        fontSize: '11px',
        fontFamily: "'JetBrains Mono', monospace",
        color: DS.colors.textSecondary,
        display: 'flex',
        alignItems: 'center',
        height: '28px',
      }}>
        {shortcutKey}
      </kbd>
    )}
  </div>
);

// ============================================
// FORM TABLE
// ============================================
export function FormTable({
  columns = [],
  data = [],
  emptyMessage = 'Nenhum item encontrado',
  emptyHint = 'Adicione itens para visualizar',
  onRowClick,
  renderCell,
  renderActions,
  className = ''
}) {
  const gridTemplate = columns.map(c => c.width || '1fr').join(' ') + (renderActions ? ' 120px' : '');

  const gridStyle = {
    display: 'grid',
    gridTemplateColumns: gridTemplate,
    alignItems: 'center',
  };

  return (
    <div className={`ds-table ${className}`} style={{ width: '100%', overflowX: 'auto' }}>
      {/* HEADER */}
      <div className="ds-table__header" style={{
        ...gridStyle,
        padding: '12px 16px',
        borderBottom: `1px solid ${DS.colors.border}`,
        background: 'rgba(6, 182, 212, 0.05)',
      }}>
        {columns.map(col => (
          <div key={col.key} className="ds-table__header-cell" style={{
            color: DS.colors.cyan,
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.03em',
            padding: '0 8px',
          }}>
            {col.label}
          </div>
        ))}
        {renderActions && (
          <div className="ds-table__header-cell" style={{
            color: DS.colors.cyan,
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.03em',
            padding: '0 8px',
          }}>
            Acoes
          </div>
        )}
      </div>

      {/* BODY */}
      <div className="ds-table__body" style={{ minHeight: '100px' }}>
        {data.length === 0 ? (
          <div className="ds-table__empty" style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '48px',
            color: DS.colors.textMuted,
          }}>
            <Package style={{ width: '48px', height: '48px', opacity: 0.5, marginBottom: '16px' }} />
            <span style={{ fontSize: '14px', color: DS.colors.textSecondary, marginBottom: '4px' }}>{emptyMessage}</span>
            <span style={{ fontSize: '12px', color: DS.colors.textMuted }}>{emptyHint}</span>
          </div>
        ) : (
          data.map((row, i) => (
            <div
              key={i}
              className="ds-table__row"
              style={{
                ...gridStyle,
                padding: '14px 16px',
                borderBottom: `1px solid ${DS.colors.border}`,
                cursor: onRowClick ? 'pointer' : 'default',
                transition: 'background 0.2s ease',
              }}
              onClick={() => onRowClick?.(row, i)}
              onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(6, 182, 212, 0.05)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              {columns.map(col => (
                <div key={col.key} className="ds-table__cell" style={{
                  color: DS.colors.textPrimary,
                  fontSize: '13px',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0 8px',
                  minHeight: '40px',
                }}>
                  {renderCell ? renderCell(col.key, row[col.key], row) : row[col.key]}
                </div>
              ))}
              {renderActions && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0 8px',
                  minHeight: '40px',
                  gap: '8px',
                }}>
                  {renderActions(row, i)}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ============================================
// FORM TOTALS
// ============================================
export const FormTotals = ({ items = [], className = '' }) => (
  <div
    className={`ds-totals ${className}`}
    style={{
      display: 'grid',
      gridTemplateColumns: `repeat(${items.length}, 1fr)`,
      gap: DS.space.md,
      padding: DS.space.lg,
      background: 'rgba(0, 0, 0, 0.2)',
      borderRadius: DS.radius.md,
      marginTop: DS.space.md,
    }}
  >
    {items.map((item, i) => (
      <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: DS.space.xs }}>
        <span style={{
          color: DS.colors.textMuted,
          fontSize: '11px',
          textTransform: 'uppercase',
          letterSpacing: '0.03em',
        }}>
          {item.label}
        </span>
        <span style={{
          color: item.variant === 'positive' ? DS.colors.green : item.variant === 'negative' ? DS.colors.red : DS.colors.textPrimary,
          fontSize: '20px',
          fontWeight: 600,
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {item.value}
        </span>
      </div>
    ))}
  </div>
);

// ============================================
// FORM FOOTER
// ============================================
export const FormFooter = ({ leftContent, rightContent, className = '' }) => (
  <footer
    className={`ds-footer ${className}`}
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: DS.space.lg,
      background: DS.colors.bgCard,
      border: `1px solid ${DS.colors.border}`,
      borderRadius: DS.radius.lg,
      marginTop: DS.space.lg,
      flexWrap: 'wrap',
      gap: DS.space.md,
    }}
  >
    <div style={{ display: 'flex', gap: DS.space.md }}>{leftContent}</div>
    <div style={{ display: 'flex', gap: DS.space.md }}>{rightContent}</div>
  </footer>
);

// ============================================
// STATUS INDICATOR
// ============================================
export const StatusIndicator = ({ status, className = '' }) => {
  const getColor = () => {
    if (status === 'pending') return DS.colors.yellow;
    if (status === 'success' || status === 'paid' || status === 'active') return DS.colors.green;
    if (status === 'error' || status === 'overdue' || status === 'revoked' || status === 'expired') return DS.colors.red;
    if (status === 'suspended' || status === 'warning') return DS.colors.orange;
    return DS.colors.cyan;
  };
  const isFilled = status !== 'pending';

  return (
    <span
      className={`ds-status ds-status--${status} ${className}`}
      style={{
        width: '12px',
        height: '12px',
        borderRadius: '50%',
        border: `2px solid ${getColor()}`,
        background: isFilled ? getColor() : 'transparent',
        flexShrink: 0,
        display: 'inline-block',
      }}
    />
  );
};

// ============================================
// FORM BUTTON
// ============================================
export const FormButton = ({
  variant = 'primary',
  size = 'default',
  loading = false,
  icon: Icon,
  children,
  disabled,
  className = '',
  ...props
}) => {
  const getBackground = () => {
    if (variant === 'primary') return DS.colors.cyan;
    if (variant === 'success') return DS.colors.green;
    if (variant === 'danger') return DS.colors.red;
    if (variant === 'warning') return DS.colors.yellow;
    return 'transparent';
  };

  const getHeight = () => size === 'sm' ? '36px' : '44px';
  const getPadding = () => size === 'icon' ? '0' : size === 'sm' ? '0 16px' : '0 24px';
  const getWidth = () => size === 'icon' ? (size === 'sm' ? '36px' : '44px') : 'auto';

  return (
    <button
      className={`ds-button ds-button--${variant} ${size === 'sm' ? 'ds-button--sm' : ''} ${className}`}
      disabled={disabled || loading}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: DS.space.sm,
        padding: getPadding(),
        height: getHeight(),
        width: getWidth(),
        borderRadius: DS.radius.md,
        fontSize: size === 'sm' ? '13px' : '14px',
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        border: variant === 'secondary' ? `1px solid ${DS.colors.border}` : 'none',
        background: getBackground(),
        color: variant === 'secondary' ? DS.colors.textPrimary : DS.colors.bgPage,
        opacity: disabled ? 0.5 : 1,
        transition: 'all 0.2s ease',
      }}
      {...props}
    >
      {loading ? <Loader2 className="w-4 h-4 animate-spin" style={{ animation: 'spin 1s linear infinite' }} /> : (Icon && <Icon style={{ width: '16px', height: '16px' }} />)}
      {children}
    </button>
  );
};

// ============================================
// STAT CARD
// ============================================
export const StatCard = ({
  icon: Icon,
  label,
  value,
  variant = 'blue',
  className = ''
}) => {
  const iconColors = {
    blue: { bg: 'linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2))', color: DS.colors.blue },
    green: { bg: 'linear-gradient(135deg, rgba(34, 197, 94, 0.2), rgba(16, 185, 129, 0.2))', color: DS.colors.green },
    yellow: { bg: 'linear-gradient(135deg, rgba(234, 179, 8, 0.2), rgba(245, 158, 11, 0.2))', color: DS.colors.yellow },
    purple: { bg: 'linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(168, 85, 247, 0.2))', color: DS.colors.purple },
    cyan: { bg: 'linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(20, 184, 166, 0.2))', color: DS.colors.cyan },
    red: { bg: 'linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(244, 63, 94, 0.2))', color: DS.colors.red },
  };

  const iconStyle = iconColors[variant] || iconColors.blue;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      className={`ds-stat-card ${className}`}
      style={{
        background: DS.colors.bgCard,
        border: `1px solid ${DS.colors.border}`,
        borderRadius: DS.radius.lg,
        padding: DS.space.lg,
        transition: 'all 0.2s ease',
      }}
    >
      <div
        className={`ds-stat-card__icon ds-stat-card__icon--${variant}`}
        style={{
          width: '48px',
          height: '48px',
          borderRadius: DS.radius.md,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: DS.space.md,
          background: iconStyle.bg,
        }}
      >
        {Icon && <Icon style={{ width: '24px', height: '24px', color: iconStyle.color }} />}
      </div>
      <div className="ds-stat-card__label" style={{
        color: DS.colors.textSecondary,
        fontSize: '14px',
        marginBottom: DS.space.xs,
      }}>
        {label}
      </div>
      <div className="ds-stat-card__value" style={{
        color: DS.colors.textPrimary,
        fontSize: '28px',
        fontWeight: 700,
      }}>
        {value}
      </div>
    </motion.div>
  );
};

// ============================================
// EXPORTS ADICIONAIS (re-export dos existentes)
// ============================================
export { default as Button } from './Button';
export { default as Badge } from './Badge';
export { default as Card, CardHeader, CardContent } from './Card';
export { default as Input } from './Input';
export { default as Select } from './Select';
export { default as Modal } from './Modal';
export { default as Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from './Table';
export { default as LoadingSpinner, FullPageLoader } from './LoadingSpinner';
export { default as Icon3DButton } from './Icon3DButton';

// Export default com todos os componentes do DS
export default {
  FormSection,
  FormGrid,
  FormField,
  FormInput,
  FormSelect,
  FormTextarea,
  FormSearch,
  FormTable,
  FormTotals,
  FormFooter,
  FormButton,
  StatusIndicator,
  StatCard,
};
