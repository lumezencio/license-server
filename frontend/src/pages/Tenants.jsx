import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Building2, Search, Eye, RefreshCw, CheckCircle, XCircle,
  Clock, Database, Package, BookOpen, Briefcase, Filter,
  MessageCircle, Home
} from 'lucide-react';
import {
  Card, CardContent, Badge, LoadingSpinner, Button, Input
} from '../components/ui';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/Table';
import { Icon3DButton } from '../components/ui';
import { Modal } from '../components/ui';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import api from '../services/api';

export default function Tenants() {
  const [loading, setLoading] = useState(true);
  const [tenants, setTenants] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [productFilter, setProductFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [viewingTenant, setViewingTenant] = useState(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);

  useEffect(() => {
    loadTenants();
  }, []);

  const loadTenants = async () => {
    setLoading(true);
    try {
      const response = await api.get('/auth/admin/tenants');
      setTenants(response.data);
    } catch (error) {
      console.error('Erro ao carregar tenants:', error);
    } finally {
      setLoading(false);
    }
  };

  // Estatisticas por produto
  const stats = {
    total: tenants.length,
    enterprise: tenants.filter(t => t.product_code === 'enterprise').length,
    diario: tenants.filter(t => t.product_code === 'diario').length,
    botwhatsapp: tenants.filter(t => t.product_code === 'botwhatsapp').length,
    condotech: tenants.filter(t => t.product_code === 'condotech').length,
    active: tenants.filter(t => t.status === 'active').length,
    trial: tenants.filter(t => t.status === 'trial').length,
  };

  const filteredTenants = tenants.filter(tenant => {
    const matchesSearch =
      tenant.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tenant.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tenant.tenant_code?.includes(searchTerm);

    const matchesProduct =
      productFilter === 'all' || tenant.product_code === productFilter;

    const matchesStatus =
      statusFilter === 'all' || tenant.status === statusFilter;

    return matchesSearch && matchesProduct && matchesStatus;
  });

  const getProductInfo = (productCode) => {
    const products = {
      enterprise: {
        name: 'Enterprise System',
        icon: Briefcase,
        color: 'blue',
        bgColor: 'bg-blue-500/20',
        textColor: 'text-blue-400',
        badgeVariant: 'info'
      },
      diario: {
        name: 'Diario Pessoal',
        icon: BookOpen,
        color: 'purple',
        bgColor: 'bg-purple-500/20',
        textColor: 'text-purple-400',
        badgeVariant: 'purple'
      },
      botwhatsapp: {
        name: 'WhatsApp Bot',
        icon: MessageCircle,
        color: 'green',
        bgColor: 'bg-green-500/20',
        textColor: 'text-green-400',
        badgeVariant: 'success'
      },
      condotech: {
        name: 'CondoTech',
        icon: Home,
        color: 'orange',
        bgColor: 'bg-orange-500/20',
        textColor: 'text-orange-400',
        badgeVariant: 'warning'
      }
    };
    return products[productCode] || {
      name: productCode || 'Desconhecido',
      icon: Package,
      color: 'gray',
      bgColor: 'bg-gray-500/20',
      textColor: 'text-gray-400',
      badgeVariant: 'default'
    };
  };

  const getStatusVariant = (status) => {
    const variants = {
      active: 'success',
      trial: 'warning',
      suspended: 'danger',
      pending: 'default'
    };
    return variants[status] || 'default';
  };

  const openViewModal = (tenant) => {
    setViewingTenant(tenant);
    setIsViewModalOpen(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <LoadingSpinner size="xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Tenants</h1>
          <p className="text-white/60 mt-1 text-sm sm:text-base">
            Gerenciamento de tenants por produto
          </p>
        </div>
        <Button icon={RefreshCw} variant="secondary" onClick={loadTenants}>
          Atualizar
        </Button>
      </div>

      {/* Stats por Produto */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <Card hover={false} className="cursor-pointer" onClick={() => { setProductFilter('all'); setStatusFilter('all'); }}>
          <CardContent className="py-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Building2 className="w-5 h-5 text-cyan-400" />
            </div>
            <p className="text-2xl sm:text-3xl font-bold text-white">{stats.total}</p>
            <p className="text-white/50 text-xs sm:text-sm">Total</p>
          </CardContent>
        </Card>

        <Card hover={false} className="cursor-pointer border-blue-500/30" onClick={() => { setProductFilter('enterprise'); setStatusFilter('all'); }}>
          <CardContent className="py-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Briefcase className="w-5 h-5 text-blue-400" />
            </div>
            <p className="text-2xl sm:text-3xl font-bold text-blue-400">{stats.enterprise}</p>
            <p className="text-white/50 text-xs sm:text-sm">Enterprise</p>
          </CardContent>
        </Card>

        <Card hover={false} className="cursor-pointer border-green-500/30" onClick={() => { setProductFilter('botwhatsapp'); setStatusFilter('all'); }}>
          <CardContent className="py-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <MessageCircle className="w-5 h-5 text-green-400" />
            </div>
            <p className="text-2xl sm:text-3xl font-bold text-green-400">{stats.botwhatsapp}</p>
            <p className="text-white/50 text-xs sm:text-sm">WhatsApp Bot</p>
          </CardContent>
        </Card>

        <Card hover={false} className="cursor-pointer border-orange-500/30" onClick={() => { setProductFilter('condotech'); setStatusFilter('all'); }}>
          <CardContent className="py-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Home className="w-5 h-5 text-orange-400" />
            </div>
            <p className="text-2xl sm:text-3xl font-bold text-orange-400">{stats.condotech}</p>
            <p className="text-white/50 text-xs sm:text-sm">CondoTech</p>
          </CardContent>
        </Card>

        <Card hover={false} className="cursor-pointer border-purple-500/30" onClick={() => { setProductFilter('diario'); setStatusFilter('all'); }}>
          <CardContent className="py-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <BookOpen className="w-5 h-5 text-purple-400" />
            </div>
            <p className="text-2xl sm:text-3xl font-bold text-purple-400">{stats.diario}</p>
            <p className="text-white/50 text-xs sm:text-sm">Diario</p>
          </CardContent>
        </Card>

        <Card hover={false} className="cursor-pointer" onClick={() => { setProductFilter('all'); setStatusFilter('trial'); }}>
          <CardContent className="py-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <Clock className="w-5 h-5 text-amber-400" />
            </div>
            <p className="text-2xl sm:text-3xl font-bold text-amber-400">{stats.trial}</p>
            <p className="text-white/50 text-xs sm:text-sm">Em Trial</p>
          </CardContent>
        </Card>
      </div>

      {/* Filtros */}
      <Card hover={false}>
        <CardContent className="py-3 sm:py-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Input
                icon={Search}
                placeholder="Buscar por nome, email ou codigo..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant={productFilter === 'all' ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => setProductFilter('all')}
              >
                Todos
              </Button>
              <Button
                variant={productFilter === 'enterprise' ? 'primary' : 'ghost'}
                size="sm"
                icon={Briefcase}
                onClick={() => setProductFilter('enterprise')}
              >
                Enterprise
              </Button>
              <Button
                variant={productFilter === 'botwhatsapp' ? 'primary' : 'ghost'}
                size="sm"
                icon={MessageCircle}
                onClick={() => setProductFilter('botwhatsapp')}
              >
                WhatsApp
              </Button>
              <Button
                variant={productFilter === 'condotech' ? 'primary' : 'ghost'}
                size="sm"
                icon={Home}
                onClick={() => setProductFilter('condotech')}
              >
                CondoTech
              </Button>
              <Button
                variant={productFilter === 'diario' ? 'primary' : 'ghost'}
                size="sm"
                icon={BookOpen}
                onClick={() => setProductFilter('diario')}
              >
                Diario
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabela */}
      <Card hover={false}>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead className="hidden sm:table-cell">Codigo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden md:table-cell">Database</TableHead>
                  <TableHead className="hidden lg:table-cell">Criado em</TableHead>
                  <TableHead className="text-right">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTenants.map((tenant) => {
                  const product = getProductInfo(tenant.product_code);
                  const ProductIcon = product.icon;

                  return (
                    <TableRow key={tenant.id}>
                      <TableCell>
                        <div className="flex items-center gap-2 sm:gap-3">
                          <div className={`w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl flex items-center justify-center flex-shrink-0 ${product.bgColor}`}>
                            <ProductIcon className={`w-4 h-4 sm:w-5 sm:h-5 ${product.textColor}`} />
                          </div>
                          <div className="min-w-0">
                            <p className="font-semibold text-white text-sm sm:text-base truncate">
                              {tenant.name}
                            </p>
                            <p className="text-xs sm:text-sm text-white/50 truncate">
                              {tenant.email}
                            </p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={product.badgeVariant || 'default'}
                          size="sm"
                        >
                          {product.name}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <span className="font-mono text-white/70 text-xs sm:text-sm">
                          {tenant.tenant_code}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={getStatusVariant(tenant.status)} size="sm">
                          {tenant.status === 'trial' ? 'Trial' : tenant.status === 'active' ? 'Ativo' : tenant.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden md:table-cell">
                        <div className="flex items-center gap-2">
                          <Database className="w-4 h-4 text-white/40" />
                          <span className="text-white/70 text-xs font-mono truncate max-w-[150px]">
                            {tenant.database_name || '-'}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">
                        <span className="text-white/70 text-sm">
                          {tenant.registered_at
                            ? format(parseISO(tenant.registered_at), "dd/MM/yyyy", { locale: ptBR })
                            : '-'
                          }
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1 sm:gap-2">
                          <Icon3DButton
                            icon={Eye}
                            variant="cyan"
                            size="iconOnly"
                            onClick={() => openViewModal(tenant)}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filteredTenants.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8 text-white/50">
                      {searchTerm || productFilter !== 'all'
                        ? 'Nenhum tenant encontrado com os filtros aplicados'
                        : 'Nenhum tenant cadastrado'
                      }
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Modal de Detalhes */}
      <Modal
        isOpen={isViewModalOpen}
        onClose={() => setIsViewModalOpen(false)}
        title="Detalhes do Tenant"
        size="lg"
        icon={Eye}
      >
        {viewingTenant && (
          <div className="space-y-4 sm:space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row items-center gap-3 sm:gap-4 text-center sm:text-left">
              {(() => {
                const product = getProductInfo(viewingTenant.product_code);
                const ProductIcon = product.icon;
                return (
                  <div className={`w-14 h-14 sm:w-16 sm:h-16 rounded-xl sm:rounded-2xl flex items-center justify-center flex-shrink-0 ${product.bgColor}`}>
                    <ProductIcon className={`w-7 h-7 sm:w-8 sm:h-8 ${product.textColor}`} />
                  </div>
                );
              })()}
              <div className="min-w-0 flex-1">
                <h3 className="text-xl sm:text-2xl font-bold text-white truncate">
                  {viewingTenant.name}
                </h3>
                <p className="text-white/60 text-sm sm:text-base truncate">
                  {viewingTenant.email}
                </p>
                <div className="flex items-center justify-center sm:justify-start gap-2 mt-2">
                  <Badge
                    variant={getProductInfo(viewingTenant.product_code).badgeVariant || 'default'}
                    size="sm"
                  >
                    {getProductInfo(viewingTenant.product_code).name}
                  </Badge>
                  <Badge variant={getStatusVariant(viewingTenant.status)} size="sm">
                    {viewingTenant.status === 'trial' ? 'Trial' : viewingTenant.status === 'active' ? 'Ativo' : viewingTenant.status}
                  </Badge>
                </div>
              </div>
            </div>

            {/* Grid de informacoes */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Codigo do Tenant</p>
                <p className="text-white font-mono mt-1 text-sm sm:text-base">
                  {viewingTenant.tenant_code}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Documento</p>
                <p className="text-white font-mono mt-1 text-sm sm:text-base">
                  {viewingTenant.document || '-'}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Telefone</p>
                <p className="text-white mt-1 text-sm sm:text-base">
                  {viewingTenant.phone || '-'}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Database</p>
                <p className="text-white font-mono mt-1 text-sm sm:text-base truncate">
                  {viewingTenant.database_name || '-'}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Registrado em</p>
                <p className="text-white mt-1 text-sm sm:text-base">
                  {viewingTenant.registered_at
                    ? format(parseISO(viewingTenant.registered_at), "dd/MM/yyyy HH:mm", { locale: ptBR })
                    : '-'
                  }
                </p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Provisionado em</p>
                <p className="text-white mt-1 text-sm sm:text-base">
                  {viewingTenant.provisioned_at
                    ? format(parseISO(viewingTenant.provisioned_at), "dd/MM/yyyy HH:mm", { locale: ptBR })
                    : '-'
                  }
                </p>
              </div>
            </div>

            {/* Trial info */}
            {viewingTenant.is_trial && (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <div className="flex items-center gap-3">
                  <Clock className="w-5 h-5 text-amber-400" />
                  <div>
                    <p className="text-white font-semibold">Periodo de Trial</p>
                    <p className="text-white/70 text-sm">
                      {viewingTenant.trial_days} dias - Expira em{' '}
                      {viewingTenant.trial_expires_at
                        ? format(parseISO(viewingTenant.trial_expires_at), "dd/MM/yyyy", { locale: ptBR })
                        : '-'
                      }
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
