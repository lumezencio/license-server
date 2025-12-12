import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Users, Plus, Search, Edit2, Trash2, Building2, Mail, Phone,
  MapPin, Key, Eye
} from 'lucide-react';
import {
  Card, CardContent, CardHeader, Button, Input, Badge, Modal,
  LoadingSpinner, Icon3DButton, FormSection, FormGrid, FormField, FormInput, FormTextarea
} from '../components/ui';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '../components/ui/Table';
import { clientsService, licensesService } from '../services/api';
import { format, parseISO } from 'date-fns';
import { ptBR } from 'date-fns/locale';

export default function Clients() {
  const [loading, setLoading] = useState(true);
  const [clients, setClients] = useState([]);
  const [licenses, setLicenses] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState(null);
  const [viewingClient, setViewingClient] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    document: '',
    phone: '',
    contact_name: '',
    address: '',
    city: '',
    state: '',
    country: 'Brasil',
    notes: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [clientsData, licensesData] = await Promise.all([
        clientsService.list(),
        licensesService.list(),
      ]);
      setClients(clientsData);
      setLicenses(licensesData);
    } catch (error) {
      console.error('Erro ao carregar clientes:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredClients = clients.filter(client =>
    client.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    client.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    client.document?.includes(searchTerm)
  );

  const getClientLicenses = (clientId) => {
    return licenses.filter(l => l.client_id === clientId);
  };

  const openNewModal = () => {
    setEditingClient(null);
    setFormData({
      name: '',
      email: '',
      document: '',
      phone: '',
      contact_name: '',
      address: '',
      city: '',
      state: '',
      country: 'Brasil',
      notes: '',
    });
    setIsModalOpen(true);
  };

  const openEditModal = (client) => {
    setEditingClient(client);
    setFormData({
      name: client.name || '',
      email: client.email || '',
      document: client.document || '',
      phone: client.phone || '',
      contact_name: client.contact_name || '',
      address: client.address || '',
      city: client.city || '',
      state: client.state || '',
      country: client.country || 'Brasil',
      notes: client.notes || '',
    });
    setIsModalOpen(true);
  };

  const openViewModal = (client) => {
    setViewingClient(client);
    setIsViewModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      if (editingClient) {
        await clientsService.update(editingClient.id, formData);
      } else {
        await clientsService.create(formData);
      }
      setIsModalOpen(false);
      loadData();
    } catch (error) {
      console.error('Erro ao salvar cliente:', error);
      alert(error.response?.data?.detail || 'Erro ao salvar cliente');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (client) => {
    if (!confirm(`Deseja excluir o cliente "${client.name}"?`)) return;

    try {
      await clientsService.delete(client.id);
      loadData();
    } catch (error) {
      console.error('Erro ao excluir cliente:', error);
      alert(error.response?.data?.detail || 'Erro ao excluir cliente');
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
    <div className="space-y-4 sm:space-y-6">
      {/* Header - Responsivo */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Clientes</h1>
          <p className="text-white/60 mt-1 text-sm sm:text-base">Gerencie os clientes do sistema</p>
        </div>
        <Button icon={Plus} onClick={openNewModal} className="w-full sm:w-auto">
          Novo Cliente
        </Button>
      </div>

      {/* Search - Responsivo */}
      <Card hover={false}>
        <CardContent className="py-3 sm:py-4">
          <Input
            icon={Search}
            placeholder="Buscar por nome, email ou documento..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </CardContent>
      </Card>

      {/* Table - Responsivo */}
      <Card hover={false}>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead className="hidden sm:table-cell">Documento</TableHead>
                  <TableHead className="hidden md:table-cell">Contato</TableHead>
                  <TableHead>Licencas</TableHead>
                  <TableHead className="hidden lg:table-cell">Cadastro</TableHead>
                  <TableHead className="text-right">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredClients.map((client) => {
                  const clientLicenses = getClientLicenses(client.id);
                  const activeLicenses = clientLicenses.filter(l => l.status === 'active').length;

                  return (
                    <TableRow key={client.id}>
                      <TableCell>
                        <div className="flex items-center gap-2 sm:gap-3">
                          <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg sm:rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                            <Building2 className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
                          </div>
                          <div className="min-w-0">
                            <p className="font-semibold text-white text-sm sm:text-base truncate">{client.name}</p>
                            <p className="text-xs sm:text-sm text-white/50 truncate">{client.email}</p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <span className="font-mono text-white/70 text-xs sm:text-sm">{client.document || '-'}</span>
                      </TableCell>
                      <TableCell className="hidden md:table-cell">
                        <div>
                          <p className="text-white/70 text-sm">{client.contact_name || '-'}</p>
                          <p className="text-xs text-white/50">{client.phone || '-'}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 sm:gap-2 flex-wrap">
                          <Badge variant={activeLicenses > 0 ? 'success' : 'default'} size="sm">
                            {activeLicenses} ativa{activeLicenses !== 1 ? 's' : ''}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">
                        <span className="text-white/70 text-sm">
                          {client.created_at
                            ? format(parseISO(client.created_at), "dd/MM/yyyy", { locale: ptBR })
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
                            onClick={() => openViewModal(client)}
                          />
                          <Icon3DButton
                            icon={Edit2}
                            variant="primary"
                            size="iconOnly"
                            onClick={() => openEditModal(client)}
                          />
                          <Icon3DButton
                            icon={Trash2}
                            variant="danger"
                            size="iconOnly"
                            onClick={() => handleDelete(client)}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filteredClients.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-white/50">
                      {searchTerm ? 'Nenhum cliente encontrado' : 'Nenhum cliente cadastrado'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Create/Edit Modal - Responsivo */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingClient ? 'Editar Cliente' : 'Novo Cliente'}
        size="lg"
        icon={Building2}
      >
        <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-6">
          <FormSection title="Dados da Empresa" icon={Building2}>
            <FormGrid cols={2}>
              <FormField label="Nome da Empresa" required className="col-span-2 sm:col-span-2">
                <FormInput
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value.toUpperCase() })}
                  placeholder="Digite o nome da empresa"
                  required
                />
              </FormField>

              <FormField label="Email" required>
                <FormInput
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="email@empresa.com"
                  required
                />
              </FormField>

              <FormField label="CNPJ/CPF">
                <FormInput
                  value={formData.document}
                  onChange={(e) => setFormData({ ...formData, document: e.target.value })}
                  placeholder="00.000.000/0000-00"
                />
              </FormField>
            </FormGrid>
          </FormSection>

          <FormSection title="Contato" icon={Phone}>
            <FormGrid cols={2}>
              <FormField label="Pessoa de Contato">
                <FormInput
                  value={formData.contact_name}
                  onChange={(e) => setFormData({ ...formData, contact_name: e.target.value.toUpperCase() })}
                  placeholder="Nome do responsavel"
                />
              </FormField>

              <FormField label="Telefone">
                <FormInput
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="(00) 00000-0000"
                />
              </FormField>
            </FormGrid>
          </FormSection>

          <FormSection title="Endereco" icon={MapPin}>
            <FormGrid cols={1}>
              <FormField label="Endereco">
                <FormInput
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value.toUpperCase() })}
                  placeholder="Rua, numero, complemento"
                />
              </FormField>
            </FormGrid>
            <FormGrid cols={3} className="mt-4">
              <FormField label="Cidade">
                <FormInput
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value.toUpperCase() })}
                  placeholder="Cidade"
                />
              </FormField>

              <FormField label="Estado">
                <FormInput
                  value={formData.state}
                  onChange={(e) => setFormData({ ...formData, state: e.target.value.toUpperCase() })}
                  placeholder="UF"
                  maxLength={2}
                />
              </FormField>

              <FormField label="Pais">
                <FormInput
                  value={formData.country}
                  onChange={(e) => setFormData({ ...formData, country: e.target.value.toUpperCase() })}
                  placeholder="Pais"
                />
              </FormField>
            </FormGrid>
          </FormSection>

          <FormSection title="Observacoes">
            <FormField label="Notas">
              <FormTextarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value.toUpperCase() })}
                placeholder="Observacoes sobre o cliente"
                rows={3}
              />
            </FormField>
          </FormSection>

          {/* Footer - Responsivo */}
          <div className="flex flex-col-reverse sm:flex-row justify-end gap-2 sm:gap-3 pt-4 border-t border-white/10">
            <Button variant="ghost" type="button" onClick={() => setIsModalOpen(false)} className="w-full sm:w-auto">
              Cancelar
            </Button>
            <Button type="submit" loading={saving} className="w-full sm:w-auto">
              {editingClient ? 'Salvar Alteracoes' : 'Criar Cliente'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* View Modal - Responsivo */}
      <Modal
        isOpen={isViewModalOpen}
        onClose={() => setIsViewModalOpen(false)}
        title="Detalhes do Cliente"
        size="lg"
        icon={Eye}
      >
        {viewingClient && (
          <div className="space-y-4 sm:space-y-6">
            {/* Header do cliente */}
            <div className="flex flex-col sm:flex-row items-center gap-3 sm:gap-4 text-center sm:text-left">
              <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-xl sm:rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0">
                <Building2 className="w-7 h-7 sm:w-8 sm:h-8 text-white" />
              </div>
              <div className="min-w-0">
                <h3 className="text-xl sm:text-2xl font-bold text-white truncate">{viewingClient.name}</h3>
                <p className="text-white/60 text-sm sm:text-base truncate">{viewingClient.email}</p>
              </div>
            </div>

            {/* Grid de informacoes - Responsivo */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Documento</p>
                <p className="text-white font-mono mt-1 text-sm sm:text-base">{viewingClient.document || '-'}</p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Telefone</p>
                <p className="text-white mt-1 text-sm sm:text-base">{viewingClient.phone || '-'}</p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Contato</p>
                <p className="text-white mt-1 text-sm sm:text-base">{viewingClient.contact_name || '-'}</p>
              </div>
              <div className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4">
                <p className="text-white/50 text-xs sm:text-sm">Localizacao</p>
                <p className="text-white mt-1 text-sm sm:text-base">
                  {viewingClient.city ? `${viewingClient.city}/${viewingClient.state}` : '-'}
                </p>
              </div>
            </div>

            {/* Licencas do Cliente */}
            <div>
              <h4 className="text-base sm:text-lg font-semibold text-white mb-3 sm:mb-4 flex items-center gap-2">
                <Key className="w-4 h-4 sm:w-5 sm:h-5 text-amber-400" />
                Licencas
              </h4>
              <div className="space-y-2 sm:space-y-3">
                {getClientLicenses(viewingClient.id).map((license) => (
                  <div
                    key={license.id}
                    className="bg-white/5 rounded-lg sm:rounded-xl p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2"
                  >
                    <div className="min-w-0">
                      <code className="text-blue-400 font-mono text-xs sm:text-sm break-all">{license.license_key}</code>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <Badge variant="info" size="sm">{license.plan}</Badge>
                        <Badge
                          variant={
                            license.status === 'active' ? 'success' :
                            license.status === 'expired' ? 'danger' :
                            license.status === 'pending' ? 'warning' : 'default'
                          }
                          size="sm"
                        >
                          {license.status}
                        </Badge>
                      </div>
                    </div>
                    <div className="text-left sm:text-right text-xs sm:text-sm">
                      <p className="text-white/50">Expira em</p>
                      <p className="text-white">
                        {license.expires_at
                          ? format(parseISO(license.expires_at), "dd/MM/yyyy")
                          : '-'
                        }
                      </p>
                    </div>
                  </div>
                ))}
                {getClientLicenses(viewingClient.id).length === 0 && (
                  <p className="text-white/50 text-center py-4 text-sm">Nenhuma licenca</p>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
