import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Users, Plus, Search, Edit2, Trash2, Building2, Mail, Phone,
  MapPin, MoreVertical, Key, Eye
} from 'lucide-react';
import Card, { CardContent, CardHeader } from '../components/ui/Card';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Badge from '../components/ui/Badge';
import Modal from '../components/ui/Modal';
import LoadingSpinner from '../components/ui/LoadingSpinner';
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Clientes</h1>
          <p className="text-white/60 mt-1">Gerencie os clientes do sistema</p>
        </div>
        <Button icon={Plus} onClick={openNewModal}>
          Novo Cliente
        </Button>
      </div>

      {/* Search */}
      <Card hover={false}>
        <CardContent className="py-4">
          <Input
            icon={Search}
            placeholder="Buscar por nome, email ou documento..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </CardContent>
      </Card>

      {/* Table */}
      <Card hover={false}>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cliente</TableHead>
                <TableHead>Documento</TableHead>
                <TableHead>Contato</TableHead>
                <TableHead>Licenças</TableHead>
                <TableHead>Cadastro</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredClients.map((client) => {
                const clientLicenses = getClientLicenses(client.id);
                const activeLicenses = clientLicenses.filter(l => l.status === 'active').length;

                return (
                  <TableRow key={client.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                          <Building2 className="w-5 h-5 text-white" />
                        </div>
                        <div>
                          <p className="font-semibold text-white">{client.name}</p>
                          <p className="text-sm text-white/50">{client.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-white/70">{client.document || '-'}</span>
                    </TableCell>
                    <TableCell>
                      <div>
                        <p className="text-white/70">{client.contact_name || '-'}</p>
                        <p className="text-sm text-white/50">{client.phone || '-'}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Badge variant={activeLicenses > 0 ? 'success' : 'default'}>
                          {activeLicenses} ativa{activeLicenses !== 1 ? 's' : ''}
                        </Badge>
                        {clientLicenses.length > activeLicenses && (
                          <Badge variant="default">
                            +{clientLicenses.length - activeLicenses}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-white/70">
                        {client.created_at
                          ? format(parseISO(client.created_at), "dd/MM/yyyy", { locale: ptBR })
                          : '-'
                        }
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Eye}
                          onClick={() => openViewModal(client)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Edit2}
                          onClick={() => openEditModal(client)}
                        />
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Trash2}
                          onClick={() => handleDelete(client)}
                          className="hover:text-red-400"
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
        </CardContent>
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingClient ? 'Editar Cliente' : 'Novo Cliente'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Nome da Empresa *"
              icon={Building2}
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
              className="md:col-span-2"
            />

            <Input
              label="Email *"
              type="email"
              icon={Mail}
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
            />

            <Input
              label="CNPJ/CPF"
              value={formData.document}
              onChange={(e) => setFormData({ ...formData, document: e.target.value })}
            />

            <Input
              label="Pessoa de Contato"
              value={formData.contact_name}
              onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
            />

            <Input
              label="Telefone"
              icon={Phone}
              value={formData.phone}
              onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
            />

            <Input
              label="Endereço"
              icon={MapPin}
              value={formData.address}
              onChange={(e) => setFormData({ ...formData, address: e.target.value })}
              className="md:col-span-2"
            />

            <Input
              label="Cidade"
              value={formData.city}
              onChange={(e) => setFormData({ ...formData, city: e.target.value })}
            />

            <Input
              label="Estado"
              value={formData.state}
              onChange={(e) => setFormData({ ...formData, state: e.target.value })}
              maxLength={2}
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-white mb-2">Observações</label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value.toUpperCase() })}
              rows={3}
              style={{ textTransform: 'uppercase' }}
              className="w-full px-4 py-3 bg-white/10 border border-white/30 rounded-xl text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-white/10">
            <Button variant="ghost" type="button" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={saving}>
              {editingClient ? 'Salvar Alterações' : 'Criar Cliente'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* View Modal */}
      <Modal
        isOpen={isViewModalOpen}
        onClose={() => setIsViewModalOpen(false)}
        title="Detalhes do Cliente"
        size="lg"
      >
        {viewingClient && (
          <div className="space-y-6">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
                <Building2 className="w-8 h-8 text-white" />
              </div>
              <div>
                <h3 className="text-2xl font-bold text-white">{viewingClient.name}</h3>
                <p className="text-white/60">{viewingClient.email}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm">Documento</p>
                <p className="text-white font-mono mt-1">{viewingClient.document || '-'}</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm">Telefone</p>
                <p className="text-white mt-1">{viewingClient.phone || '-'}</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm">Contato</p>
                <p className="text-white mt-1">{viewingClient.contact_name || '-'}</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm">Localização</p>
                <p className="text-white mt-1">
                  {viewingClient.city ? `${viewingClient.city}/${viewingClient.state}` : '-'}
                </p>
              </div>
            </div>

            {/* Licenças do Cliente */}
            <div>
              <h4 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Key className="w-5 h-5 text-amber-400" />
                Licenças
              </h4>
              <div className="space-y-3">
                {getClientLicenses(viewingClient.id).map((license) => (
                  <div
                    key={license.id}
                    className="bg-white/5 rounded-xl p-4 flex items-center justify-between"
                  >
                    <div>
                      <code className="text-blue-400 font-mono">{license.license_key}</code>
                      <div className="flex items-center gap-2 mt-1">
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
                    <div className="text-right text-sm">
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
                  <p className="text-white/50 text-center py-4">Nenhuma licença</p>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
