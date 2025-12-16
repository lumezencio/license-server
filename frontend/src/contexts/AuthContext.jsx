import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authService } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authChecked, setAuthChecked] = useState(false);

  // Verifica autenticação apenas uma vez na montagem
  useEffect(() => {
    if (authChecked) return;

    const checkAuth = async () => {
      const token = localStorage.getItem('admin_token');

      if (!token) {
        setLoading(false);
        setAuthChecked(true);
        return;
      }

      try {
        const userData = await authService.me();
        setUser(userData);
      } catch (error) {
        console.error('Auth check failed:', error);
        localStorage.removeItem('admin_token');
        setUser(null);
      } finally {
        setLoading(false);
        setAuthChecked(true);
      }
    };

    checkAuth();
  }, [authChecked]);

  const login = useCallback(async (email, password) => {
    const data = await authService.login(email, password);
    localStorage.setItem('admin_token', data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('admin_token');
    setUser(null);
  }, []);

  const value = {
    user,
    loading,
    login,
    logout,
    isAuthenticated: !!user
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
