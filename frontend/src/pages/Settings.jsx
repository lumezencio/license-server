import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Settings as SettingsIcon, Key, Shield, Server, Globe,
  Copy, Eye, EyeOff, RefreshCw, Download
} from 'lucide-react';
import { Card, CardContent, CardHeader, Button, Badge } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';

export default function Settings() {
  const { user } = useAuth();
  const [showPublicKey, setShowPublicKey] = useState(false);
  const [publicKey, setPublicKey] = useState('');
  const [loadingKey, setLoadingKey] = useState(false);

  const loadPublicKey = async () => {
    setLoadingKey(true);
    try {
      const response = await fetch('/api/v1/public-key');
      const data = await response.json();
      setPublicKey(data.public_key);
      setShowPublicKey(true);
    } catch (error) {
      console.error('Erro ao carregar chave pública:', error);
    } finally {
      setLoadingKey(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    alert('Copiado!');
  };

  const downloadPublicKey = () => {
    const blob = new Blob([publicKey], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'license-server-public-key.pem';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Configurações</h1>
        <p className="text-white/60 mt-1">Configurações do servidor de licenças</p>
      </div>

      {/* Server Info */}
      <Card hover={false}>
        <CardHeader>
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-blue-400" />
            Informações do Servidor
          </h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white/5 rounded-xl p-4">
              <p className="text-white/50 text-sm">Versão</p>
              <p className="text-white font-semibold mt-1">1.0.0</p>
            </div>
            <div className="bg-white/5 rounded-xl p-4">
              <p className="text-white/50 text-sm">Ambiente</p>
              <Badge variant="warning" className="mt-2">Development</Badge>
            </div>
            <div className="bg-white/5 rounded-xl p-4">
              <p className="text-white/50 text-sm">Criptografia</p>
              <p className="text-white font-semibold mt-1">RSA 4096-bit</p>
            </div>
            <div className="bg-white/5 rounded-xl p-4">
              <p className="text-white/50 text-sm">Algoritmo</p>
              <p className="text-white font-semibold mt-1">RSA-PSS + SHA256</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* User Info */}
      <Card hover={false}>
        <CardHeader>
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-purple-400" />
            Usuário Atual
          </h3>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <span className="text-2xl font-bold text-white">
                {user?.full_name?.charAt(0) || 'A'}
              </span>
            </div>
            <div>
              <p className="text-xl font-bold text-white">{user?.full_name || 'Admin'}</p>
              <p className="text-white/60">{user?.email}</p>
              <div className="flex gap-2 mt-2">
                {user?.is_superadmin && (
                  <Badge variant="purple">Super Admin</Badge>
                )}
                <Badge variant="success">Ativo</Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Public Key */}
      <Card hover={false}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
              <Key className="w-5 h-5 text-amber-400" />
              Chave Pública RSA
            </h3>
            {!showPublicKey && (
              <Button
                variant="secondary"
                size="sm"
                icon={Eye}
                onClick={loadPublicKey}
                loading={loadingKey}
              >
                Mostrar Chave
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-white/60 text-sm mb-4">
            Esta chave pública é usada pelos clientes para verificar assinaturas de licença offline.
            Distribua esta chave junto com o software cliente.
          </p>

          {showPublicKey && publicKey && (
            <div className="space-y-4">
              <div className="bg-black/30 rounded-xl p-4 font-mono text-xs text-green-400 overflow-x-auto max-h-48 overflow-y-auto">
                <pre>{publicKey}</pre>
              </div>

              <div className="flex gap-3">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Copy}
                  onClick={() => copyToClipboard(publicKey)}
                >
                  Copiar
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Download}
                  onClick={downloadPublicKey}
                >
                  Download .pem
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={EyeOff}
                  onClick={() => setShowPublicKey(false)}
                >
                  Ocultar
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* API Endpoints */}
      <Card hover={false}>
        <CardHeader>
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Globe className="w-5 h-5 text-green-400" />
            Endpoints da API
          </h3>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              { method: 'POST', path: '/api/v1/activate', desc: 'Ativar licença' },
              { method: 'POST', path: '/api/v1/validate', desc: 'Validar licença (heartbeat)' },
              { method: 'GET', path: '/api/v1/public-key', desc: 'Obter chave pública' },
              { method: 'GET', path: '/api/v1/health', desc: 'Health check' },
            ].map((endpoint) => (
              <div
                key={endpoint.path}
                className="flex items-center gap-4 bg-white/5 rounded-xl p-3"
              >
                <Badge
                  variant={endpoint.method === 'GET' ? 'success' : 'info'}
                  size="sm"
                  className="w-16 justify-center"
                >
                  {endpoint.method}
                </Badge>
                <code className="text-blue-300 font-mono text-sm flex-1">{endpoint.path}</code>
                <span className="text-white/50 text-sm">{endpoint.desc}</span>
                <button
                  onClick={() => copyToClipboard(endpoint.path)}
                  className="p-2 hover:bg-white/10 rounded-lg transition-colors"
                >
                  <Copy className="w-4 h-4 text-white/50" />
                </button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Security Info */}
      <Card hover={false}>
        <CardHeader>
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-red-400" />
            Segurança
          </h3>
        </CardHeader>
        <CardContent>
          <div className="bg-amber-500/10 border border-amber-400/30 rounded-xl p-4 mb-4">
            <p className="text-amber-200 font-semibold mb-2">Importante</p>
            <ul className="text-amber-100/80 text-sm space-y-1 list-disc list-inside">
              <li>Mantenha a chave privada RSA em segurança absoluta</li>
              <li>Nunca exponha a chave privada ou endpoints administrativos</li>
              <li>Use HTTPS em produção</li>
              <li>Configure firewall para permitir apenas IPs autorizados</li>
              <li>Monitore tentativas de validação com falha</li>
            </ul>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <Shield className="w-8 h-8 text-green-400 mx-auto mb-2" />
              <p className="text-white font-semibold">RSA-PSS</p>
              <p className="text-white/50 text-sm">Assinatura segura</p>
            </div>
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <Key className="w-8 h-8 text-blue-400 mx-auto mb-2" />
              <p className="text-white font-semibold">4096-bit</p>
              <p className="text-white/50 text-sm">Chave robusta</p>
            </div>
            <div className="bg-white/5 rounded-xl p-4 text-center">
              <Globe className="w-8 h-8 text-purple-400 mx-auto mb-2" />
              <p className="text-white font-semibold">Hardware ID</p>
              <p className="text-white/50 text-sm">Binding único</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
