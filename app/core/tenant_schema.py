"""
Schema SQL completo para provisionamento de bancos de tenant.
Baseado na estrutura real do enterprise_system.
"""

TENANT_SCHEMA_SQL = """
-- =====================================================
-- TIPOS ENUM
-- =====================================================
DO $$ BEGIN
    CREATE TYPE accountreceivablestatus AS ENUM ('PENDING', 'PARTIAL', 'PAID', 'OVERDUE', 'CANCELLED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE paymentmethod AS ENUM ('DINHEIRO', 'PIX', 'CARTAO_CREDITO', 'CARTAO_DEBITO', 'BOLETO', 'TRANSFERENCIA', 'CHEQUE', 'OUTRO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE nfestatus AS ENUM ('PENDING', 'AUTHORIZED', 'REJECTED', 'CANCELLED', 'INUTILIZED', 'CONTINGENCY', 'ERROR');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- TABELA DE EMPRESA (COMPANIES)
-- =====================================================
CREATE TABLE IF NOT EXISTS companies (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Tipo de pessoa
    person_type VARCHAR(2) DEFAULT 'PJ',
    -- Dados da empresa
    trade_name VARCHAR(200),
    legal_name VARCHAR(200),
    document VARCHAR(20),
    state_registration VARCHAR(20),
    municipal_registration VARCHAR(20),
    -- Contato
    email VARCHAR(255),
    phone VARCHAR(20),
    mobile VARCHAR(20),
    website VARCHAR(255),
    -- Endereço
    zip_code VARCHAR(10),
    street VARCHAR(200),
    number VARCHAR(10),
    complement VARCHAR(100),
    neighborhood VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(2),
    country VARCHAR(50) DEFAULT 'Brasil',
    -- Dados bancários
    bank_name VARCHAR(100),
    bank_agency VARCHAR(20),
    bank_account VARCHAR(30),
    pix_key VARCHAR(100),
    -- Logo
    logo_path VARCHAR(500),
    -- Outros
    description TEXT,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA DE USUÁRIOS (USERS)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Dados de login
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    -- Dados pessoais
    full_name VARCHAR(255),
    phone VARCHAR(20),
    avatar_url VARCHAR(500),
    -- Permissões
    role VARCHAR(50) DEFAULT 'user',
    permissions JSONB,
    -- Status
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    -- 2FA
    two_factor_enabled BOOLEAN DEFAULT FALSE NOT NULL,
    two_factor_secret VARCHAR(255),
    backup_codes JSONB,
    -- Tokens
    verification_token VARCHAR(255),
    verification_token_expires_at TIMESTAMP,
    reset_token VARCHAR(255),
    reset_token_expires_at TIMESTAMP,
    refresh_token TEXT,
    refresh_token_expires_at TIMESTAMP,
    -- Login tracking
    failed_login_attempts INTEGER DEFAULT 0 NOT NULL,
    locked_until TIMESTAMP,
    last_login_at TIMESTAMP,
    last_login_ip VARCHAR(50),
    -- OAuth
    oauth_provider VARCHAR(50),
    oauth_id VARCHAR(255),
    -- Metadados
    user_metadata JSONB,
    deleted_at TIMESTAMP,
    -- Flag para trocar senha no primeiro acesso
    must_change_password BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA DE CLIENTES (CUSTOMERS)
-- =====================================================
CREATE TABLE IF NOT EXISTS customers (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Dados pessoais
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(200),
    phone VARCHAR(20),
    mobile VARCHAR(20),
    -- Documentos
    cpf_cnpj VARCHAR(20) UNIQUE,
    rg VARCHAR(20),
    birth_date DATE,
    gender VARCHAR(20),
    -- Endereço
    address VARCHAR(200),
    address_number VARCHAR(20),
    address_complement VARCHAR(100),
    neighborhood VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(2),
    zip_code VARCHAR(10),
    country VARCHAR(50) DEFAULT 'BR',
    -- Dados da empresa (PJ)
    company_name VARCHAR(200),
    trade_name VARCHAR(200),
    state_registration VARCHAR(30),
    municipal_registration VARCHAR(30),
    -- Tipo e status
    customer_type VARCHAR(20) DEFAULT 'individual',
    customer_status VARCHAR(20) DEFAULT 'active',
    -- Crédito
    credit_limit DECIMAL(15,2) DEFAULT 0,
    credit_used DECIMAL(15,2) DEFAULT 0,
    payment_term_days INTEGER,
    -- Metadados
    notes TEXT,
    tags JSONB,
    segment VARCHAR(50),
    payment_terms VARCHAR(100),
    customer_metadata JSONB,
    -- Controle
    is_active BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA DE FORNECEDORES (SUPPLIERS)
-- =====================================================
CREATE TABLE IF NOT EXISTS suppliers (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Tipo de pessoa
    tipo_pessoa VARCHAR(20),
    -- Dados da empresa (PJ)
    company_name VARCHAR(200),
    trade_name VARCHAR(200),
    cnpj VARCHAR(20) UNIQUE,
    state_registration VARCHAR(30),
    -- Dados pessoais (PF)
    name VARCHAR(200),
    cpf VARCHAR(20),
    -- Contato
    email VARCHAR(255),
    phone VARCHAR(20),
    website VARCHAR(200),
    contact_name VARCHAR(100),
    contact_email VARCHAR(200),
    contact_phone VARCHAR(20),
    -- Endereço
    address VARCHAR(200),
    address_number VARCHAR(20),
    address_complement VARCHAR(100),
    neighborhood VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(2),
    zip_code VARCHAR(10),
    country VARCHAR(50) DEFAULT 'BR',
    -- Informações comerciais
    payment_terms VARCHAR(100),
    delivery_time VARCHAR(50),
    min_order VARCHAR(50),
    rating VARCHAR(20),
    category VARCHAR(50),
    -- Observações
    notes TEXT,
    -- Status
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    -- Metadados
    supplier_metadata JSONB
);

-- =====================================================
-- TABELA DE PRODUTOS (PRODUCTS)
-- =====================================================
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Identificação básica
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(200),
    code VARCHAR(50),
    barcode_ean VARCHAR(50),
    barcode_ean128 VARCHAR(50),
    sku VARCHAR(100),
    item_type VARCHAR(20) DEFAULT 'PRODUCT',
    -- Fiscal
    ncm VARCHAR(10),
    cest VARCHAR(10),
    cfop_venda_estadual VARCHAR(10),
    cfop_venda_interestadual VARCHAR(10),
    origem_mercadoria VARCHAR(5) DEFAULT '0',
    cst_icms VARCHAR(10),
    aliquota_icms DECIMAL(5,2) DEFAULT 0,
    reducao_bc_icms DECIMAL(5,2) DEFAULT 0,
    icms_st_aliquota DECIMAL(5,2) DEFAULT 0,
    icms_st_mva DECIMAL(5,2) DEFAULT 0,
    cst_ipi VARCHAR(10),
    aliquota_ipi DECIMAL(5,2) DEFAULT 0,
    codigo_enquadramento_ipi VARCHAR(10),
    cst_pis VARCHAR(10),
    aliquota_pis DECIMAL(5,2) DEFAULT 0,
    cst_cofins VARCHAR(10),
    aliquota_cofins DECIMAL(5,2) DEFAULT 0,
    -- Descrições
    description TEXT,
    short_description VARCHAR(500),
    technical_specification TEXT,
    application TEXT,
    composition TEXT,
    -- Categorização
    category_id VARCHAR(36),
    subcategory_id VARCHAR(36),
    brand VARCHAR(100),
    model VARCHAR(100),
    -- Unidades
    unit_of_measure VARCHAR(20) DEFAULT 'UN',
    unit_weight DECIMAL(10,4) DEFAULT 0,
    gross_weight DECIMAL(10,4) DEFAULT 0,
    net_weight DECIMAL(10,4) DEFAULT 0,
    length DECIMAL(10,4) DEFAULT 0,
    width DECIMAL(10,4) DEFAULT 0,
    height DECIMAL(10,4) DEFAULT 0,
    volume DECIMAL(10,4) DEFAULT 0,
    packaging_unit VARCHAR(20),
    packaging_quantity DECIMAL(10,3) DEFAULT 0,
    pallet_quantity INTEGER DEFAULT 0,
    shelf_life_days INTEGER,
    storage_temperature_min DECIMAL(5,2),
    storage_temperature_max DECIMAL(5,2),
    -- Preços
    price DECIMAL(10,2) NOT NULL DEFAULT 0,
    cost_price DECIMAL(15,2) DEFAULT 0,
    additional_costs DECIMAL(15,2) DEFAULT 0,
    final_cost DECIMAL(15,2) DEFAULT 0,
    markup_percentage DECIMAL(5,2) DEFAULT 0,
    sale_price DECIMAL(15,2) DEFAULT 0,
    suggested_price DECIMAL(15,2) DEFAULT 0,
    minimum_price DECIMAL(15,2) DEFAULT 0,
    maximum_discount DECIMAL(5,2) DEFAULT 0,
    -- Estoque
    stock_control BOOLEAN DEFAULT TRUE,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    current_stock DECIMAL(15,3) DEFAULT 0,
    reserved_stock DECIMAL(15,3) DEFAULT 0,
    available_stock DECIMAL(15,3) DEFAULT 0,
    minimum_stock DECIMAL(15,3) DEFAULT 0,
    maximum_stock DECIMAL(15,3) DEFAULT 0,
    min_stock INTEGER,
    max_stock INTEGER,
    reorder_point DECIMAL(15,3) DEFAULT 0,
    economic_lot DECIMAL(15,3) DEFAULT 0,
    abc_classification VARCHAR(1),
    -- Fornecedor
    main_supplier_id VARCHAR(36),
    supplier_code VARCHAR(50),
    supplier_description VARCHAR(200),
    lead_time_days INTEGER,
    minimum_order_qty DECIMAL(15,3) DEFAULT 0,
    purchase_unit VARCHAR(20),
    conversion_factor DECIMAL(10,4) DEFAULT 1,
    -- Status
    status VARCHAR(20) DEFAULT 'ACTIVE',
    sales_status VARCHAR(20) DEFAULT 'ACTIVE',
    purchase_status VARCHAR(20) DEFAULT 'ACTIVE',
    -- Controles
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    quality_control BOOLEAN DEFAULT FALSE,
    serialized_control BOOLEAN DEFAULT FALSE,
    is_kit BOOLEAN DEFAULT FALSE,
    is_manufactured BOOLEAN DEFAULT FALSE,
    is_imported BOOLEAN DEFAULT FALSE,
    is_controlled BOOLEAN DEFAULT FALSE,
    -- Observações
    observations TEXT,
    internal_notes TEXT,
    sales_notes TEXT,
    purchase_notes TEXT,
    tags VARCHAR(500),
    -- Auditoria
    created_by_user_id VARCHAR(36),
    last_updated_by_user_id VARCHAR(36),
    -- Histórico
    last_purchase_date TIMESTAMP,
    last_purchase_price DECIMAL(15,2),
    last_sale_date TIMESTAMP,
    last_sale_price DECIMAL(15,2),
    last_cost_update TIMESTAMP,
    last_inventory_date TIMESTAMP,
    -- Imagens
    main_image VARCHAR(500),
    additional_images TEXT,
    technical_drawings TEXT,
    certificates TEXT,
    manuals TEXT
);

-- =====================================================
-- TABELA DE FUNCIONÁRIOS (EMPLOYEES)
-- =====================================================
CREATE TABLE IF NOT EXISTS employees (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Dados pessoais
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    name VARCHAR(200),  -- Campo auxiliar para nome completo (usado em JOINs)
    email VARCHAR(255),
    phone VARCHAR(20),
    mobile VARCHAR(20),
    -- Documentos
    cpf VARCHAR(14),
    rg VARCHAR(20),
    birth_date DATE,
    -- Endereço
    address VARCHAR(200),
    address_number VARCHAR(10),
    address_complement VARCHAR(100),
    neighborhood VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(2),
    zip_code VARCHAR(10),
    -- Informações trabalhistas
    position VARCHAR(100),
    department VARCHAR(100),
    hire_date DATE,
    termination_date DATE,
    salary DECIMAL(15,2) DEFAULT 0,
    commission_rate DECIMAL(5,2) DEFAULT 0,
    -- Flags
    is_seller BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    -- Observações
    notes TEXT,
    -- Metadados
    employee_metadata JSONB
);

-- =====================================================
-- TABELA DE VENDAS (SALES)
-- =====================================================
CREATE TABLE IF NOT EXISTS sales (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Identificação
    sale_number VARCHAR(20) UNIQUE NOT NULL,
    sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    customer_id VARCHAR(36) REFERENCES customers(id),
    seller_id VARCHAR(36) REFERENCES employees(id),
    company_id VARCHAR(36),
    -- Tipo de venda
    sale_type VARCHAR(20) DEFAULT 'SALE',
    -- Valores
    subtotal DECIMAL(15,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    shipping_amount DECIMAL(15,2) DEFAULT 0,
    -- Impostos
    icms_amount DECIMAL(15,2) DEFAULT 0,
    pis_amount DECIMAL(15,2) DEFAULT 0,
    cofins_amount DECIMAL(15,2) DEFAULT 0,
    iss_amount DECIMAL(15,2) DEFAULT 0,
    total_amount DECIMAL(15,2) DEFAULT 0,
    -- Pagamento
    payment_method VARCHAR(50) DEFAULT 'CASH',
    payment_status VARCHAR(30) DEFAULT 'pending',
    installments INTEGER DEFAULT 1,
    -- Status
    sale_status VARCHAR(30) DEFAULT 'completed',
    -- Datas de controle
    confirmed_at TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancelled_by VARCHAR(36),
    cancellation_reason TEXT,
    -- Reembolso
    is_refunded BOOLEAN DEFAULT FALSE,
    refunded_at TIMESTAMP,
    refunded_by VARCHAR(36),
    refund_reason TEXT,
    -- Controle de estoque
    is_stock_updated BOOLEAN DEFAULT FALSE,
    stock_updated_at TIMESTAMP,
    -- Observações
    notes TEXT,
    internal_notes TEXT,
    -- Versionamento
    version INTEGER DEFAULT 1,
    created_by VARCHAR(36),
    updated_by VARCHAR(36),
    deleted_at TIMESTAMP,
    -- Metadados
    sale_metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_status ON sales(sale_status);

-- =====================================================
-- ITENS DE VENDA (SALE_ITEMS)
-- =====================================================
CREATE TABLE IF NOT EXISTS sale_items (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    sale_id VARCHAR(36) NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id VARCHAR(36) REFERENCES products(id),
    -- Dados do item
    product_code VARCHAR(100),
    product_name VARCHAR(500) NOT NULL,
    product_description TEXT,
    quantity DECIMAL(15,4) DEFAULT 1,
    unit VARCHAR(20) DEFAULT 'UN',
    unit_price DECIMAL(15,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    subtotal DECIMAL(15,2) DEFAULT 0,
    total_amount DECIMAL(15,2) DEFAULT 0,
    -- Impostos
    icms_rate DECIMAL(5,2) DEFAULT 0,
    icms_amount DECIMAL(15,2) DEFAULT 0,
    pis_rate DECIMAL(5,2) DEFAULT 0,
    pis_amount DECIMAL(15,2) DEFAULT 0,
    cofins_rate DECIMAL(5,2) DEFAULT 0,
    cofins_amount DECIMAL(15,2) DEFAULT 0,
    -- Dados fiscais
    ncm_code VARCHAR(20),
    cfop VARCHAR(20),
    cst_icms VARCHAR(10),
    cst_pis VARCHAR(10),
    cst_cofins VARCHAR(10),
    -- Controle de estoque
    stock_reserved BOOLEAN DEFAULT FALSE,
    stock_deducted BOOLEAN DEFAULT FALSE,
    stock_deducted_at TIMESTAMP,
    item_order INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sale_item_sale ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_item_product ON sale_items(product_id);

-- =====================================================
-- CONFIGURAÇÕES FISCAIS (FISCAL_SETTINGS)
-- Armazena configurações para emissão de NF-e via SEFAZ
-- =====================================================
CREATE TABLE IF NOT EXISTS fiscal_settings (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Certificado Digital A1
    certificate_file BYTEA,
    certificate_password_encrypted VARCHAR(500),
    certificate_expires_at TIMESTAMP,
    certificate_serial VARCHAR(100),
    certificate_issuer VARCHAR(300),
    certificate_subject VARCHAR(300),
    -- Ambiente SEFAZ (1=Producao, 2=Homologacao)
    ambiente INTEGER DEFAULT 2,
    -- UF da empresa
    uf VARCHAR(2) NOT NULL DEFAULT 'SP',
    -- Código IBGE do município
    codigo_municipio VARCHAR(10),
    -- Numeração NF-e
    serie_nfe INTEGER DEFAULT 1,
    ultimo_numero_nfe INTEGER DEFAULT 0,
    -- Numeração NFC-e (Nota Fiscal de Consumidor)
    serie_nfce INTEGER DEFAULT 1,
    ultimo_numero_nfce INTEGER DEFAULT 0,
    -- Token CSC para NFC-e
    csc_id VARCHAR(10),
    csc_token VARCHAR(50),
    -- Regime Tributário (1=Simples Nacional, 2=SN Excesso, 3=Regime Normal)
    regime_tributario INTEGER DEFAULT 1,
    -- CNAE Principal
    cnae_principal VARCHAR(10),
    -- Inscrição Municipal
    inscricao_municipal VARCHAR(20),
    -- Configurações de impressão
    logo_danfe BYTEA,
    mensagem_contribuinte TEXT,
    -- Email para envio de NF-e
    email_remetente VARCHAR(255),
    email_copia VARCHAR(500),
    -- Contingência
    justificativa_contingencia TEXT,
    data_contingencia TIMESTAMP,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_configured BOOLEAN DEFAULT FALSE
);

-- =====================================================
-- EMISSÕES DE NF-e (NFE_EMISSIONS)
-- Registra todas as NF-e emitidas
-- =====================================================
CREATE TABLE IF NOT EXISTS nfe_emissions (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento com venda
    sale_id VARCHAR(36) REFERENCES sales(id),
    -- Modelo (55=NF-e, 65=NFC-e)
    modelo INTEGER DEFAULT 55,
    -- Dados da NF-e
    chave_acesso VARCHAR(44) UNIQUE,
    numero_nfe INTEGER NOT NULL,
    serie INTEGER NOT NULL,
    -- Status da NF-e
    status nfestatus DEFAULT 'PENDING',
    -- Autorização
    protocolo_autorizacao VARCHAR(20),
    data_autorizacao TIMESTAMP,
    digest_value VARCHAR(100),
    -- Ambiente (1=Producao, 2=Homologacao)
    ambiente INTEGER DEFAULT 2,
    -- Tipo de emissão (1=Normal, 9=Contingência)
    tipo_emissao INTEGER DEFAULT 1,
    -- XML armazenado
    xml_nfe TEXT,
    xml_protocolo TEXT,
    xml_evento TEXT,
    -- DANFE (PDF em base64)
    danfe_pdf TEXT,
    -- Valores totais
    valor_total DECIMAL(15,2) DEFAULT 0,
    valor_produtos DECIMAL(15,2) DEFAULT 0,
    valor_desconto DECIMAL(15,2) DEFAULT 0,
    valor_frete DECIMAL(15,2) DEFAULT 0,
    -- Impostos
    valor_icms DECIMAL(15,2) DEFAULT 0,
    valor_pis DECIMAL(15,2) DEFAULT 0,
    valor_cofins DECIMAL(15,2) DEFAULT 0,
    valor_ipi DECIMAL(15,2) DEFAULT 0,
    -- Mensagens de retorno
    codigo_retorno VARCHAR(10),
    motivo_retorno TEXT,
    -- Cancelamento
    cancelled_at TIMESTAMP,
    motivo_cancelamento TEXT,
    protocolo_cancelamento VARCHAR(20),
    xml_cancelamento TEXT,
    -- Carta de Correção
    ultima_carta_correcao TEXT,
    total_cartas_correcao INTEGER DEFAULT 0,
    -- Inutilização
    inutilized_at TIMESTAMP,
    justificativa_inutilizacao TEXT,
    protocolo_inutilizacao VARCHAR(20),
    -- Controle
    tentativas_envio INTEGER DEFAULT 0,
    ultimo_erro TEXT,
    -- Email enviado
    email_enviado BOOLEAN DEFAULT FALSE,
    email_enviado_at TIMESTAMP,
    email_destinatario VARCHAR(255),
    -- Metadados
    nfe_metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_nfe_emissions_sale ON nfe_emissions(sale_id);
CREATE INDEX IF NOT EXISTS idx_nfe_emissions_chave ON nfe_emissions(chave_acesso);
CREATE INDEX IF NOT EXISTS idx_nfe_emissions_numero ON nfe_emissions(numero_nfe, serie);
CREATE INDEX IF NOT EXISTS idx_nfe_emissions_status ON nfe_emissions(status);
CREATE INDEX IF NOT EXISTS idx_nfe_emissions_data ON nfe_emissions(created_at);

-- =====================================================
-- TABELA DE ORÇAMENTOS (QUOTATIONS)
-- =====================================================
CREATE TABLE IF NOT EXISTS quotations (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Identificação
    quotation_number VARCHAR(20) UNIQUE NOT NULL,
    quotation_date DATE NOT NULL,
    valid_until DATE,
    -- Relacionamentos
    customer_id VARCHAR(36) REFERENCES customers(id),
    seller_id VARCHAR(36) REFERENCES employees(id),
    -- Valores
    subtotal DECIMAL(15,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    freight_amount DECIMAL(15,2) DEFAULT 0,
    total_amount DECIMAL(15,2) DEFAULT 0,
    -- Pagamento
    payment_method VARCHAR(50),
    payment_terms VARCHAR(200),
    installments INTEGER DEFAULT 1,
    -- Status
    quotation_status VARCHAR(20) DEFAULT 'pending',
    -- Observações
    notes TEXT,
    internal_notes TEXT,
    -- Conversão para venda
    converted_to_sale BOOLEAN DEFAULT FALSE,
    sale_id VARCHAR(36) REFERENCES sales(id),
    converted_at TIMESTAMP,
    -- Metadados
    quotation_metadata JSONB
);

-- =====================================================
-- ITENS DE ORÇAMENTO (QUOTATION_ITEMS)
-- =====================================================
CREATE TABLE IF NOT EXISTS quotation_items (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    quotation_id VARCHAR(36) NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
    product_id VARCHAR(36) REFERENCES products(id),
    -- Dados do item
    product_name VARCHAR(200) NOT NULL,
    quantity DECIMAL(15,3) DEFAULT 1,
    unit_price DECIMAL(15,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    total_amount DECIMAL(15,2) DEFAULT 0
);

-- =====================================================
-- TABELA DE COMPRAS (PURCHASES)
-- =====================================================
CREATE TABLE IF NOT EXISTS purchases (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Identificação
    purchase_number VARCHAR(20) UNIQUE NOT NULL,
    -- Relacionamentos
    supplier_id VARCHAR(36) REFERENCES suppliers(id),
    -- Nota fiscal
    invoice_number VARCHAR(50),
    invoice_series VARCHAR(10),
    invoice_key VARCHAR(50),
    invoice_date DATE,
    -- Datas
    purchase_date DATE,
    delivery_date DATE,
    expected_delivery_date DATE,
    -- Valores
    subtotal DECIMAL(15,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    freight_amount DECIMAL(15,2) DEFAULT 0,
    insurance_amount DECIMAL(15,2) DEFAULT 0,
    other_expenses DECIMAL(15,2) DEFAULT 0,
    tax_amount DECIMAL(15,2) DEFAULT 0,
    total_amount DECIMAL(15,2) DEFAULT 0,
    -- Pagamento
    payment_method VARCHAR(50),
    payment_terms VARCHAR(100),
    installments INTEGER DEFAULT 1,
    -- Status
    status VARCHAR(20) DEFAULT 'pending',
    -- Observações
    notes TEXT,
    internal_notes TEXT,
    -- Controles
    stock_updated BOOLEAN DEFAULT FALSE,
    accounts_payable_created BOOLEAN DEFAULT FALSE,
    -- Fiscal
    cfop VARCHAR(10),
    nature_operation VARCHAR(100)
);

-- =====================================================
-- ITENS DE COMPRA (PURCHASE_ITEMS)
-- =====================================================
CREATE TABLE IF NOT EXISTS purchase_items (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    purchase_id VARCHAR(36) NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id VARCHAR(36) REFERENCES products(id),
    -- Identificação
    item_number INTEGER DEFAULT 1,
    description VARCHAR(200),
    -- Quantidades
    quantity DECIMAL(15,3) DEFAULT 1,
    quantity_received DECIMAL(15,3) DEFAULT 0,
    unit_of_measure VARCHAR(20) DEFAULT 'UN',
    -- Valores
    unit_price DECIMAL(15,2) DEFAULT 0,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    subtotal DECIMAL(15,2) DEFAULT 0,
    total DECIMAL(15,2) DEFAULT 0,
    -- Impostos
    icms_percent DECIMAL(5,2) DEFAULT 0,
    ipi_percent DECIMAL(5,2) DEFAULT 0,
    -- Lote
    batch_number VARCHAR(50),
    manufacturing_date DATE,
    expiration_date DATE,
    -- Fiscal
    ncm VARCHAR(10),
    cfop VARCHAR(10),
    -- Observações
    notes TEXT,
    -- Controle
    stock_updated BOOLEAN DEFAULT FALSE
);

-- =====================================================
-- CONTAS A RECEBER (ACCOUNTS_RECEIVABLE)
-- =====================================================
CREATE TABLE IF NOT EXISTS accounts_receivable (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    customer_id VARCHAR(36) REFERENCES customers(id),
    parent_id VARCHAR(36),
    -- Identificação
    description VARCHAR(200),
    document_number VARCHAR(50),
    -- Valores
    amount DECIMAL(15,2) DEFAULT 0,
    paid_amount DECIMAL(15,2) DEFAULT 0,
    discount DECIMAL(15,2) DEFAULT 0,
    interest DECIMAL(15,2) DEFAULT 0,
    fine DECIMAL(15,2) DEFAULT 0,
    -- Datas
    issue_date DATE,
    due_date DATE,
    payment_date DATE,
    -- Status e categoria
    status accountreceivablestatus DEFAULT 'PENDING',
    payment_method paymentmethod,
    category VARCHAR(50),
    -- Parcelamento
    installment_number INTEGER DEFAULT 0,
    total_installments INTEGER DEFAULT 1,
    -- Controle
    is_active BOOLEAN DEFAULT TRUE,
    -- Observações
    notes TEXT
);

-- =====================================================
-- CONTAS A PAGAR (ACCOUNTS_PAYABLE)
-- =====================================================
CREATE TABLE IF NOT EXISTS accounts_payable (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    supplier_id VARCHAR(36) REFERENCES suppliers(id),
    purchase_id VARCHAR(36) REFERENCES purchases(id),
    parent_id VARCHAR(36),
    supplier VARCHAR(200),
    -- Identificação
    description VARCHAR(200),
    document_number VARCHAR(50),
    -- Valores
    amount DECIMAL(15,2) DEFAULT 0,
    amount_paid DECIMAL(15,2) DEFAULT 0,
    balance DECIMAL(15,2) DEFAULT 0,
    -- Datas
    issue_date DATE,
    due_date DATE,
    payment_date DATE,
    -- Status e categoria
    status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(50),
    category VARCHAR(50),
    -- Parcelamento
    installment_number INTEGER DEFAULT 0,
    total_installments INTEGER DEFAULT 1,
    -- Observações
    notes TEXT
);

-- =====================================================
-- CÁLCULOS JURÍDICOS (LEGAL_CALCULATIONS)
-- Schema completo conforme produção - NÃO ALTERAR!
-- =====================================================
CREATE TABLE IF NOT EXISTS legal_calculations (
    id VARCHAR(36) PRIMARY KEY,
    -- Identificação (NOT NULL conforme produção)
    nome VARCHAR(255) NOT NULL,
    descricao TEXT,
    numero_processo VARCHAR(100),
    customer_id VARCHAR(36) NOT NULL,
    -- Datas (NOT NULL conforme produção)
    data_calculo DATE NOT NULL,
    termo_final DATE NOT NULL,
    -- Índice de correção (NOT NULL conforme produção)
    indice_correcao VARCHAR(50) NOT NULL DEFAULT 'ipca_e',
    -- Opções de correção monetária
    aplicar_variacoes_positivas BOOLEAN DEFAULT TRUE,
    usar_capitalizacao_simples BOOLEAN DEFAULT FALSE,
    manter_valor_nominal_inflacao_negativa BOOLEAN DEFAULT TRUE,
    -- Juros de mora (NOT NULL conforme produção)
    tipo_juros_mora VARCHAR(50) NOT NULL DEFAULT 'nao_aplicar',
    percentual_juros_mora DECIMAL(10,4) DEFAULT 1.0,
    juros_mora_a_partir_de VARCHAR(50) DEFAULT 'vencimento',
    data_fixa_juros_mora DATE,
    aplicar_juros_mora_pro_rata BOOLEAN DEFAULT TRUE,
    calcular_juros_mora_sobre_compensatorios BOOLEAN DEFAULT FALSE,
    capitalizar_juros_mora_mensal BOOLEAN DEFAULT FALSE,
    -- Juros compensatórios
    tipo_juros_compensatorios VARCHAR(50) NOT NULL DEFAULT 'nao_aplicar',
    percentual_juros_compensatorios DECIMAL(10,4) DEFAULT 0,
    juros_compensatorios_a_partir_de VARCHAR(50),
    data_fixa_juros_compensatorios DATE,
    capitalizar_juros_compensatorios_mensal BOOLEAN DEFAULT FALSE,
    -- Multa
    percentual_multa DECIMAL(10,4) DEFAULT 0,
    aplicar_multa_sobre_juros_mora BOOLEAN DEFAULT FALSE,
    aplicar_multa_sobre_juros_compensatorios BOOLEAN DEFAULT FALSE,
    aplicar_multa_nos_creditos BOOLEAN DEFAULT FALSE,
    aplicar_multa_523 BOOLEAN DEFAULT FALSE,
    aplicar_multa_moratoria_10 BOOLEAN DEFAULT FALSE,
    aplicar_honorarios_523_10 BOOLEAN DEFAULT FALSE,
    incluir_juros_mora_multa_523 BOOLEAN DEFAULT FALSE,
    incluir_custas_multa_523 BOOLEAN DEFAULT FALSE,
    incluir_honorarios_sucumbenciais_multa_523 BOOLEAN DEFAULT FALSE,
    incluir_multa_base_multa_523 BOOLEAN DEFAULT FALSE,
    incluir_juros_compensatorios_multa_523 BOOLEAN DEFAULT FALSE,
    -- Status
    status VARCHAR(50) DEFAULT 'ativo',
    -- Valores calculados
    valor_total_geral DECIMAL(15,2) DEFAULT 0,
    valor_principal DECIMAL(15,2) DEFAULT 0,
    valor_juros_mora DECIMAL(15,2) DEFAULT 0,
    valor_juros_compensatorios DECIMAL(15,2) DEFAULT 0,
    valor_multa DECIMAL(15,2) DEFAULT 0,
    valor_custas DECIMAL(15,2) DEFAULT 0,
    valor_despesas DECIMAL(15,2) DEFAULT 0,
    valor_honorarios_sucumbencia DECIMAL(15,2) DEFAULT 0,
    valor_honorarios_contratuais DECIMAL(15,2) DEFAULT 0,
    valor_multa_523 DECIMAL(15,2) DEFAULT 0,
    subtotal DECIMAL(15,2) DEFAULT 0,
    -- Metadados (armazena débitos e detalhes completos)
    metadata_calculo JSONB,
    -- Auditoria (NOT NULL conforme produção)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(36),
    updated_by VARCHAR(36),
    deleted_at TIMESTAMP,
    deleted_by VARCHAR(36),
    -- Campo adicional
    data_corte_juros_mora DATE
);

-- =====================================================
-- ÍNDICES PARA PERFORMANCE
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_customers_cpf_cnpj ON customers(cpf_cnpj);
CREATE INDEX IF NOT EXISTS idx_customers_first_name ON customers(first_name);
CREATE INDEX IF NOT EXISTS idx_customers_last_name ON customers(last_name);
CREATE INDEX IF NOT EXISTS idx_suppliers_cnpj ON suppliers(cnpj);
CREATE INDEX IF NOT EXISTS idx_suppliers_company_name ON suppliers(company_name);
CREATE INDEX IF NOT EXISTS idx_products_code ON products(code);
CREATE INDEX IF NOT EXISTS idx_products_barcode_ean ON products(barcode_ean);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_number ON sales(sale_number);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchases(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date);
CREATE INDEX IF NOT EXISTS idx_accounts_receivable_due ON accounts_receivable(due_date);
CREATE INDEX IF NOT EXISTS idx_accounts_receivable_customer ON accounts_receivable(customer_id);
CREATE INDEX IF NOT EXISTS idx_accounts_receivable_status ON accounts_receivable(status);
CREATE INDEX IF NOT EXISTS idx_accounts_payable_due ON accounts_payable(due_date);
CREATE INDEX IF NOT EXISTS idx_accounts_payable_supplier ON accounts_payable(supplier_id);
CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email);
CREATE INDEX IF NOT EXISTS idx_employees_cpf ON employees(cpf);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users(reset_token) WHERE reset_token IS NOT NULL;
"""

# =====================================================
# CONDOTECH - SISTEMA DE GESTÃO CONDOMINIAL
# =====================================================
CONDOTECH_SCHEMA_SQL = """
-- =====================================================
-- TIPOS ENUM - CONDOTECH
-- =====================================================
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('ADMIN', 'SINDICO', 'SUBSINDICO', 'CONSELHEIRO', 'PORTEIRO', 'MORADOR');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE unit_type AS ENUM ('APARTAMENTO', 'CASA', 'SALA_COMERCIAL', 'LOJA', 'GARAGEM', 'DEPOSITO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE resident_type AS ENUM ('PROPRIETARIO', 'INQUILINO', 'DEPENDENTE', 'FUNCIONARIO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE ticket_status AS ENUM ('ABERTO', 'EM_ANDAMENTO', 'AGUARDANDO', 'RESOLVIDO', 'FECHADO', 'CANCELADO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE ticket_priority AS ENUM ('BAIXA', 'MEDIA', 'ALTA', 'URGENTE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE ticket_category AS ENUM ('MANUTENCAO', 'BARULHO', 'SEGURANCA', 'LIMPEZA', 'FINANCEIRO', 'ADMINISTRATIVO', 'SUGESTAO', 'RECLAMACAO', 'OUTRO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE financial_type AS ENUM ('RECEITA', 'DESPESA');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE financial_status AS ENUM ('PENDENTE', 'PAGO', 'ATRASADO', 'CANCELADO', 'PARCIAL');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE reservation_status AS ENUM ('PENDENTE', 'CONFIRMADA', 'CANCELADA', 'CONCLUIDA');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE communication_type AS ENUM ('AVISO', 'COMUNICADO', 'CONVOCACAO', 'REGULAMENTO', 'ATA');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE package_status AS ENUM ('RECEBIDO', 'AGUARDANDO', 'RETIRADO', 'DEVOLVIDO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE pet_size AS ENUM ('PEQUENO', 'MEDIO', 'GRANDE');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE vehicle_type AS ENUM ('CARRO', 'MOTO', 'BICICLETA', 'OUTRO');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- TABELA DE USUÁRIOS (USERS)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Dados de login
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    -- Dados pessoais
    name VARCHAR(255) NOT NULL,
    cpf VARCHAR(14) UNIQUE,
    phone VARCHAR(20),
    avatar_url VARCHAR(500),
    -- Permissões
    role user_role DEFAULT 'MORADOR',
    permissions JSONB,
    -- Status
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    -- Tokens
    reset_token VARCHAR(255),
    reset_token_expires_at TIMESTAMP,
    -- Login tracking
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    last_login_at TIMESTAMP,
    -- Flag para trocar senha
    must_change_password BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA DE CONDOMÍNIOS (CONDOMINIUMS)
-- =====================================================
CREATE TABLE IF NOT EXISTS condominiums (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Dados básicos
    name VARCHAR(200) NOT NULL,
    cnpj VARCHAR(20) UNIQUE,
    -- Endereço
    zip_code VARCHAR(10),
    street VARCHAR(200),
    number VARCHAR(10),
    complement VARCHAR(100),
    neighborhood VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(2),
    -- Contato
    email VARCHAR(255),
    phone VARCHAR(20),
    -- Administração
    sindico_id VARCHAR(36) REFERENCES users(id),
    administradora VARCHAR(200),
    -- Configurações
    taxa_condominio DECIMAL(10,2) DEFAULT 0,
    dia_vencimento INTEGER DEFAULT 10,
    -- Status
    is_active BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA DE BLOCOS/TORRES (BLOCKS)
-- =====================================================
CREATE TABLE IF NOT EXISTS blocks (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id) ON DELETE CASCADE,
    -- Dados
    name VARCHAR(100) NOT NULL,
    description TEXT,
    floors INTEGER DEFAULT 1,
    -- Status
    is_active BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- TABELA DE UNIDADES (UNITS)
-- =====================================================
CREATE TABLE IF NOT EXISTS units (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id) ON DELETE CASCADE,
    block_id VARCHAR(36) REFERENCES blocks(id),
    -- Identificação
    number VARCHAR(20) NOT NULL,
    floor INTEGER,
    unit_type unit_type DEFAULT 'APARTAMENTO',
    -- Área
    area DECIMAL(10,2),
    -- Frações
    fracao_ideal DECIMAL(10,6),
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_rented BOOLEAN DEFAULT FALSE
);

-- =====================================================
-- TABELA DE MORADORES (RESIDENTS)
-- =====================================================
CREATE TABLE IF NOT EXISTS residents (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    user_id VARCHAR(36) REFERENCES users(id),
    -- Dados pessoais
    name VARCHAR(255) NOT NULL,
    cpf VARCHAR(14),
    rg VARCHAR(20),
    birth_date DATE,
    -- Contato
    email VARCHAR(255),
    phone VARCHAR(20),
    mobile VARCHAR(20),
    -- Tipo
    resident_type resident_type DEFAULT 'MORADOR',
    is_primary BOOLEAN DEFAULT FALSE,
    -- Datas
    move_in_date DATE,
    move_out_date DATE,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    -- Observações
    notes TEXT
);

-- =====================================================
-- TABELA DE VEÍCULOS (VEHICLES)
-- =====================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    resident_id VARCHAR(36) REFERENCES residents(id),
    -- Dados do veículo
    vehicle_type vehicle_type DEFAULT 'CARRO',
    brand VARCHAR(50),
    model VARCHAR(50),
    color VARCHAR(30),
    plate VARCHAR(10) NOT NULL,
    year INTEGER,
    -- Vaga
    parking_spot VARCHAR(20),
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    -- TAG/Controle
    tag_number VARCHAR(50),
    -- Observações
    notes TEXT
);

-- =====================================================
-- TABELA DE TICKETS/CHAMADOS (TICKETS)
-- =====================================================
CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Identificação
    ticket_number VARCHAR(20) UNIQUE NOT NULL,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    unit_id VARCHAR(36) REFERENCES units(id),
    created_by VARCHAR(36) REFERENCES users(id),
    assigned_to VARCHAR(36) REFERENCES users(id),
    -- Dados do chamado
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    category ticket_category DEFAULT 'OUTRO',
    priority ticket_priority DEFAULT 'MEDIA',
    status ticket_status DEFAULT 'ABERTO',
    -- Datas
    due_date DATE,
    closed_at TIMESTAMP,
    -- Resolução
    resolution TEXT,
    -- Anexos
    attachments JSONB
);

-- =====================================================
-- COMENTÁRIOS DE TICKETS (TICKET_COMMENTS)
-- =====================================================
CREATE TABLE IF NOT EXISTS ticket_comments (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    ticket_id VARCHAR(36) NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    user_id VARCHAR(36) REFERENCES users(id),
    -- Conteúdo
    content TEXT NOT NULL,
    is_internal BOOLEAN DEFAULT FALSE,
    -- Anexos
    attachments JSONB
);

-- =====================================================
-- COMUNICADOS (COMMUNICATIONS)
-- =====================================================
CREATE TABLE IF NOT EXISTS communications (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    created_by VARCHAR(36) REFERENCES users(id),
    -- Dados
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    communication_type communication_type DEFAULT 'AVISO',
    -- Visibilidade
    is_published BOOLEAN DEFAULT TRUE,
    publish_date TIMESTAMP,
    expire_date TIMESTAMP,
    -- Notificações
    send_email BOOLEAN DEFAULT FALSE,
    send_push BOOLEAN DEFAULT FALSE,
    -- Anexos
    attachments JSONB
);

-- =====================================================
-- ÁREAS COMUNS (COMMON_AREAS)
-- =====================================================
CREATE TABLE IF NOT EXISTS common_areas (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    -- Dados
    name VARCHAR(100) NOT NULL,
    description TEXT,
    capacity INTEGER,
    -- Reservas
    is_reservable BOOLEAN DEFAULT TRUE,
    requires_approval BOOLEAN DEFAULT FALSE,
    advance_days INTEGER DEFAULT 7,
    max_hours INTEGER DEFAULT 4,
    -- Taxa
    reservation_fee DECIMAL(10,2) DEFAULT 0,
    -- Horários
    opens_at TIME,
    closes_at TIME,
    -- Regras
    rules TEXT,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    -- Imagem
    image_url VARCHAR(500)
);

-- =====================================================
-- RESERVAS (RESERVATIONS)
-- =====================================================
CREATE TABLE IF NOT EXISTS reservations (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    common_area_id VARCHAR(36) NOT NULL REFERENCES common_areas(id),
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id),
    resident_id VARCHAR(36) REFERENCES residents(id),
    approved_by VARCHAR(36) REFERENCES users(id),
    -- Datas
    reservation_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    -- Status
    status reservation_status DEFAULT 'PENDENTE',
    -- Aprovação
    approved_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancellation_reason TEXT,
    -- Taxa
    fee_amount DECIMAL(10,2) DEFAULT 0,
    fee_paid BOOLEAN DEFAULT FALSE,
    -- Observações
    notes TEXT
);

-- =====================================================
-- LANÇAMENTOS FINANCEIROS (FINANCIAL_ENTRIES)
-- =====================================================
CREATE TABLE IF NOT EXISTS financial_entries (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    unit_id VARCHAR(36) REFERENCES units(id),
    created_by VARCHAR(36) REFERENCES users(id),
    -- Identificação
    reference VARCHAR(50),
    description VARCHAR(200) NOT NULL,
    -- Tipo
    entry_type financial_type NOT NULL,
    category VARCHAR(50),
    -- Valores
    amount DECIMAL(15,2) NOT NULL,
    discount DECIMAL(15,2) DEFAULT 0,
    interest DECIMAL(15,2) DEFAULT 0,
    fine DECIMAL(15,2) DEFAULT 0,
    total DECIMAL(15,2) NOT NULL,
    -- Datas
    due_date DATE NOT NULL,
    payment_date DATE,
    competence_date DATE,
    -- Status
    status financial_status DEFAULT 'PENDENTE',
    -- Pagamento
    payment_method VARCHAR(50),
    -- Boleto
    boleto_url VARCHAR(500),
    boleto_code VARCHAR(100),
    -- Observações
    notes TEXT
);

-- =====================================================
-- DOCUMENTOS (DOCUMENTS)
-- =====================================================
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    uploaded_by VARCHAR(36) REFERENCES users(id),
    -- Dados
    title VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(50),
    -- Arquivo
    file_url VARCHAR(500) NOT NULL,
    file_name VARCHAR(200),
    file_type VARCHAR(50),
    file_size INTEGER,
    -- Visibilidade
    is_public BOOLEAN DEFAULT TRUE,
    -- Status
    is_active BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- ENQUETES (POLLS)
-- =====================================================
CREATE TABLE IF NOT EXISTS polls (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    created_by VARCHAR(36) REFERENCES users(id),
    -- Dados
    title VARCHAR(200) NOT NULL,
    description TEXT,
    -- Opções (JSON array)
    options JSONB NOT NULL,
    -- Configurações
    allow_multiple BOOLEAN DEFAULT FALSE,
    is_anonymous BOOLEAN DEFAULT FALSE,
    -- Datas
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_published BOOLEAN DEFAULT FALSE
);

-- =====================================================
-- VOTOS DE ENQUETES (POLL_VOTES)
-- =====================================================
CREATE TABLE IF NOT EXISTS poll_votes (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    poll_id VARCHAR(36) NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id),
    user_id VARCHAR(36) REFERENCES users(id),
    -- Voto (índice da opção ou array para múltipla escolha)
    selected_options JSONB NOT NULL,
    -- Unicidade
    UNIQUE(poll_id, unit_id)
);

-- =====================================================
-- ENCOMENDAS/CORRESPONDÊNCIAS (PACKAGES)
-- =====================================================
CREATE TABLE IF NOT EXISTS packages (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id),
    received_by VARCHAR(36) REFERENCES users(id),
    delivered_by VARCHAR(36) REFERENCES users(id),
    -- Dados
    tracking_code VARCHAR(50),
    sender VARCHAR(100),
    carrier VARCHAR(50),
    description TEXT,
    -- Status
    status package_status DEFAULT 'RECEBIDO',
    -- Datas
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP,
    -- Observações
    notes TEXT
);

-- =====================================================
-- PETS (PETS)
-- =====================================================
CREATE TABLE IF NOT EXISTS pets (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    resident_id VARCHAR(36) REFERENCES residents(id),
    -- Dados
    name VARCHAR(100) NOT NULL,
    species VARCHAR(50) NOT NULL,
    breed VARCHAR(50),
    color VARCHAR(30),
    size pet_size DEFAULT 'MEDIO',
    birth_date DATE,
    -- Documentação
    vaccination_up_to_date BOOLEAN DEFAULT FALSE,
    last_vaccination DATE,
    microchip VARCHAR(50),
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    -- Foto
    photo_url VARCHAR(500),
    -- Observações
    notes TEXT
);

-- =====================================================
-- CONTATOS DE EMERGÊNCIA (EMERGENCY_CONTACTS)
-- =====================================================
CREATE TABLE IF NOT EXISTS emergency_contacts (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    -- Dados
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    phone VARCHAR(20) NOT NULL,
    phone_secondary VARCHAR(20),
    email VARCHAR(255),
    address TEXT,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    -- Ordem de exibição
    display_order INTEGER DEFAULT 0,
    -- Observações
    notes TEXT
);

-- =====================================================
-- VISITANTES (VISITORS)
-- =====================================================
CREATE TABLE IF NOT EXISTS visitors (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    unit_id VARCHAR(36) NOT NULL REFERENCES units(id),
    authorized_by VARCHAR(36) REFERENCES residents(id),
    -- Dados do visitante
    name VARCHAR(200) NOT NULL,
    document VARCHAR(20),
    phone VARCHAR(20),
    vehicle_plate VARCHAR(10),
    -- Autorização
    visit_date DATE NOT NULL,
    start_time TIME,
    end_time TIME,
    is_permanent BOOLEAN DEFAULT FALSE,
    valid_until DATE,
    -- Entrada/Saída
    checked_in_at TIMESTAMP,
    checked_out_at TIMESTAMP,
    checked_by VARCHAR(36) REFERENCES users(id),
    -- Observações
    notes TEXT
);

-- =====================================================
-- LOG DE ACESSOS (ACCESS_LOG)
-- =====================================================
CREATE TABLE IF NOT EXISTS access_log (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamentos
    condominium_id VARCHAR(36) NOT NULL REFERENCES condominiums(id),
    unit_id VARCHAR(36) REFERENCES units(id),
    resident_id VARCHAR(36) REFERENCES residents(id),
    visitor_id VARCHAR(36) REFERENCES visitors(id),
    registered_by VARCHAR(36) REFERENCES users(id),
    -- Dados
    access_type VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    access_point VARCHAR(50),
    -- Veículo
    vehicle_plate VARCHAR(10),
    -- Observações
    notes TEXT
);

-- =====================================================
-- ÍNDICES PARA PERFORMANCE - CONDOTECH
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_cpf ON users(cpf);
CREATE INDEX IF NOT EXISTS idx_condominiums_cnpj ON condominiums(cnpj);
CREATE INDEX IF NOT EXISTS idx_blocks_condominium ON blocks(condominium_id);
CREATE INDEX IF NOT EXISTS idx_units_condominium ON units(condominium_id);
CREATE INDEX IF NOT EXISTS idx_units_block ON units(block_id);
CREATE INDEX IF NOT EXISTS idx_residents_unit ON residents(unit_id);
CREATE INDEX IF NOT EXISTS idx_residents_cpf ON residents(cpf);
CREATE INDEX IF NOT EXISTS idx_vehicles_unit ON vehicles(unit_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_plate ON vehicles(plate);
CREATE INDEX IF NOT EXISTS idx_tickets_condominium ON tickets(condominium_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON tickets(created_by);
CREATE INDEX IF NOT EXISTS idx_ticket_comments_ticket ON ticket_comments(ticket_id);
CREATE INDEX IF NOT EXISTS idx_communications_condominium ON communications(condominium_id);
CREATE INDEX IF NOT EXISTS idx_common_areas_condominium ON common_areas(condominium_id);
CREATE INDEX IF NOT EXISTS idx_reservations_area ON reservations(common_area_id);
CREATE INDEX IF NOT EXISTS idx_reservations_unit ON reservations(unit_id);
CREATE INDEX IF NOT EXISTS idx_reservations_date ON reservations(reservation_date);
CREATE INDEX IF NOT EXISTS idx_financial_condominium ON financial_entries(condominium_id);
CREATE INDEX IF NOT EXISTS idx_financial_unit ON financial_entries(unit_id);
CREATE INDEX IF NOT EXISTS idx_financial_due_date ON financial_entries(due_date);
CREATE INDEX IF NOT EXISTS idx_financial_status ON financial_entries(status);
CREATE INDEX IF NOT EXISTS idx_documents_condominium ON documents(condominium_id);
CREATE INDEX IF NOT EXISTS idx_polls_condominium ON polls(condominium_id);
CREATE INDEX IF NOT EXISTS idx_poll_votes_poll ON poll_votes(poll_id);
CREATE INDEX IF NOT EXISTS idx_packages_condominium ON packages(condominium_id);
CREATE INDEX IF NOT EXISTS idx_packages_unit ON packages(unit_id);
CREATE INDEX IF NOT EXISTS idx_packages_status ON packages(status);
CREATE INDEX IF NOT EXISTS idx_pets_unit ON pets(unit_id);
CREATE INDEX IF NOT EXISTS idx_emergency_contacts_condominium ON emergency_contacts(condominium_id);
CREATE INDEX IF NOT EXISTS idx_visitors_condominium ON visitors(condominium_id);
CREATE INDEX IF NOT EXISTS idx_visitors_unit ON visitors(unit_id);
CREATE INDEX IF NOT EXISTS idx_visitors_date ON visitors(visit_date);
CREATE INDEX IF NOT EXISTS idx_access_log_condominium ON access_log(condominium_id);
CREATE INDEX IF NOT EXISTS idx_access_log_created ON access_log(created_at);
"""

# =====================================================
# DIARIO PESSOAL - SISTEMA DE DIÁRIO PESSOAL
# =====================================================
DIARIO_SCHEMA_SQL = """
-- =====================================================
-- TIPOS ENUM - DIARIO PESSOAL
-- =====================================================
DO $$ BEGIN
    CREATE TYPE mood_type AS ENUM ('happy', 'sad', 'neutral', 'anxious', 'excited', 'tired', 'angry', 'grateful', 'calm', 'stressed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE weather_type AS ENUM ('sunny', 'cloudy', 'rainy', 'snowy', 'windy', 'stormy', 'foggy');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE export_format AS ENUM ('pdf', 'txt', 'json', 'markdown');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- =====================================================
-- TABELA DE USUÁRIOS (USERS)
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Dados de login
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    -- Dados pessoais
    full_name VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    -- Permissões (necessário para compatibilidade com tenant_auth)
    role VARCHAR(50) DEFAULT 'user',
    -- Preferências
    timezone VARCHAR(50) DEFAULT 'America/Sao_Paulo',
    language VARCHAR(10) DEFAULT 'pt-BR',
    -- Status
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    -- Tokens
    reset_token VARCHAR(255),
    reset_token_expires_at TIMESTAMP,
    verification_token VARCHAR(255),
    verification_token_expires_at TIMESTAMP,
    -- Login tracking
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    last_login_at TIMESTAMP,
    last_login_ip VARCHAR(50),
    -- Flag para trocar senha
    must_change_password BOOLEAN DEFAULT TRUE,
    -- Soft delete (necessário para compatibilidade com tenant_auth)
    deleted_at TIMESTAMP
);

-- =====================================================
-- ENTRADAS DO DIÁRIO (DIARY_ENTRIES)
-- =====================================================
CREATE TABLE IF NOT EXISTS diary_entries (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Conteúdo
    title VARCHAR(255),
    content TEXT NOT NULL,
    content_html TEXT,
    summary VARCHAR(500),
    -- Humor e bem-estar
    mood mood_type DEFAULT 'neutral',
    mood_score INTEGER CHECK (mood_score >= 1 AND mood_score <= 10),
    energy_level INTEGER CHECK (energy_level >= 1 AND energy_level <= 10),
    -- Contexto
    weather weather_type,
    location VARCHAR(255),
    location_lat DECIMAL(10,8),
    location_lng DECIMAL(11,8),
    -- Organização
    is_favorite BOOLEAN DEFAULT FALSE,
    is_private BOOLEAN DEFAULT TRUE,
    is_pinned BOOLEAN DEFAULT FALSE,
    -- Métricas
    word_count INTEGER DEFAULT 0,
    reading_time INTEGER DEFAULT 0,
    -- Datas
    entry_date DATE NOT NULL,
    entry_time TIME,
    -- Mídia
    images JSONB,
    attachments JSONB,
    -- Metadados
    metadata JSONB,
    -- Soft delete
    deleted_at TIMESTAMP
);

-- =====================================================
-- TAGS (TAGS)
-- =====================================================
CREATE TABLE IF NOT EXISTS tags (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Dados
    name VARCHAR(50) NOT NULL,
    slug VARCHAR(50) NOT NULL,
    color VARCHAR(7) DEFAULT '#3B82F6',
    icon VARCHAR(50),
    description VARCHAR(200),
    -- Métricas
    usage_count INTEGER DEFAULT 0,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    -- Unicidade por usuário
    UNIQUE(user_id, slug)
);

-- =====================================================
-- RELAÇÃO ENTRADA-TAG (ENTRY_TAGS)
-- =====================================================
CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id VARCHAR(36) NOT NULL REFERENCES diary_entries(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entry_id, tag_id)
);

-- =====================================================
-- CONFIGURAÇÕES DO USUÁRIO (USER_SETTINGS)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_settings (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Aparência
    theme VARCHAR(20) DEFAULT 'dark',
    font_family VARCHAR(50) DEFAULT 'Inter',
    font_size VARCHAR(10) DEFAULT 'medium',
    -- Editor
    editor_mode VARCHAR(20) DEFAULT 'rich',
    auto_save BOOLEAN DEFAULT TRUE,
    auto_save_interval INTEGER DEFAULT 30,
    spell_check BOOLEAN DEFAULT TRUE,
    -- Notificações
    reminder_enabled BOOLEAN DEFAULT FALSE,
    reminder_time TIME DEFAULT '21:00:00',
    reminder_days JSONB DEFAULT '["mon","tue","wed","thu","fri","sat","sun"]',
    email_notifications BOOLEAN DEFAULT TRUE,
    -- Privacidade
    default_privacy VARCHAR(20) DEFAULT 'private',
    require_pin BOOLEAN DEFAULT FALSE,
    pin_hash VARCHAR(255),
    -- Estatísticas
    show_word_count BOOLEAN DEFAULT TRUE,
    show_mood_stats BOOLEAN DEFAULT TRUE,
    show_streak BOOLEAN DEFAULT TRUE,
    -- Exportação
    default_export_format export_format DEFAULT 'pdf',
    include_images_export BOOLEAN DEFAULT TRUE,
    -- Backup
    auto_backup BOOLEAN DEFAULT FALSE,
    backup_frequency VARCHAR(20) DEFAULT 'weekly',
    last_backup_at TIMESTAMP
);

-- =====================================================
-- PROMPTS DE ESCRITA (WRITING_PROMPTS)
-- =====================================================
CREATE TABLE IF NOT EXISTS writing_prompts (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento (NULL = prompt do sistema)
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
    -- Dados
    prompt_text TEXT NOT NULL,
    category VARCHAR(50),
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_system BOOLEAN DEFAULT FALSE,
    -- Métricas
    times_used INTEGER DEFAULT 0
);

-- =====================================================
-- HISTÓRICO DE HUMOR (MOOD_HISTORY)
-- =====================================================
CREATE TABLE IF NOT EXISTS mood_history (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_id VARCHAR(36) REFERENCES diary_entries(id) ON DELETE SET NULL,
    -- Dados
    mood mood_type NOT NULL,
    mood_score INTEGER CHECK (mood_score >= 1 AND mood_score <= 10),
    energy_level INTEGER CHECK (energy_level >= 1 AND energy_level <= 10),
    notes VARCHAR(500),
    -- Data
    recorded_date DATE NOT NULL,
    recorded_time TIME DEFAULT CURRENT_TIME
);

-- =====================================================
-- STREAKS E CONQUISTAS (USER_STREAKS)
-- =====================================================
CREATE TABLE IF NOT EXISTS user_streaks (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Streak atual
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    -- Datas
    streak_start_date DATE,
    last_entry_date DATE,
    -- Estatísticas
    total_entries INTEGER DEFAULT 0,
    total_words INTEGER DEFAULT 0,
    total_days_active INTEGER DEFAULT 0,
    -- Conquistas
    achievements JSONB DEFAULT '[]'
);

-- =====================================================
-- LOG DE ATIVIDADES (ACTIVITY_LOGS)
-- =====================================================
CREATE TABLE IF NOT EXISTS activity_logs (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    -- Dados
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(36),
    -- Detalhes
    old_values JSONB,
    new_values JSONB,
    description VARCHAR(500),
    -- Contexto
    ip_address INET,
    user_agent TEXT,
    -- Metadados
    metadata JSONB
);

-- =====================================================
-- TEMPLATES DE ENTRADA (ENTRY_TEMPLATES)
-- =====================================================
CREATE TABLE IF NOT EXISTS entry_templates (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Dados
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    content_template TEXT NOT NULL,
    -- Configurações
    default_mood mood_type,
    default_tags JSONB,
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,
    -- Métricas
    times_used INTEGER DEFAULT 0
);

-- =====================================================
-- COMPARTILHAMENTOS (SHARED_ENTRIES)
-- =====================================================
CREATE TABLE IF NOT EXISTS shared_entries (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Relacionamento
    entry_id VARCHAR(36) NOT NULL REFERENCES diary_entries(id) ON DELETE CASCADE,
    -- Compartilhamento
    share_token VARCHAR(100) UNIQUE NOT NULL,
    share_password_hash VARCHAR(255),
    -- Permissões
    allow_comments BOOLEAN DEFAULT FALSE,
    -- Validade
    expires_at TIMESTAMP,
    max_views INTEGER,
    view_count INTEGER DEFAULT 0,
    -- Status
    is_active BOOLEAN DEFAULT TRUE
);

-- =====================================================
-- ÍNDICES PARA PERFORMANCE - DIARIO
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_diary_entries_user ON diary_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_diary_entries_date ON diary_entries(entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_diary_entries_user_date ON diary_entries(user_id, entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_diary_entries_mood ON diary_entries(mood);
CREATE INDEX IF NOT EXISTS idx_diary_entries_favorite ON diary_entries(user_id, is_favorite) WHERE is_favorite = TRUE;
CREATE INDEX IF NOT EXISTS idx_diary_entries_deleted ON diary_entries(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tags_user ON tags(user_id);
CREATE INDEX IF NOT EXISTS idx_tags_slug ON tags(user_id, slug);
CREATE INDEX IF NOT EXISTS idx_entry_tags_entry ON entry_tags(entry_id);
CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_mood_history_user ON mood_history(user_id);
CREATE INDEX IF NOT EXISTS idx_mood_history_date ON mood_history(user_id, recorded_date DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON activity_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_entity ON activity_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_shared_entries_token ON shared_entries(share_token);
CREATE INDEX IF NOT EXISTS idx_writing_prompts_user ON writing_prompts(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_writing_prompts_system ON writing_prompts(is_system) WHERE is_system = TRUE;

-- =====================================================
-- TRIGGERS PARA ATUALIZAÇÃO AUTOMÁTICA
-- =====================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION count_words()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.content IS NOT NULL THEN
        NEW.word_count = array_length(regexp_split_to_array(trim(NEW.content), '\\s+'), 1);
        NEW.reading_time = GREATEST(1, NEW.word_count / 200);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_tag_usage()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE tags SET usage_count = usage_count + 1 WHERE id = NEW.tag_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE tags SET usage_count = GREATEST(0, usage_count - 1) WHERE id = OLD.tag_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Aplicar triggers
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_diary_entries_updated_at ON diary_entries;
CREATE TRIGGER update_diary_entries_updated_at BEFORE UPDATE ON diary_entries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tags_updated_at ON tags;
CREATE TRIGGER update_tags_updated_at BEFORE UPDATE ON tags
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_settings_updated_at ON user_settings;
CREATE TRIGGER update_user_settings_updated_at BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_word_count ON diary_entries;
CREATE TRIGGER update_word_count BEFORE INSERT OR UPDATE ON diary_entries
    FOR EACH ROW EXECUTE FUNCTION count_words();

DROP TRIGGER IF EXISTS update_tag_usage_insert ON entry_tags;
CREATE TRIGGER update_tag_usage_insert AFTER INSERT ON entry_tags
    FOR EACH ROW EXECUTE FUNCTION update_tag_usage();

DROP TRIGGER IF EXISTS update_tag_usage_delete ON entry_tags;
CREATE TRIGGER update_tag_usage_delete AFTER DELETE ON entry_tags
    FOR EACH ROW EXECUTE FUNCTION update_tag_usage();

-- =====================================================
-- DADOS INICIAIS - PROMPTS DO SISTEMA
-- =====================================================
INSERT INTO writing_prompts (id, prompt_text, category, is_system, is_active) VALUES
    (gen_random_uuid()::text, 'O que aconteceu de bom hoje?', 'gratidao', TRUE, TRUE),
    (gen_random_uuid()::text, 'Pelo que você é grato hoje?', 'gratidao', TRUE, TRUE),
    (gen_random_uuid()::text, 'Como você está se sentindo agora?', 'emocoes', TRUE, TRUE),
    (gen_random_uuid()::text, 'Qual foi o momento mais marcante do seu dia?', 'reflexao', TRUE, TRUE),
    (gen_random_uuid()::text, 'O que você aprendeu hoje?', 'aprendizado', TRUE, TRUE),
    (gen_random_uuid()::text, 'Quais são seus objetivos para amanhã?', 'planejamento', TRUE, TRUE),
    (gen_random_uuid()::text, 'Descreva um momento que te fez sorrir hoje.', 'positividade', TRUE, TRUE),
    (gen_random_uuid()::text, 'O que você faria diferente hoje se pudesse?', 'reflexao', TRUE, TRUE),
    (gen_random_uuid()::text, 'Qual desafio você enfrentou hoje e como lidou com ele?', 'desafios', TRUE, TRUE),
    (gen_random_uuid()::text, 'Escreva uma carta para o seu eu do futuro.', 'criativo', TRUE, TRUE)
ON CONFLICT DO NOTHING;
"""

# =====================================================
# MAPEAMENTO DE PRODUTOS PARA SCHEMAS
# =====================================================
PRODUCT_SCHEMAS = {
    "enterprise": TENANT_SCHEMA_SQL,
    "tech-emp": TENANT_SCHEMA_SQL,
    "condotech": CONDOTECH_SCHEMA_SQL,
    "diario": DIARIO_SCHEMA_SQL,
}

def get_schema_for_product(product_code: str) -> str:
    """Retorna o schema SQL apropriado para o produto especificado."""
    return PRODUCT_SCHEMAS.get(product_code.lower(), TENANT_SCHEMA_SQL)
