import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Users, Key, CheckCircle, XCircle, Clock, AlertTriangle,
  TrendingUp, Calendar, Activity, Shield
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import Card, { CardContent, CardHeader } from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { statsService, licensesService, clientsService } from '../services/api';
import { format, parseISO, subDays } from 'date-fns';
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

      // Calcula estatísticas
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

  const statCards = [
    {
      title: 'Total de Clientes',
      value: stats?.totalClients || 0,
      icon: Users,
      color: 'from-blue-500 to-cyan-500',
      shadowColor: 'shadow-blue-500/30',
    },
    {
      title: 'Licenças Ativas',
      value: stats?.activeLicenses || 0,
      icon: CheckCircle,
      color: 'from-green-500 to-emerald-500',
      shadowColor: 'shadow-green-500/30',
    },
    {
      title: 'Expirando em 30 dias',
      value: stats?.expiringSoon || 0,
      icon: AlertTriangle,
      color: 'from-amber-500 to-orange-500',
      shadowColor: 'shadow-amber-500/30',
    },
    {
      title: 'Total de Licenças',
      value: stats?.totalLicenses || 0,
      icon: Key,
      color: 'from-purple-500 to-violet-500',
      shadowColor: 'shadow-purple-500/30',
    },
  ];

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
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="text-white/60 mt-1">Visão geral do sistema de licenças</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((card, index) => (
          <motion.div
            key={card.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card hover={false} className="relative overflow-hidden">
              <CardContent>
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-white/60 text-sm font-medium">{card.title}</p>
                    <p className="text-4xl font-bold text-white mt-2">{card.value}</p>
                  </div>
                  <div className={`p-3 rounded-xl bg-gradient-to-br ${card.color} ${card.shadowColor} shadow-lg`}>
                    <card.icon className="w-6 h-6 text-white" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Status Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Card hover={false}>
            <CardHeader>
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" />
                Distribuição de Status
              </h3>
            </CardHeader>
            <CardContent>
              {stats?.statusDistribution?.length > 0 ? (
                <div className="flex items-center gap-8">
                  <div className="w-48 h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={stats.statusDistribution}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={80}
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
                  <div className="flex-1 space-y-3">
                    {stats.statusDistribution.map((item) => (
                      <div key={item.name} className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: item.color }}
                        />
                        <span className="text-white/70 flex-1">{item.name}</span>
                        <span className="text-white font-semibold">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-white/50">
                  Nenhuma licença cadastrada
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
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <Shield className="w-5 h-5 text-purple-400" />
                Licenças por Plano
              </h3>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
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
                      <div className="flex justify-between text-sm mb-1">
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

      {/* Recent Licenses */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
      >
        <Card hover={false}>
          <CardHeader>
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Key className="w-5 h-5 text-amber-400" />
              Licenças Recentes
            </h3>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-white/5 border-b border-white/10">
                  <tr>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-white/70">Chave</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-white/70">Cliente</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-white/70">Plano</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-white/70">Status</th>
                    <th className="px-6 py-3 text-left text-sm font-semibold text-white/70">Expira em</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {licenses.slice(0, 5).map((license) => {
                    const client = clients.find(c => c.id === license.client_id);
                    const expiresAt = license.expires_at ? parseISO(license.expires_at) : null;
                    const daysLeft = expiresAt ? Math.ceil((expiresAt - new Date()) / (1000 * 60 * 60 * 24)) : null;

                    return (
                      <tr key={license.id} className="hover:bg-white/5 transition-colors">
                        <td className="px-6 py-4">
                          <code className="text-blue-400 font-mono text-sm">{license.license_key}</code>
                        </td>
                        <td className="px-6 py-4 text-white">
                          {client?.name || '-'}
                        </td>
                        <td className="px-6 py-4">
                          <Badge variant="info" size="sm">
                            {getPlanLabel(license.plan)}
                          </Badge>
                        </td>
                        <td className="px-6 py-4">
                          <Badge variant={getStatusVariant(license.status)} size="sm">
                            {getStatusLabel(license.status)}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 text-white/70">
                          {expiresAt ? (
                            <span className={daysLeft <= 30 ? 'text-amber-400' : ''}>
                              {format(expiresAt, "dd/MM/yyyy", { locale: ptBR })}
                              {daysLeft > 0 && ` (${daysLeft} dias)`}
                            </span>
                          ) : '-'}
                        </td>
                      </tr>
                    );
                  })}
                  {licenses.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-white/50">
                        Nenhuma licença cadastrada
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
