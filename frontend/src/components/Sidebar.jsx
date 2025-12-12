import { NavLink, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Users,
  Key,
  History,
  Settings,
  LogOut,
  Shield,
  ChevronRight
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

const menuItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { path: '/clients', icon: Users, label: 'Clientes' },
  { path: '/licenses', icon: Key, label: 'Licenças' },
  { path: '/validations', icon: History, label: 'Validações' },
  { path: '/settings', icon: Settings, label: 'Configurações' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <motion.aside
      initial={{ x: -100, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className="w-72 h-screen bg-[var(--ds-bg-card)]/80 backdrop-blur-xl border-r border-[var(--ds-border)] flex flex-col"
    >
      {/* Logo */}
      <div className="p-6 border-b border-[var(--ds-border)]">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[var(--ds-cyan)] to-[var(--ds-blue)] flex items-center justify-center shadow-lg shadow-cyan-500/30">
            <Shield className="w-7 h-7 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-[var(--ds-text-primary)]">License Server</h1>
            <p className="text-xs text-[var(--ds-text-muted)]">Admin Panel</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
        {menuItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `
              flex items-center gap-3 px-4 py-3 rounded-lg
              transition-all duration-200 group
              ${isActive
                ? 'bg-[var(--ds-cyan)]/10 border border-[var(--ds-cyan)]/30 text-[var(--ds-text-primary)] shadow-lg'
                : 'text-[var(--ds-text-secondary)] hover:bg-white/5 hover:text-[var(--ds-text-primary)]'
              }
            `}
          >
            {({ isActive }) => (
              <>
                <item.icon className={`w-5 h-5 ${isActive ? 'text-[var(--ds-cyan)]' : 'text-[var(--ds-text-muted)] group-hover:text-[var(--ds-text-secondary)]'}`} />
                <span className="font-medium">{item.label}</span>
                {isActive && (
                  <ChevronRight className="w-4 h-4 ml-auto text-[var(--ds-cyan)]" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User info */}
      <div className="p-4 border-t border-[var(--ds-border)]">
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white/5">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[var(--ds-cyan)] to-[var(--ds-blue)] flex items-center justify-center">
            <span className="text-white font-bold text-sm">
              {user?.full_name?.charAt(0) || 'A'}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[var(--ds-text-primary)] truncate">
              {user?.full_name || 'Admin'}
            </p>
            <p className="text-xs text-[var(--ds-text-muted)] truncate">
              {user?.email}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
            title="Sair"
          >
            <LogOut className="w-5 h-5 text-[var(--ds-text-muted)] hover:text-[var(--ds-red)]" />
          </button>
        </div>
      </div>
    </motion.aside>
  );
}
