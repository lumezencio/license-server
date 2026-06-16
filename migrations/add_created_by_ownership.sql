-- =====================================================================
-- MIGRACAO: Controle de acesso por dono (created_by)
-- =====================================================================
-- Adiciona a coluna created_by aos lancamentos financeiros e calculos
-- juridicos, permitindo o filtro:
--   - superadmin (dono da conta) -> ve TODOS os lancamentos
--   - demais usuarios            -> veem apenas os que eles criaram
--
-- IMPORTANTE:
--  * Idempotente: pode ser executado varias vezes com seguranca.
--  * Nao faz backfill: registros antigos ficam com created_by = NULL,
--    o que (por decisao do cliente) os deixa visiveis SOMENTE ao superadmin.
--  * O "superadmin" e determinado no LOGIN (email == email de cadastro do
--    tenant), portanto NAO e necessario alterar a tabela users aqui.
--
-- COMO EXECUTAR (para CADA tenant):
--   license-db (novos tenants):
--     docker exec license-db psql -U license_admin -d cliente_XXXX -f /tmp/add_created_by_ownership.sql
--   enterprise-db (tenant legado 29235654000186):
--     docker exec enterprise-db psql -U enterprise_admin -d cliente_29235654000186 -f /tmp/add_created_by_ownership.sql
-- =====================================================================

ALTER TABLE accounts_receivable ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);
ALTER TABLE accounts_payable    ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);
ALTER TABLE purchases           ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);

-- Estas duas ja costumam ter a coluna no schema novo, mas garantimos
-- para tenants antigos que possam nao ter:
ALTER TABLE sales               ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);
ALTER TABLE legal_calculations  ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);

-- Indices para acelerar o filtro por dono (opcional, mas recomendado):
CREATE INDEX IF NOT EXISTS idx_ar_created_by ON accounts_receivable (created_by);
CREATE INDEX IF NOT EXISTS idx_ap_created_by ON accounts_payable (created_by);
CREATE INDEX IF NOT EXISTS idx_purchases_created_by ON purchases (created_by);
CREATE INDEX IF NOT EXISTS idx_sales_created_by ON sales (created_by);
CREATE INDEX IF NOT EXISTS idx_legalcalc_created_by ON legal_calculations (created_by);
