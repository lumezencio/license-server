import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, Shield, LogIn } from 'lucide-react';
import AppBackground from '../components/AppBackground';
import { Button, Input } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao fazer login');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppBackground>
      <div className="min-h-screen flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          {/* Logo */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', bounce: 0.5 }}
              className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-2xl shadow-blue-500/30"
            >
              <Shield className="w-10 h-10 text-white" />
            </motion.div>
            <h1 className="mt-6 text-3xl font-bold text-white">License Server</h1>
            <p className="mt-2 text-white/60">Painel Administrativo</p>
          </div>

          {/* Form Card */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-white/10 backdrop-blur-xl border border-white/20 rounded-2xl p-8 shadow-2xl"
          >
            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="p-4 bg-red-500/20 border border-red-400/30 rounded-xl text-red-200 text-sm"
                >
                  {error}
                </motion.div>
              )}

              <Input
                label="Email"
                type="email"
                icon={Mail}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
                required
              />

              <Input
                label="Senha"
                type="password"
                icon={Lock}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />

              <Button
                type="submit"
                variant="primary"
                size="lg"
                icon={LogIn}
                loading={loading}
                className="w-full"
              >
                Entrar
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-white/40 text-sm">
                Credenciais padrão: admin@license-server.com / admin123
              </p>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </AppBackground>
  );
}
