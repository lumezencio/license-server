export function Table({ children, className = '' }) {
  return (
    <div className="overflow-x-auto">
      <table className={`w-full ${className}`}>
        {children}
      </table>
    </div>
  );
}

export function TableHeader({ children }) {
  return (
    <thead className="bg-[var(--ds-cyan)]/5 border-b border-[var(--ds-border)]">
      {children}
    </thead>
  );
}

export function TableBody({ children }) {
  return <tbody className="divide-y divide-[var(--ds-border)]">{children}</tbody>;
}

export function TableRow({ children, className = '', onClick }) {
  return (
    <tr
      onClick={onClick}
      className={`
        hover:bg-[var(--ds-cyan)]/5 transition-colors
        ${onClick ? 'cursor-pointer' : ''}
        ${className}
      `}
    >
      {children}
    </tr>
  );
}

export function TableHead({ children, className = '' }) {
  return (
    <th className={`px-4 py-3 text-left text-[11px] font-semibold text-[var(--ds-cyan)] uppercase tracking-wider ${className}`}>
      {children}
    </th>
  );
}

export function TableCell({ children, className = '' }) {
  return (
    <td className={`px-4 py-3 text-sm text-[var(--ds-text-primary)] ${className}`}>
      {children}
    </td>
  );
}
