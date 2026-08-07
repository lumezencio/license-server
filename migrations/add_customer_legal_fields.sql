-- =====================================================================
-- MIGRACAO: campos juridicos/pessoais em customers (geracao de documentos)
-- =====================================================================
-- Adiciona os campos usados na Procuracao e Declaracoes (hipossuficiencia,
-- isento de IR) ao cadastro de clientes. Todos NULLABLE (aditivo e seguro).
--
-- Idempotente. O gateway tambem cria essas colunas automaticamente por tenant
-- (ensure_customer_columns), mas rode a migracao para garantir.
--
-- COMO EXECUTAR (para CADA tenant):
--   license-db:     docker exec license-db psql -U license_admin -d cliente_XXXX -f /tmp/add_customer_legal_fields.sql
--   enterprise-db:  docker exec enterprise-db psql -U enterprise_admin -d cliente_29235654000186 -f /tmp/add_customer_legal_fields.sql
-- =====================================================================

ALTER TABLE customers ADD COLUMN IF NOT EXISTS rg_issuer      VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS rg_issue_date  DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS nationality    VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS marital_status VARCHAR(50);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS profession     VARCHAR(150);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS birth_city     VARCHAR(150);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS birth_state    VARCHAR(2);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS mother_name    VARCHAR(255);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS father_name    VARCHAR(255);
