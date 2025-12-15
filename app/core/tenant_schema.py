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
    two_factor_enabled BOOLEAN DEFAULT FALSE,
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
    failed_login_attempts INTEGER DEFAULT 0,
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
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
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
    slug VARCHAR(200) NOT NULL,
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
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    mobile VARCHAR(20),
    -- Documentos
    cpf VARCHAR(14) UNIQUE,
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
    sale_date DATE NOT NULL,
    -- Relacionamentos
    customer_id VARCHAR(36) REFERENCES customers(id),
    seller_id VARCHAR(36) REFERENCES employees(id),
    -- Valores
    subtotal DECIMAL(15,2) DEFAULT 0,
    discount_amount DECIMAL(15,2) DEFAULT 0,
    discount_percent DECIMAL(5,2) DEFAULT 0,
    total_amount DECIMAL(15,2) DEFAULT 0,
    -- Pagamento
    payment_method VARCHAR(50),
    payment_status VARCHAR(20) DEFAULT 'pending',
    installments INTEGER DEFAULT 1,
    -- Status
    sale_status VARCHAR(20) DEFAULT 'completed',
    -- Observações
    notes TEXT,
    -- Metadados
    sale_metadata JSONB
);

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
    -- Identificação
    nome VARCHAR(255),
    descricao TEXT,
    numero_processo VARCHAR(100),
    customer_id VARCHAR(36),
    -- Datas
    data_calculo DATE,
    termo_final DATE,
    -- Índice de correção
    indice_correcao VARCHAR(50) DEFAULT 'ipca_e',
    -- Opções de correção monetária
    aplicar_variacoes_positivas BOOLEAN DEFAULT TRUE,
    usar_capitalizacao_simples BOOLEAN DEFAULT FALSE,
    manter_valor_nominal_inflacao_negativa BOOLEAN DEFAULT TRUE,
    -- Juros de mora
    tipo_juros_mora VARCHAR(50) DEFAULT 'taxa_fixa',
    percentual_juros_mora DECIMAL(10,4) DEFAULT 1.0,
    juros_mora_a_partir_de VARCHAR(50) DEFAULT 'vencimento',
    data_fixa_juros_mora DATE,
    aplicar_juros_mora_pro_rata BOOLEAN DEFAULT TRUE,
    calcular_juros_mora_sobre_compensatorios BOOLEAN DEFAULT FALSE,
    capitalizar_juros_mora_mensal BOOLEAN DEFAULT FALSE,
    -- Juros compensatórios
    tipo_juros_compensatorios VARCHAR(50),
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
    -- Auditoria
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
"""
