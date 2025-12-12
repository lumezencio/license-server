import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Users, Key, CheckCircle, XCircle, Clock, AlertTriangle,
  TrendingUp, Calendar, Activity, Shield
} from 'lucide-react';
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip
} from 'recharts';
import { Card, CardContent, CardHeader, Badge, LoadingSpinner, StatCard } from '../components/ui';
import { statsService, licensesService, clientsService } from '../services/api';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';

const COLORS = ['#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#6b7280'];

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [licenses, setLicenses] = useState([]);
  const [clients, setClients] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [licensesData, clientsData] = await Promise.all([
        licensesService.list(0, 100),
        clientsService.list(0, 100),
      ]);

      setLicenses(licensesData);
      setClients(clientsData);

      // Calcula estatisticas
      const now = new Date();
      const activeCount = licensesData.filter(l => l.status === 'active').length;
      const expiredCount = licensesData.filter(l => l.status === 'expired').length;
      const pendingCount = licensesData.filter(l => l.status === 'pending').length;
      const revokedCount = licensesData.filter(l => l.status === 'revoked').length;
      const suspendedCount = licensesData.filter(l => l.status === 'suspended').length;

      const expiringSoon = licensesData.filter(l => {
        if (!l.expires_at || l.status !== 'active') return false;
        const expires = parseISO(l.expires_at);
        const daysLeft = Math.ceil((expires - now) / (1000 * 60 * 60 * 24));
        return daysLeft > 0 && daysLeft <= 30;
      }).length;

      setStats({
        totalClients: clientsData.length,
        totalLicenses: licensesData.length,
        activeLicenses: activeCount,
        expiredLicenses: expiredCount,
        pendingLicenses: pendingCount,
        revokedLicenses: revokedCount,
        suspendedLicenses: suspendedCount,
        expiringSoon,
        statusDistribution: [
          { name: 'Ativas', value: activeCount, color: '#22c55e' },
          { name: 'Pendentes', value: pendingCount, color: '#f59e0b' },
          { name: 'Expiradas', value: expiredCount, color: '#ef4444' },
          { name: 'Suspensas', value: suspendedCount, color: '#8b5cf6' },
          { name: 'Revogadas', value: revokedCount, color: '#6b7280' },
        ].filter(s => s.value > 0),
      });
    } catch (error) {
      console.error('Erro ao carregar dados:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <LoadingSpinner size="xl" />
      </div>
    );
  }

  const getStatusVariant = (status) => {
    const variants = {
      active: 'success',
      pending: 'warning',
      expired: 'danger',
      suspended: 'purple',
      revoked: 'default',
    };
    return variants[status] || 'default';
  };

  const getStatusLabel = (status) => {
    const labels = {
      active: 'Ativa',
      pending: 'Pendente',
      expired: 'Expirada',
      suspended: 'Suspensa',
      revoked: 'Revogada',
    };
    return labels[status] || status;
  };

  const getPlanLabel = (plan) => {
    const labels = {
      starter: 'Starter',
      professional: 'Professional',
      enterprise: 'Enterprise',
      unlimited: 'Unlimited',
    };
    return labels[plan] || plan;
  };

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Dashboard</h1>
        <p className="text-white/60 mt-1 text-sm sm:text-base">Visao geral do sistema de licencas</p>
      </div>

      {/* Stats Cards - Responsivo */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6">
        <StatCard
          icon={Users}
          label="Total de Clientes"
          value={stats?.totalClients || 0}
          variant="blue"
        />
        <StatCard
          icon={CheckCircle}
          label="Licencas Ativas"
          value={stats?.activeLicenses || 0}
          variant="green"
        />
        <StatCard
          icon={AlertTriangle}
          label="Expirando em 30 dias"
          value={stats?.expiringSoon || 0}
          variant="yellow"
        />
        <StatCard
          icon={Key}
          label="Total de Licencas"
          value={stats?.totalLicenses || 0}
          variant="purple"
        />
      </div>

      {/* Charts Row - Responsivo */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        {/* Status Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Card hover={false}>
            <CardHeader>
              <h3 className="text-base sm:text-lg font-semibold text-white flex items-center gap-2">
                <Activity className="w-4 h-4 sm:w-5 sm:h-5 text-blue-400" />
                Distribuicao de Status
              </h3>
            </CardHeader>
            <CardContent>
              {stats?.statusDistribution?.length > 0 ? (
                <div className="flex flex-col sm:flex-row items-center gap-4 sm:gap-8">
                  <div className="w-36 h-36 sm:w-48 sm:h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={stats.statusDistribution}
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={60}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {stats.statusDistribution.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1e293b',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: '8px',
                            color: '#fff'
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex-1 space-y-2 sm:space-y-3 w-full">
                    {stats.statusDistribution.map((item) => (
                      <div key={item.name} className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="text-white/70 flex-1 text-sm sm:text-base">{item.name}</span>
                        <span className="text-white font-semibold">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-white/50">
                  Nenhuma licenca cadastrada
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* License by Plan */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <Card hover={false}>
            <CardHeader>
              <h3 className="text-base sm:text-lg font-semibold text-white flex items-center gap-2">
                <Shield className="w-4 h-4 sm:w-5 sm:h-5 text-purple-400" />
                Licencas por Plano
              </h3>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 sm:space-y-4">
                {['starter', 'professional', 'enterprise', 'unlimited'].map((plan) => {
                  const count = licenses.filter(l => l.plan === plan).length;
                  const percentage = licenses.length > 0 ? (count / licenses.length) * 100 : 0;
                  const colors = {
                    starter: 'bg-blue-500',
                    professional: 'bg-purple-500',
                    enterprise: 'bg-amber-500',
                    unlimited: 'bg-emerald-500',
                  };

                  return (
                    <div key={plan}>
                      <div className="flex justify-between text-xs sm:text-sm mb-1">
                        <span className="text-white/70 capitalize">{getPlanLabel(plan)}</span>
                        <span className="text-white font-medium">{count}</span>
                      </div>
                      <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${percentage}%` }}
                          transition={{ duration: 1, delay: 0.5 }}
                          className={`h-full ${colors[plan]} rounded-full`}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Recent Licenses - Responsivo */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
      >
        <Card hover={false}>
          <CardHeader>
            <h3 className="text-base sm:text-lg font-semibold text-white flex items-center gap-2">
              <Key className="w-4 h-4 sm:w-5 sm:h-5 text-amber-400" />
              Licencas Recentes
            </h3>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[600px]">
                <thead className="bg-white/5 border-b border-white/10">
                  <tr>
                    <th className="px-3 sm:px-6 py-3 text-left text-xs sm:text-sm font-semibold text-white/70">Chave</th>
                    <th className="px-3 sm:px-6 py-3 text-left text-xs sm:text-sm font-semibold text-white/70">Cliente</th>
                    <th className="px-3 sm:px-6 py-3 text-left text-xs sm:text-sm font-semibold text-white/70">Plano</th>
                    <th className="px-3 sm:px-6 py-3 text-left text-xs sm:text-sm font-semibold text-white/70">Status</th>
                    <th className="px-3 sm:px-6 py-3 text-left text-xs sm:text-sm font-semibold text-white/70">Expira em</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {licenses.slice(0, 5).map((license) => {
                    const client = clients.find(c => c.id === license.client_id);
                    const expiresAt = license.expires_at ? parseISO(license.expires_at) : null;
                    const daysLeft = expiresAt ? Math.ceil((expiresAt - new Date()) / (1000 * 60 * 60 * 24)) : null;

                    return (
                      <tr key={license.id} className="hover:bg-white/5 transition-colors">
                        <td className="px-3 sm:px-6 py-3 sm:py-4">
                          <code className="text-blue-400 font-mono text-xs sm:text-sm">{license.license_key}</code>
                        </td>
                        <td className="px-3 sm:px-6 py-3 sm:py-4 text-white text-xs sm:text-sm">
                          {client?.name || '-'}
                        </td>
                        <td className="px-3 sm:px-6 py-3 sm:py-4">
                          <Badge variant="info" size="sm">
                            {getPlanLabel(license.plan)}
                          </Badge>
                        </td>
                        <td className="px-3 sm:px-6 py-3 sm:py-4">
                          <Badge variant={getStatusVariant(license.status)} size="sm">
                            {getStatusLabel(license.status)}
                          </Badge>
                        </td>
                        <td className="px-3 sm:px-6 py-3 sm:py-4 text-white/70 text-xs sm:text-sm">
                          {expiresAt ? (
                            <span className={daysLeft <= 30 ? 'text-amber-400' : ''}>
                              {format(expiresAt, "dd/MM/yyyy", { locale: ptBR })}
                              {daysLeft > 0 && ` (${daysLeft}d)`}
                            </span>
                          ) : '-'}
                        </td>
                      </tr>
                    );
                  })}
                  {licenses.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-white/50">
                        Nenhuma licenca cadastrada
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
