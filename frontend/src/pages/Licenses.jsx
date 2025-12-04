import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Key, Plus, Search, Edit2, Copy, Ban, Play, Pause, Eye,
  Calendar, Users, Building2, CheckCircle, XCircle, Clock,
  AlertTriangle, RefreshCw
} from 'lucide-react';
import Card, { CardContent, CardHeader } from '../components/ui/Card';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Select from '../components/ui/Select';
import Badge from '../components/ui/Badge';
import Modal from '../components/ui/Modal';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/Table';
import { licensesService, clientsService } from '../services/api';
import { format, parseISO, addDays, addMonths, addYears } from 'date-fns';
import { ptBR } from 'date-fns/locale';

const PLAN_OPTIONS = [
  { value: 'starter', label: 'Starter (3 usuários)' },
  { value: 'professional', label: 'Professional (10 usuários)' },
  { value: 'enterprise', label: 'Enterprise (50 usuários)' },
  { value: 'unlimited', label: 'Unlimited (Ilimitado)' },
];

const DURATION_OPTIONS = [
  { value: '30', label: '30 dias' },
  { value: '90', label: '90 dias' },
  { value: '180', label: '6 meses' },
  { value: '365', label: '1 ano' },
  { value: '730', label: '2 anos' },
  { value: '1095', label: '3 anos' },
];

export default function Licenses() {
  const [loading, setLoading] = useState(true);
  const [licenses, setLicenses] = useState([]);
  const [clients, setClients] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [viewingLicense, setViewingLicense] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    client_id: '',
    plan: 'professional',
    duration_days: '365',
    notes: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [licensesData, clientsData] = await Promise.all([
        licensesService.list(),
        clientsService.list(),
      ]);
      setLicenses(licensesData);
      setClients(clientsData);
    } catch (error) {
      console.error('Erro ao carregar licenças:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredLicenses = licenses.filter(license => {
    const matchesSearch =
      license.license_key?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      clients.find(c => c.id === license.client_id)?.name?.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesStatus = statusFilter === 'all' || license.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const getClient = (clientId) => clients.find(c => c.id === clientId);

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

  const getPlanInfo = (plan) => {
    const plans = {
      starter: { label: 'Starter', users: 3, color: 'info' },
      professional: { label: 'Professional', users: 10, color: 'purple' },
      enterprise: { label: 'Enterprise', users: 50, color: 'warning' },
      unlimited: { label: 'Unlimited', users: '∞', color: 'success' },
    };
    return plans[plan] || { label: plan, users: '-', color: 'default' };
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    alert('Chave copiada!');
  };

  const openNewModal = () => {
    setFormData({
      client_id: clients[0]?.id || '',
      plan: 'professional',
      duration_days: '365',
      notes: '',
    });
    setIsModalOpen(true);
  };

  const openViewModal = async (license) => {
    setViewingLicense(license);
    setIsViewModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      await licensesService.create({
        client_id: formData.client_id,
        plan: formData.plan,
        duration_days: parseInt(formData.duration_days),
        notes: formData.notes,
      });
      setIsModalOpen(false);
      loadData();
    } catch (error) {
      console.error('Erro ao criar licença:', error);
      alert(error.response?.data?.detail || 'Erro ao criar licença');
    } finally {
      setSaving(false);
    }
  };

  const handleRevoke = async (license) => {
    if (!confirm('Deseja REVOGAR esta licença? Esta ação não pode ser desfeita.')) return;

    try {
      await licensesService.revoke(license.id);
      loadData();
    } catch (error) {
      console.error('Erro ao revogar licença:', error);
      alert(error.response?.data?.detail || 'Erro ao revogar licença');
    }
  };

  const handleSuspend = async (license) => {
    if (!confirm('Deseja suspender esta licença?')) return;

    try {
      await licensesService.suspend(license.id);
      loadData();
    } catch (error) {
      console.error('Erro ao suspender licença:', error);
      alert(error.response?.data?.detail || 'Erro ao suspender licença');
    }
  };

  const handleReactivate = async (license) => {
    if (!confirm('Deseja reativar esta licença?')) return;

    try {
      await licensesService.reactivate(license.id);
      loadData();
    } catch (error) {
      console.error('Erro ao reativar licença:', error);
      alert(error.response?.data?.detail || 'Erro ao reativar licença');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <LoadingSpinner size="xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Licenças</h1>
          <p className="text-white/60 mt-1">Gerencie as licenças do sistema</p>
        </div>
        <Button icon={Plus} onClick={openNewModal} disabled={clients.length === 0}>
          Nova Licença
        </Button>
      </div>

      {/* Filters */}
      <Card hover={false}>
        <CardContent className="py-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <Input
                icon={Search}
                placeholder="Buscar por chave ou cliente..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: 'all', label: 'Todos os status' },
                { value: 'active', label: 'Ativas' },
                { value: 'pending', label: 'Pendentes' },
                { value: 'expired', label: 'Expiradas' },
                { value: 'suspended', label: 'Suspensas' },
                { value: 'revoked', label: 'Revogadas' },
              ]}
              className="w-48"
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card hover={false}>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Chave da Licença</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Plano</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Expiração</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredLicenses.map((license) => {
                const client = getClient(license.client_id);
                const planInfo = getPlanInfo(license.plan);
                const expiresAt = license.expires_at ? parseISO(license.expires_at) : null;
                const daysLeft = expiresAt ? Math.ceil((expiresAt - new Date()) / (1000 * 60 * 60 * 24)) : null;
                const isExpiringSoon = daysLeft !== null && daysLeft > 0 && daysLeft <= 30;

                return (
                  <TableRow key={license.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <code className="text-blue-400 font-mono text-sm">{license.license_key}</code>
                        <button
                          onClick={() => copyToClipboard(license.license_key)}
                          className="p-1 hover:bg-white/10 rounded transition-colors"
                          title="Copiar chave"
                        >
                          <Copy className="w-4 h-4 text-white/50" />
                        </button>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-white/50" />
                        <span className="text-white">{client?.name || '-'}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={planInfo.color} size="sm">
                        {planInfo.label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(license.status)} size="sm">
                        {getStatusLabel(license.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {expiresAt ? (
                        <div className={isExpiringSoon ? 'text-amber-400' : 'text-white/70'}>
                          <div className="flex items-center gap-1">
                            {isExpiringSoon && <AlertTriangle className="w-4 h-4" />}
                            {format(expiresAt, "dd/MM/yyyy")}
                          </div>
                          {daysLeft !== null && daysLeft > 0 && (
                            <span className="text-xs text-white/50">
                              {daysLeft} dia{daysLeft !== 1 ? 's' : ''} restante{daysLeft !== 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                      ) : '-'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Eye}
                          onClick={() => openViewModal(license)}
                          title="Ver detalhes"
                        />
                        {license.status === 'active' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={Pause}
                            onClick={() => handleSuspend(license)}
                            title="Suspender"
                            className="hover:text-amber-400"
                          />
                        )}
                        {license.status === 'suspended' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={Play}
                            onClick={() => handleReactivate(license)}
                            title="Reativar"
                            className="hover:text-green-400"
                          />
                        )}
                        {license.status !== 'revoked' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={Ban}
                            onClick={() => handleRevoke(license)}
                            title="Revogar"
                            className="hover:text-red-400"
                          />
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {filteredLicenses.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-white/50">
                    {searchTerm || statusFilter !== 'all'
                      ? 'Nenhuma licença encontrada'
                      : 'Nenhuma licença cadastrada'
                    }
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Nova Licença"
        size="md"
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          <Select
            label="Cliente *"
            icon={Building2}
            value={formData.client_id}
            onChange={(e) => setFormData({ ...formData, client_id: e.target.value })}
            options={clients.map(c => ({ value: c.id, label: c.name }))}
            required
          />

          <Select
            label="Plano *"
            icon={Key}
            value={formData.plan}
            onChange={(e) => setFormData({ ...formData, plan: e.target.value })}
            options={PLAN_OPTIONS}
            required
          />

          <Select
            label="Duração *"
            icon={Calendar}
            value={formData.duration_days}
            onChange={(e) => setFormData({ ...formData, duration_days: e.target.value })}
            options={DURATION_OPTIONS}
            required
          />

          <div>
            <label className="block text-sm font-semibold text-white mb-2">Observações</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              rows={3}
              className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-xl text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="Anotações internas sobre esta licença..."
            />
          </div>

          <div className="bg-blue-500/10 border border-blue-400/30 rounded-xl p-4">
            <h4 className="text-blue-300 font-semibold mb-2">Resumo da Licença</h4>
            <div className="text-sm text-white/70 space-y-1">
              <p>Cliente: {clients.find(c => c.id === formData.client_id)?.name || '-'}</p>
              <p>Plano: {PLAN_OPTIONS.find(p => p.value === formData.plan)?.label}</p>
              <p>Válida até: {format(addDays(new Date(), parseInt(formData.duration_days)), "dd/MM/yyyy")}</p>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-white/10">
            <Button variant="ghost" type="button" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={saving} icon={Key}>
              Gerar Licença
            </Button>
          </div>
        </form>
      </Modal>

      {/* View Modal */}
      <Modal
        isOpen={isViewModalOpen}
        onClose={() => setIsViewModalOpen(false)}
        title="Detalhes da Licença"
        size="lg"
      >
        {viewingLicense && (
          <div className="space-y-6">
            {/* License Key */}
            <div className="bg-gradient-to-r from-blue-500/20 to-purple-500/20 border border-blue-400/30 rounded-2xl p-6 text-center">
              <p className="text-white/50 text-sm mb-2">Chave da Licença</p>
              <div className="flex items-center justify-center gap-3">
                <code className="text-3xl font-mono text-blue-300 tracking-wider">
                  {viewingLicense.license_key}
                </code>
                <button
                  onClick={() => copyToClipboard(viewingLicense.license_key)}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                >
                  <Copy className="w-5 h-5 text-white/50" />
                </button>
              </div>
            </div>

            {/* Status & Plan */}
            <div className="flex items-center justify-center gap-4">
              <Badge variant={getStatusVariant(viewingLicense.status)} size="lg">
                {getStatusLabel(viewingLicense.status)}
              </Badge>
              <Badge variant={getPlanInfo(viewingLicense.plan).color} size="lg">
                {getPlanInfo(viewingLicense.plan).label}
              </Badge>
            </div>

            {/* Info Grid */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm flex items-center gap-2">
                  <Building2 className="w-4 h-4" /> Cliente
                </p>
                <p className="text-white font-medium mt-1">
                  {getClient(viewingLicense.client_id)?.name || '-'}
                </p>
              </div>

              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm flex items-center gap-2">
                  <Users className="w-4 h-4" /> Máx. Usuários
                </p>
                <p className="text-white font-medium mt-1">{viewingLicense.max_users}</p>
              </div>

              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm flex items-center gap-2">
                  <Calendar className="w-4 h-4" /> Emitida em
                </p>
                <p className="text-white font-medium mt-1">
                  {viewingLicense.issued_at
                    ? format(parseISO(viewingLicense.issued_at), "dd/MM/yyyy HH:mm")
                    : '-'
                  }
                </p>
              </div>

              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm flex items-center gap-2">
                  <Clock className="w-4 h-4" /> Expira em
                </p>
                <p className="text-white font-medium mt-1">
                  {viewingLicense.expires_at
                    ? format(parseISO(viewingLicense.expires_at), "dd/MM/yyyy HH:mm")
                    : '-'
                  }
                </p>
              </div>

              {viewingLicense.activated_at && (
                <div className="bg-white/5 rounded-xl p-4">
                  <p className="text-white/50 text-sm flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" /> Ativada em
                  </p>
                  <p className="text-white font-medium mt-1">
                    {format(parseISO(viewingLicense.activated_at), "dd/MM/yyyy HH:mm")}
                  </p>
                </div>
              )}

              {viewingLicense.hardware_id && (
                <div className="bg-white/5 rounded-xl p-4">
                  <p className="text-white/50 text-sm">Hardware ID</p>
                  <code className="text-blue-300 font-mono text-xs mt-1 block truncate">
                    {viewingLicense.hardware_id}
                  </code>
                </div>
              )}
            </div>

            {/* Limits */}
            <div className="bg-white/5 rounded-xl p-4">
              <h4 className="text-white font-semibold mb-3">Limites</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold text-white">{viewingLicense.max_users}</p>
                  <p className="text-white/50 text-sm">Usuários</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-white">{viewingLicense.max_customers?.toLocaleString()}</p>
                  <p className="text-white/50 text-sm">Clientes</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-white">{viewingLicense.max_products?.toLocaleString()}</p>
                  <p className="text-white/50 text-sm">Produtos</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-white">{viewingLicense.max_monthly_transactions?.toLocaleString()}</p>
                  <p className="text-white/50 text-sm">Trans./mês</p>
                </div>
              </div>
            </div>

            {/* Features */}
            {viewingLicense.features?.length > 0 && (
              <div className="bg-white/5 rounded-xl p-4">
                <h4 className="text-white font-semibold mb-3">Recursos</h4>
                <div className="flex flex-wrap gap-2">
                  {viewingLicense.features.map((feature) => (
                    <Badge key={feature} variant="info" size="sm">
                      {feature}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Notes */}
            {viewingLicense.notes && (
              <div className="bg-white/5 rounded-xl p-4">
                <h4 className="text-white font-semibold mb-2">Observações</h4>
                <p className="text-white/70">{viewingLicense.notes}</p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
