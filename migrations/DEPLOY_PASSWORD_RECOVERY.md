# Deploy: Sistema de Recuperacao de Senha

## Pre-requisitos

- [ ] Codigo testado localmente
- [ ] Sintaxe verificada (py_compile, npm build)
- [ ] Commit e push para GitHub realizados

---

## 1. TESTAR LOCALMENTE PRIMEIRO (OBRIGATORIO)

### 1.1 Iniciar servidores locais

```bash
# Terminal 1: License Server
cd /c/Projetos/license-server
venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8080

# Terminal 2: Frontend
cd /c/Projetos/enterprise_system/frontend
npm run dev
```

### 1.2 Testar fluxo completo

1. Acessar `http://localhost:5173/login`
2. Clicar em "Esqueceu a senha?"
3. Informar email cadastrado
4. Verificar logs do License Server para ver o token gerado
5. Acessar `http://localhost:5173/reset-password?token=TOKEN_GERADO`
6. Definir nova senha
7. Fazer login com nova senha

---

## 2. MIGRACAO DOS TENANTS EXISTENTES

### 2.1 Verificar se colunas existem (ANTES de migrar)

```bash
# Tenant legado (enterprise-db)
ssh root@192.241.243.248 "docker exec enterprise-db psql -U enterprise_admin -d cliente_29235654000186 -c \"
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN ('reset_token', 'reset_token_expires_at');
\""

# Tenant novo (license-db)
ssh root@192.241.243.248 "docker exec license-db psql -U license_admin -d cliente_00590417657 -c \"
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN ('reset_token', 'reset_token_expires_at');
\""
```

### 2.2 Aplicar migracao no tenant legado (enterprise-db)

```bash
# 1. Copiar script para o servidor
scp /c/Projetos/license-server/migrations/add_reset_token_columns.sql root@192.241.243.248:/tmp/

# 2. Copiar para container e executar
ssh root@192.241.243.248 "docker cp /tmp/add_reset_token_columns.sql enterprise-db:/tmp/ && \
docker exec enterprise-db psql -U enterprise_admin -d cliente_29235654000186 -f /tmp/add_reset_token_columns.sql"
```

### 2.3 Aplicar migracao nos tenants novos (license-db)

```bash
# Para cliente_00590417657
ssh root@192.241.243.248 "docker cp /tmp/add_reset_token_columns.sql license-db:/tmp/ && \
docker exec license-db psql -U license_admin -d cliente_00590417657 -f /tmp/add_reset_token_columns.sql"

# Para outros tenants (substituir TENANT_CODE)
# ssh root@192.241.243.248 "docker exec license-db psql -U license_admin -d cliente_TENANT_CODE -f /tmp/add_reset_token_columns.sql"
```

### 2.4 Verificar migracao (APOS migrar)

```bash
# Verificar tenant legado
ssh root@192.241.243.248 "docker exec enterprise-db psql -U enterprise_admin -d cliente_29235654000186 -c \"
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN ('reset_token', 'reset_token_expires_at');
\""

# Verificar tenant novo
ssh root@192.241.243.248 "docker exec license-db psql -U license_admin -d cliente_00590417657 -c \"
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'users' AND column_name IN ('reset_token', 'reset_token_expires_at');
\""
```

---

## 3. DEPLOY DO BACKEND (License Server)

### 3.1 Upload dos arquivos modificados

```bash
# tenant_auth.py (endpoints de recuperacao)
scp /c/Projetos/license-server/app/api/tenant_auth.py root@192.241.243.248:~/license-server/app/api/

# email.py (template de email)
scp /c/Projetos/license-server/app/core/email.py root@192.241.243.248:~/license-server/app/core/
```

### 3.2 Copiar para container e reiniciar

```bash
ssh root@192.241.243.248 "docker cp ~/license-server/app/api/tenant_auth.py license-api:/app/app/api/ && \
docker cp ~/license-server/app/core/email.py license-api:/app/app/core/ && \
docker restart license-api"
```

### 3.3 Verificar logs

```bash
ssh root@192.241.243.248 "docker logs license-api --tail 30"
```

---

## 4. DEPLOY DO FRONTEND

### 4.1 Build local

```bash
cd /c/Projetos/enterprise_system/frontend
npm run build
```

### 4.2 Upload para servidor

```bash
scp -r dist/* root@192.241.243.248:~/enterprise-clients/code/frontend/dist/
```

### 4.3 Limpar assets antigos e copiar novos

```bash
ssh root@192.241.243.248 "docker exec cliente1-frontend sh -c 'rm -rf /usr/share/nginx/html/assets/*' && \
docker cp ~/enterprise-clients/code/frontend/dist/. cliente1-frontend:/usr/share/nginx/html/ && \
docker exec cliente1-frontend nginx -s reload"
```

### 4.4 Verificar deploy

```bash
ssh root@192.241.243.248 "docker exec cliente1-frontend ls -la /usr/share/nginx/html/assets/ | head -10"
```

---

## 5. VERIFICACAO FINAL

### 5.1 Testar em producao

1. Acessar `https://www.tech-emp.com/login`
2. Clicar em "Esqueceu a senha?"
3. Informar email de um usuario real
4. Verificar se email foi recebido
5. Clicar no link do email
6. Definir nova senha
7. Fazer login com nova senha

### 5.2 Verificar logs apos teste

```bash
# Logs do License Server
ssh root@192.241.243.248 "docker logs license-api --tail 50 | grep -i 'recuperacao\|reset\|token'"
```

---

## ROLLBACK (se necessario)

### Reverter backend

```bash
# Restaurar versao anterior do tenant_auth.py (se tiver backup)
ssh root@192.241.243.248 "docker restart license-api"
```

### Reverter frontend

```bash
# Fazer novo build da versao anterior e repetir deploy
```

---

## Arquivos Modificados

| Arquivo | Descricao |
|---------|-----------|
| `license-server/app/api/tenant_auth.py` | Novos endpoints: forgot-password, reset-password, verify-reset-token |
| `license-server/app/core/email.py` | Novo metodo: send_password_reset_email |
| `frontend/src/pages/ForgotPassword.jsx` | Nova pagina de solicitacao |
| `frontend/src/pages/ResetPassword.jsx` | Nova pagina de redefinicao |
| `frontend/src/pages/Login.jsx` | Link atualizado |
| `frontend/src/App.jsx` | Novas rotas adicionadas |
| `license-server/migrations/add_reset_token_columns.sql` | Script de migracao |

---

## Checklist Final

- [ ] Testado localmente
- [ ] Migracao aplicada em cliente_29235654000186 (enterprise-db)
- [ ] Migracao aplicada em cliente_00590417657 (license-db)
- [ ] Backend deployado (license-api)
- [ ] Frontend deployado (cliente1-frontend)
- [ ] Testado em producao
- [ ] Logs verificados
