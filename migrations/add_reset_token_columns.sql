-- =====================================================
-- MIGRACAO: Adicionar colunas para recuperacao de senha
-- =====================================================
-- Data: 2025-12-25
-- Descricao: Adiciona colunas reset_token e reset_token_expires_at
--            na tabela users para suportar recuperacao de senha
--
-- IMPORTANTE: Este script usa IF NOT EXISTS, entao e seguro
--             executar multiplas vezes (idempotente)
-- =====================================================

-- Adiciona coluna reset_token se nao existir
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'reset_token'
    ) THEN
        ALTER TABLE users ADD COLUMN reset_token VARCHAR(255);
        RAISE NOTICE 'Coluna reset_token adicionada com sucesso';
    ELSE
        RAISE NOTICE 'Coluna reset_token ja existe';
    END IF;
END $$;

-- Adiciona coluna reset_token_expires_at se nao existir
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'reset_token_expires_at'
    ) THEN
        ALTER TABLE users ADD COLUMN reset_token_expires_at TIMESTAMP;
        RAISE NOTICE 'Coluna reset_token_expires_at adicionada com sucesso';
    ELSE
        RAISE NOTICE 'Coluna reset_token_expires_at ja existe';
    END IF;
END $$;

-- Cria indice para busca rapida por token (se nao existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'users' AND indexname = 'idx_users_reset_token'
    ) THEN
        CREATE INDEX idx_users_reset_token ON users(reset_token) WHERE reset_token IS NOT NULL;
        RAISE NOTICE 'Indice idx_users_reset_token criado com sucesso';
    ELSE
        RAISE NOTICE 'Indice idx_users_reset_token ja existe';
    END IF;
END $$;

-- Verificacao final
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name IN ('reset_token', 'reset_token_expires_at')
ORDER BY column_name;
