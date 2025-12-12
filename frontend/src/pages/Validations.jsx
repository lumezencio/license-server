import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  History, Search, CheckCircle, XCircle, Monitor, Globe,
  Calendar, Filter, RefreshCw
} from 'lucide-react';
import { Card, CardContent, CardHeader, Button, Input, Select, Badge, LoadingSpinner, StatCard } from '../components/ui';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/Table';
import { licensesService, clientsService } from '../services/api';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';

export default function Validations() {
  const [loading, setLoading] = useState(true);
  const [validations, setValidations] = useState([]);
  const [licenses, setLicenses] = useState([]);
  const [clients, setClients] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [successFilter, setSuccessFilter] = useState('all');

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

      // Carrega validações de todas as licenças
      const allValidations = [];
      for (const license of licensesData) {
        try {
          const licenseValidations = await licensesService.validations(license.id, 0, 100);
          allValidations.push(...licenseValidations.map(v => ({
            ...v,
            license_key: license.license_key,
            client_id: license.client_id,
          })));
        } catch (e) {
          // Ignora erros de licenças sem validações
        }
      }

      // Ordena por data mais recente
      allValidations.sort((a, b) => {
        const dateA = a.created_at ? new Date(a.created_at) : new Date(0);
        const dateB = b.created_at ? new Date(b.created_at) : new Date(0);
        return dateB - dateA;
      });

      setValidations(allValidations);
    } catch (error) {
      console.error('Erro ao carregar validações:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredValidations = validations.filter(validation => {
    const matchesSearch =
      validation.license_key?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      validation.ip_address?.includes(searchTerm) ||
      validation.hardware_id?.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesType = typeFilter === 'all' || validation.validation_type === typeFilter;
    const matchesSuccess =
      successFilter === 'all' ||
      (successFilter === 'success' && validation.success) ||
      (successFilter === 'failed' && !validation.success);

    return matchesSearch && matchesType && matchesSuccess;
  });

  const getClient = (clientId) => clients.find(c => c.id === clientId);

  const getTypeLabel = (type) => {
    const labels = {
      activation: 'Ativação',
      heartbeat: 'Heartbeat',
      check: 'Verificação',
    };
    return labels[type] || type;
  };

  const getTypeVariant = (type) => {
    const variants = {
      activation: 'purple',
      heartbeat: 'info',
      check: 'default',
    };
    return variants[type] || 'default';
  };

  // Estatísticas
  const stats = {
    total: validations.length,
    successful: validations.filter(v => v.success).length,
    failed: validations.filter(v => !v.success).length,
    activations: validations.filter(v => v.validation_type === 'activation').length,
    heartbeats: validations.filter(v => v.validation_type === 'heartbeat').length,
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
          <h1 className="text-3xl font-bold text-white">Histórico de Validações</h1>
          <p className="text-white/60 mt-1">Monitore todas as validações de licença</p>
        </div>
        <Button icon={RefreshCw} variant="secondary" onClick={loadData}>
          Atualizar
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card hover={false}>
          <CardContent className="py-4 text-center">
            <p className="text-3xl font-bold text-white">{stats.total}</p>
            <p className="text-white/50 text-sm">Total</p>
          </CardContent>
        </Card>
        <Card hover={false}>
          <CardContent className="py-4 text-center">
            <p className="text-3xl font-bold text-green-400">{stats.successful}</p>
            <p className="text-white/50 text-sm">Sucesso</p>
          </CardContent>
        </Card>
        <Card hover={false}>
          <CardContent className="py-4 text-center">
            <p className="text-3xl font-bold text-red-400">{stats.failed}</p>
            <p className="text-white/50 text-sm">Falhas</p>
          </CardContent>
        </Card>
        <Card hover={false}>
          <CardContent className="py-4 text-center">
            <p className="text-3xl font-bold text-purple-400">{stats.activations}</p>
            <p className="text-white/50 text-sm">Ativações</p>
          </CardContent>
        </Card>
        <Card hover={false}>
          <CardContent className="py-4 text-center">
            <p className="text-3xl font-bold text-blue-400">{stats.heartbeats}</p>
            <p className="text-white/50 text-sm">Heartbeats</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card hover={false}>
        <CardContent className="py-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <Input
                icon={Search}
                placeholder="Buscar por chave, IP ou hardware ID..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <Select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              options={[
                { value: 'all', label: 'Todos os tipos' },
                { value: 'activation', label: 'Ativação' },
                { value: 'heartbeat', label: 'Heartbeat' },
                { value: 'check', label: 'Verificação' },
              ]}
              className="w-40"
            />
            <Select
              value={successFilter}
              onChange={(e) => setSuccessFilter(e.target.value)}
              options={[
                { value: 'all', label: 'Todos' },
                { value: 'success', label: 'Sucesso' },
                { value: 'failed', label: 'Falha' },
              ]}
              className="w-32"
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
                <TableHead>Data/Hora</TableHead>
                <TableHead>Licença</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>Hardware ID</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredValidations.map((validation, index) => {
                const client = getClient(validation.client_id);

                return (
                  <TableRow key={`${validation.id}-${index}`}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-white/50" />
                        <span className="text-white/70">
                          {validation.created_at
                            ? format(parseISO(validation.created_at), "dd/MM/yyyy HH:mm:ss", { locale: ptBR })
                            : '-'
                          }
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <code className="text-blue-400 font-mono text-sm">
                        {validation.license_key}
                      </code>
                    </TableCell>
                    <TableCell>
                      <span className="text-white">{client?.name || '-'}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getTypeVariant(validation.validation_type)} size="sm">
                        {getTypeLabel(validation.validation_type)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {validation.success ? (
                        <div className="flex items-center gap-2 text-green-400">
                          <CheckCircle className="w-4 h-4" />
                          <span>Sucesso</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 text-red-400">
                          <XCircle className="w-4 h-4" />
                          <span title={validation.error_message}>Falha</span>
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Globe className="w-4 h-4 text-white/50" />
                        <span className="font-mono text-white/70 text-sm">
                          {validation.ip_address || '-'}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Monitor className="w-4 h-4 text-white/50" />
                        <code className="font-mono text-white/70 text-xs truncate max-w-[150px]" title={validation.hardware_id}>
                          {validation.hardware_id ? validation.hardware_id.substring(0, 16) + '...' : '-'}
                        </code>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {filteredValidations.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-white/50">
                    {searchTerm || typeFilter !== 'all' || successFilter !== 'all'
                      ? 'Nenhuma validação encontrada'
                      : 'Nenhuma validação registrada'
                    }
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
