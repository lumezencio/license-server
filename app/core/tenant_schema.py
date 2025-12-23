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
# MAPEAMENTO DE PRODUTOS PARA SCHEMAS
# =====================================================
PRODUCT_SCHEMAS = {
    "enterprise": TENANT_SCHEMA_SQL,
    "tech-emp": TENANT_SCHEMA_SQL,
    "condotech": CONDOTECH_SCHEMA_SQL,
}

def get_schema_for_product(product_code: str) -> str:
    """Retorna o schema SQL apropriado para o produto especificado."""
    return PRODUCT_SCHEMAS.get(product_code.lower(), TENANT_SCHEMA_SQL)
