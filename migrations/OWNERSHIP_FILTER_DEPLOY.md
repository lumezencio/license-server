# Controle de Acesso por Dono (superadmin x admin) + Troca de Senha

Data: 2026-06-16

## Objetivo
1. **Troca de senha**: qualquer usuario logado pode alterar a propria senha pelo sistema
   (antes so existia o fluxo forcado no 1o login).
2. **Filtro por dono**:
   - **superadmin** = usuario com `role='superadmin'` (EXPLICITO; marcado na tela Usuarios)
     enxerga **TODOS** os lancamentos financeiros e calculos juridicos (incl. antigos).
   - **demais usuarios** (admin/user/etc) enxergam **APENAS o que eles proprios criaram**
     (created_by = id deles), em listagens, PAINEL e relatorios. Lancamentos de outros
     usuarios E registros antigos sem dono (created_by NULL) ficam visiveis SOMENTE ao
     superadmin.
   - NOTAS (2026-06-16): a regra "dono = email de cadastro" foi REMOVIDA (gerava
     superadmin inesperado; vale somente role explicito). Isolamento ESTRITO, valido
     "de agora pra frente": sem backfill do historico antigo (decisao do cliente) -
     dados sem created_by ficam so para superadmin; cada usuario novo ja nasce isolado.
   - Registros **antigos** (sem `created_by`) ficam visiveis **somente ao superadmin**
     (decisao do cliente).

## Arquivos alterados

### license-server (backend / API Gateway)
- `app/api/tenant_auth.py`
  - `verify_tenant_user`: retorna tambem `role`.
  - `tenant_login`: token JWT agora inclui `role` e `is_superadmin`
    (is_superadmin = role superadmin OU email == tenant.email).
- `app/api/tenant_gateway.py`
  - `get_tenant_from_token`: propaga `role` e `is_superadmin` para `user_data`
    (fallback p/ tokens antigos = is_admin, para nao esconder dados de sessoes ativas).
  - Helpers novos: `owner_filter()`, `owner_where()`, `current_user_id()`,
    `ensure_ownership_columns()` (garante a coluna created_by por tenant).
  - INSERTs gravam `created_by` (vendas, compras, contas a receber/pagar incl. parcelas,
    calculos juridicos).
  - Listagens e agregacoes (dashboard, stats e relatorios financeiros) aplicam o filtro.
- `app/core/tenant_schema.py`
  - Coluna `created_by VARCHAR(36)` adicionada em accounts_receivable, accounts_payable
    e purchases (sales e legal_calculations ja possuiam).

### enterprise_system (frontend)
- `frontend/src/components/ChangePasswordModal.jsx` (novo): modal "Alterar Senha".
- `frontend/src/components/DashboardLayout.jsx`: botao de engrenagem no topo abre o modal.

## VALIDACAO OBRIGATORIA ANTES DO DEPLOY
> A maquina de desenvolvimento esta SEM Python (o Python312 base foi removido e todos os
> venvs apontam para ele). Por isso o `py_compile` NAO foi executado localmente.
> **Rodar OBRIGATORIAMENTE antes do deploy** (ex.: dentro do container, que tem Python):

```bash
# Sintaxe do backend
docker exec license-api python -m py_compile app/api/tenant_gateway.py app/api/tenant_auth.py app/core/tenant_schema.py
# ou, com Python local restaurado:
python -m py_compile app/api/tenant_gateway.py app/api/tenant_auth.py app/core/tenant_schema.py

# Build do frontend
cd enterprise_system/frontend && npm run build
```

E testar localmente (login como superadmin e como admin) ANTES de subir.

## MIGRACAO DE BANCO (TODOS OS TENANTS EXISTENTES)
Aplicar `add_created_by_ownership.sql` em cada tenant. O gateway tambem cria a coluna
automaticamente na 1a requisicao (ensure_ownership_columns), mas rode a migracao para
garantir e criar os indices.

```bash
# Copiar o script para o servidor e para os containers de banco
scp migrations/add_created_by_ownership.sql root@192.241.243.248:/tmp/

# license-db (novos tenants) - repetir para cada cliente_*
ssh root@192.241.243.248 "docker cp /tmp/add_created_by_ownership.sql license-db:/tmp/ && \
  docker exec license-db psql -U license_admin -d cliente_00590417657 -f /tmp/add_created_by_ownership.sql"

# enterprise-db (tenant legado)
ssh root@192.241.243.248 "docker cp /tmp/add_created_by_ownership.sql enterprise-db:/tmp/ && \
  docker exec enterprise-db psql -U enterprise_admin -d cliente_29235654000186 -f /tmp/add_created_by_ownership.sql"
```

> NAO ha backfill: registros antigos ficam com created_by NULL e (por decisao) so o
> superadmin os ve. Se quiser que algum admin continue vendo um lote antigo, rode um
> UPDATE direcionado definindo created_by = <user_id do dono>.

## OBSERVACOES / PONTOS DE ATENCAO
- **superadmin = dono da conta**: e calculado no login comparando o email do usuario com
  `tenant.email`. Nenhuma alteracao na tabela users e necessaria. Se desejar marcar
  superadmin manualmente, basta `UPDATE users SET role='superadmin' WHERE email=...`.
- **Sessoes ativas (token 8h)**: tokens emitidos antes do deploy nao tem `is_superadmin`.
  Nesses casos o gateway usa `is_admin` como fallback (admins continuam vendo tudo ate
  relogar; usuarios comuns ja ficam restritos). Apos novo login o comportamento correto
  passa a valer.
- **Escopo do filtro**: aplica-se a Financas (contas a receber/pagar, vendas, compras) e
  Calculos Juridicos, alem do Dashboard e Relatorios financeiros. NAO se aplica a cadastros
  compartilhados (clientes, fornecedores, produtos, funcionarios) nem ao relatorio de
  Cadastros/Registry.
- **Endpoints GET/PUT/DELETE por ID** (ex.: abrir um lancamento especifico pelo id) ainda
  permitem acesso se o id for conhecido. As LISTAGENS ja nao expoem ids de terceiros.
  Hardening adicional (404 quando created_by != usuario) pode ser feito como proximo passo.
- **Seguranca do filtro inline**: o user_id vem de JWT assinado e e validado como UUID antes
  de ser inserido na query (sem risco de SQL injection).
