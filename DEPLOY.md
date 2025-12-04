# License Server - Guia de Deploy no Digital Ocean

## Arquitetura de Produção

```
┌─────────────────────────────────────────────────────────────────┐
│                     Digital Ocean                                │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   Droplet/App Platform                       ││
│  │                                                              ││
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  ││
│  │  │  License     │    │  License     │    │  PostgreSQL  │  ││
│  │  │  Server API  │◄──►│  Admin Panel │    │  Database    │  ││
│  │  │  (port 8080) │    │  (port 80)   │    │  (port 5432) │  ││
│  │  └──────────────┘    └──────────────┘    └──────────────┘  ││
│  │         ▲                                        │          ││
│  │         │                                        │          ││
│  │         └────────────────────────────────────────┘          ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│                              ▼                                   │
│                     Internet (HTTPS)                             │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │     Enterprise System          │
              │     (Cliente)                  │
              │                                │
              │  - Valida licença na ativação  │
              │  - Heartbeat periódico         │
              │  - Grace period offline        │
              └────────────────────────────────┘
```

## Opção 1: Deploy com Droplet + Docker Compose

### 1. Criar Droplet

1. Acesse [cloud.digitalocean.com](https://cloud.digitalocean.com)
2. Create > Droplets
3. Selecione:
   - **Image**: Ubuntu 22.04 LTS
   - **Plan**: Basic ($6/mês - 1GB RAM, 25GB SSD)
   - **Datacenter**: NYC1 ou mais próximo
   - **Authentication**: SSH Key (recomendado)

### 2. Configurar Droplet

```bash
# Conectar via SSH
ssh root@SEU_IP_DO_DROPLET

# Atualizar sistema
apt update && apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Instalar Docker Compose
apt install docker-compose-plugin -y

# Criar diretório
mkdir -p /opt/license-server
cd /opt/license-server
```

### 3. Clonar Repositório

```bash
# Instalar Git
apt install git -y

# Clonar repositório (substitua pela URL do seu repo)
git clone https://github.com/seu-usuario/license-server.git .
```

### 4. Configurar Ambiente

```bash
# Criar arquivo .env
cat > .env << 'EOF'
# Database
DB_NAME=license_server
DB_USER=license_admin
DB_PASSWORD=SUA_SENHA_SEGURA_AQUI

# Security (gere com: openssl rand -hex 32)
SECRET_KEY=SUA_CHAVE_SECRETA_AQUI

# Admin
ADMIN_EMAIL=admin@seudominio.com
ADMIN_PASSWORD=SUA_SENHA_ADMIN_AQUI

# Ports
API_PORT=8090
FRONTEND_PORT=5174

# Frontend URL
VITE_API_URL=http://SEU_IP_OU_DOMINIO:8090

# CORS
CORS_ORIGINS=["http://SEU_IP_OU_DOMINIO:5174", "https://seudominio.com"]
EOF
```

### 5. Iniciar Serviços

```bash
# Build e start
docker compose -f docker-compose.prod.yml up -d --build

# Verificar logs
docker compose -f docker-compose.prod.yml logs -f

# Verificar status
docker compose -f docker-compose.prod.yml ps
```

### 6. Configurar Firewall

```bash
# Permitir portas necessárias
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 8090/tcp  # API
ufw allow 5174/tcp  # Frontend
ufw enable
```

### 7. Configurar SSL (Opcional mas Recomendado)

```bash
# Instalar Certbot
apt install certbot python3-certbot-nginx -y

# Instalar Nginx
apt install nginx -y

# Configurar Nginx como proxy reverso
cat > /etc/nginx/sites-available/license-server << 'EOF'
server {
    listen 80;
    server_name seudominio.com;

    location / {
        proxy_pass http://localhost:5174;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://localhost:8090/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# Ativar site
ln -s /etc/nginx/sites-available/license-server /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Obter certificado SSL
certbot --nginx -d seudominio.com
```

---

## Opção 2: Deploy com App Platform

O App Platform é mais simples mas mais caro. Siga o arquivo `.do/app.yaml`.

1. Acesse [cloud.digitalocean.com/apps](https://cloud.digitalocean.com/apps)
2. Create App
3. Conecte seu repositório GitHub
4. O App Platform detectará o `app.yaml` automaticamente
5. Configure as variáveis de ambiente secretas (SECRET_KEY, ADMIN_PASSWORD)
6. Deploy!

---

## Conectando o Enterprise System

Após o deploy do License Server, configure o Enterprise System para usar o servidor de licenças em produção:

### 1. Variável de Ambiente (Backend)

```bash
# No enterprise_system, configure:
LICENSE_SERVER_URL=https://seudominio.com
# ou
LICENSE_SERVER_URL=http://SEU_IP:8090
```

### 2. Variável de Ambiente (Frontend)

```bash
# No .env.production do frontend:
VITE_LICENSE_SERVER_URL=https://seudominio.com
```

---

## Criando a Primeira Licença

1. Acesse o painel admin: `http://SEU_IP:5174` ou `https://seudominio.com`
2. Faça login com ADMIN_EMAIL e ADMIN_PASSWORD
3. Vá em "Clients" > "Novo Cliente"
4. Cadastre o cliente
5. Vá em "Licenses" > "Nova Licença"
6. Selecione o cliente e configure o plano
7. A chave de licença será gerada automaticamente (formato: XXXX-XXXX-XXXX-XXXX)

---

## Ativando Licença no Enterprise System

1. No enterprise_system, crie/edite o arquivo `license.json`:

```json
{
  "license_key": "XXXX-XXXX-XXXX-XXXX"
}
```

2. Na primeira execução, o sistema irá ativar automaticamente a licença
3. O hardware_id será registrado e a licença ficará vinculada àquela máquina

---

## Monitoramento

### Verificar Saúde do Sistema

```bash
# Health check da API
curl http://localhost:8090/api/v1/health

# Verificar logs
docker compose -f docker-compose.prod.yml logs -f api

# Verificar uso de recursos
docker stats
```

### Backup do Banco de Dados

```bash
# Backup
docker compose -f docker-compose.prod.yml exec db pg_dump -U license_admin license_server > backup_$(date +%Y%m%d).sql

# Restore
cat backup_YYYYMMDD.sql | docker compose -f docker-compose.prod.yml exec -T db psql -U license_admin license_server
```

---

## Troubleshooting

### API não responde

```bash
# Verificar se container está rodando
docker compose -f docker-compose.prod.yml ps

# Verificar logs
docker compose -f docker-compose.prod.yml logs api

# Reiniciar serviço
docker compose -f docker-compose.prod.yml restart api
```

### Erro de conexão com banco

```bash
# Verificar se PostgreSQL está rodando
docker compose -f docker-compose.prod.yml logs db

# Verificar conexão
docker compose -f docker-compose.prod.yml exec db psql -U license_admin -d license_server -c "SELECT 1"
```

### Licença não valida

1. Verifique se o LICENSE_SERVER_URL está correto
2. Verifique se o firewall permite a porta 8090
3. Verifique os logs do enterprise_system e do license-server

---

## Custos Estimados (Digital Ocean)

| Recurso | Especificação | Custo Mensal |
|---------|---------------|--------------|
| Droplet | Basic 1GB RAM | $6 |
| Database (Managed) | Dev/Test | $15 |
| **Total Básico** | | **$6-21** |

Para produção com mais clientes:
- Droplet 2GB RAM: $12/mês
- Database Production: $30/mês
- Load Balancer: $12/mês
- **Total Produção**: ~$54/mês

---

## Próximos Passos

1. [ ] Configurar domínio personalizado
2. [ ] Configurar SSL/HTTPS
3. [ ] Configurar backup automático
4. [ ] Configurar monitoramento (Uptime Robot, etc)
5. [ ] Configurar alertas de expiração de licença
