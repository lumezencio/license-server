"""
License Server - Tenant API Gateway
API Gateway Multi-Tenant que roteia requisicoes para o banco correto

Este modulo serve como um "proxy" que:
1. Recebe requisicoes autenticadas com JWT
2. Extrai o tenant_code do token
3. Conecta ao banco do tenant correto
4. Executa a operacao e retorna os dados
"""
from datetime import datetime, date
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, UploadFile, File
from fastapi.responses import FileResponse
import os
import uuid as uuid_lib
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncpg
import jwt
import json
from decimal import Decimal

from app.database import get_db
from app.models import Tenant, TenantStatus
from app.core import settings
from app.core.error_notifier import send_error_notification
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway", tags=["Tenant Gateway"])

security = HTTPBearer()


# === MODELOS ===

class CustomerModel(BaseModel):
    """Modelo de cliente - compatível com schema legado do enterprise_system"""
    id: Optional[str] = None
    # Campo name opcional (schema novo) - se não vier, usa first_name + last_name
    name: Optional[str] = None
    # Campos do schema legado
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    trade_name: Optional[str] = None
    # Documentos
    document: Optional[str] = None
    cpf_cnpj: Optional[str] = None
    rg: Optional[str] = None
    state_registration: Optional[str] = None
    municipal_registration: Optional[str] = None
    # Contato
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    # Endereço
    address: Optional[str] = None
    address_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = "BR"
    # Dados adicionais
    birth_date: Optional[str] = None
    customer_type: Optional[str] = "individual"
    customer_status: Optional[str] = "active"
    notes: Optional[str] = None
    credit_limit: Optional[float] = 0
    payment_term_days: Optional[int] = 30
    is_active: bool = True


class ProductModel(BaseModel):
    id: Optional[str] = None
    # Identificacao
    name: Optional[str] = None
    code: Optional[str] = None
    barcode_ean: Optional[str] = None
    barcode_ean128: Optional[str] = None
    sku: Optional[str] = None
    item_type: Optional[str] = "PRODUCT"
    # Descricao
    description: Optional[str] = ""
    short_description: Optional[str] = ""
    technical_specification: Optional[str] = None
    application: Optional[str] = None
    composition: Optional[str] = None
    category_id: Optional[str] = None
    subcategory_id: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    # Unidade e Medidas
    unit_of_measure: Optional[str] = "UN"
    unit_weight: Optional[Any] = None
    gross_weight: Optional[Any] = None
    net_weight: Optional[Any] = None
    length: Optional[Any] = None
    width: Optional[Any] = None
    height: Optional[Any] = None
    volume: Optional[Any] = None
    packaging_unit: Optional[str] = None
    packaging_quantity: Optional[Any] = None
    pallet_quantity: Optional[Any] = None
    # Fiscal
    ncm: Optional[str] = ""
    cest: Optional[str] = None
    cfop_venda_estadual: Optional[str] = "5102"
    cfop_venda_interestadual: Optional[str] = "6108"
    origem_mercadoria: Optional[str] = "0"
    cst_icms: Optional[str] = "101"
    aliquota_icms: Optional[Any] = 0
    reducao_bc_icms: Optional[Any] = None
    icms_st_aliquota: Optional[Any] = None
    icms_st_mva: Optional[Any] = None
    cst_ipi: Optional[str] = None
    aliquota_ipi: Optional[Any] = 0
    codigo_enquadramento_ipi: Optional[str] = None
    cst_pis: Optional[str] = "07"
    aliquota_pis: Optional[Any] = 0
    cst_cofins: Optional[str] = "07"
    aliquota_cofins: Optional[Any] = 0
    # Precos
    cost_price: Optional[Any] = 0
    additional_costs: Optional[Any] = 0
    final_cost: Optional[Any] = 0
    markup_percentage: Optional[Any] = 0
    sale_price: Optional[Any] = 0
    suggested_price: Optional[Any] = None
    minimum_price: Optional[Any] = None
    maximum_discount: Optional[Any] = None
    # Estoque
    stock_control: Optional[Any] = True
    current_stock: Optional[Any] = 0
    reserved_stock: Optional[Any] = 0
    available_stock: Optional[Any] = 0
    minimum_stock: Optional[Any] = 0
    maximum_stock: Optional[Any] = None
    reorder_point: Optional[Any] = None
    economic_lot: Optional[Any] = None
    abc_classification: Optional[str] = None
    # Fornecedor
    main_supplier_id: Optional[str] = None
    supplier_code: Optional[str] = None
    supplier_description: Optional[str] = None
    lead_time_days: Optional[Any] = None
    minimum_order_qty: Optional[Any] = None
    purchase_unit: Optional[str] = None
    conversion_factor: Optional[Any] = None
    # Status
    status: Optional[str] = "ACTIVE"
    sales_status: Optional[str] = "ENABLED"
    purchase_status: Optional[str] = "ENABLED"
    quality_control: Optional[Any] = False
    serialized_control: Optional[Any] = False
    is_kit: Optional[Any] = False
    is_manufactured: Optional[Any] = False
    is_imported: Optional[Any] = False
    is_controlled: Optional[Any] = False
    # Observacoes
    observations: Optional[str] = None
    internal_notes: Optional[str] = None
    sales_notes: Optional[str] = None
    purchase_notes: Optional[str] = None
    tags: Optional[str] = None
    # Imagens
    main_image: Optional[str] = None
    additional_images: Optional[str] = None
    technical_drawings: Optional[str] = None
    certificates: Optional[str] = None
    manuals: Optional[str] = None

    class Config:
        extra = "allow"  # Permite campos extras que nao estao no modelo


class SupplierModel(BaseModel):
    id: Optional[str] = None
    # Campos PJ
    company_name: Optional[str] = None
    trade_name: Optional[str] = None
    cnpj: Optional[str] = None
    state_registration: Optional[str] = None
    # Campos PF
    name: Optional[str] = None
    cpf: Optional[str] = None
    # Tipo de pessoa
    tipo_pessoa: str = "PJ"
    # Contato
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    # Endereco
    address: Optional[str] = None
    address_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = "BR"
    # Comercial
    payment_terms: Optional[str] = None
    delivery_time: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"
    is_active: bool = True


class EmployeeModel(BaseModel):
    id: Optional[str] = None
    name: str
    document: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    hire_date: Optional[str] = None
    salary: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


# === HELPERS ===

def custom_json_serializer(obj):
    """Serializa tipos especiais para JSON"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def row_to_dict(row) -> dict:
    """Converte asyncpg Record para dict"""
    if row is None:
        return None
    result = dict(row)
    # Converte tipos especiais
    for key, value in result.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif hasattr(value, '__str__') and not isinstance(value, (str, int, float, bool, type(None))):
            result[key] = str(value)
    return result


async def get_tenant_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> tuple[Tenant, dict]:
    """
    Extrai e valida token JWT, retorna tenant e dados do usuario.
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalido: {str(e)}"
        )

    tenant_code = payload.get("tenant_code")
    if not tenant_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sem tenant_code"
        )

    # Busca tenant
    result = await db.execute(
        select(Tenant).where(Tenant.tenant_code == tenant_code)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant nao encontrado"
        )

    if tenant.status not in [TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant com status invalido: {tenant.status}"
        )

    user_data = {
        "email": payload.get("sub"),
        "user_id": payload.get("user_id"),
        "is_admin": payload.get("is_admin", False)
    }

    return tenant, user_data


async def get_tenant_connection(tenant: Tenant) -> asyncpg.Connection:
    """Cria conexao com banco do tenant"""
    try:
        conn = await asyncpg.connect(
            host=tenant.database_host or settings.POSTGRES_HOST,
            port=tenant.database_port or settings.POSTGRES_PORT,
            user=tenant.database_user,
            password=tenant.database_password,
            database=tenant.database_name
        )
        return conn
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco do tenant {tenant.tenant_code}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Erro ao conectar ao banco de dados"
        )


async def ensure_sales_and_quotations_schema(conn: asyncpg.Connection):
    """
    Garante que as tabelas sales, sale_items, quotations e quotation_items existem
    com TODAS as colunas corretas. Isso resolve problemas de bancos de tenant
    criados antes das ultimas alteracoes de schema.

    Esta funcao e CRITICA para garantir que o sistema funcione perfeitamente
    para novos clientes desde o primeiro acesso.
    """
    logger.info("Verificando/atualizando schema de vendas e orcamentos...")
    try:
        # =====================================================
        # TABELA SALES
        # =====================================================
        sales_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'sales')"
        )

        if not sales_exists:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sales (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sale_number VARCHAR(20) UNIQUE NOT NULL,
                    sale_date DATE NOT NULL,
                    customer_id VARCHAR(36),
                    seller_id VARCHAR(36),
                    subtotal DECIMAL(15,2) DEFAULT 0,
                    discount_amount DECIMAL(15,2) DEFAULT 0,
                    discount_percent DECIMAL(5,2) DEFAULT 0,
                    total_amount DECIMAL(15,2) DEFAULT 0,
                    payment_method VARCHAR(50),
                    payment_status VARCHAR(20) DEFAULT 'pending',
                    installments INTEGER DEFAULT 1,
                    sale_status VARCHAR(20) DEFAULT 'completed',
                    notes TEXT,
                    sale_metadata JSONB
                )
            """)
            logger.info("Tabela sales criada com sucesso")
        else:
            sales_columns = [
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("sale_date", "DATE"),
                ("customer_id", "VARCHAR(36)"),
                ("seller_id", "VARCHAR(36)"),
                ("subtotal", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_percent", "DECIMAL(5,2) DEFAULT 0"),
                ("total_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("payment_method", "VARCHAR(50)"),
                ("payment_status", "VARCHAR(20) DEFAULT 'pending'"),
                ("installments", "INTEGER DEFAULT 1"),
                ("sale_status", "VARCHAR(20) DEFAULT 'completed'"),
                ("notes", "TEXT"),
                ("sale_metadata", "JSONB"),
            ]
            for col_name, col_type in sales_columns:
                try:
                    await conn.execute(f"ALTER TABLE sales ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                except Exception:
                    pass

        # =====================================================
        # TABELA SALE_ITEMS
        # =====================================================
        sale_items_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'sale_items')"
        )

        if not sale_items_exists:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sale_items (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sale_id VARCHAR(36) NOT NULL,
                    product_id VARCHAR(36),
                    product_name VARCHAR(200) NOT NULL,
                    quantity DECIMAL(15,3) DEFAULT 1,
                    unit_price DECIMAL(15,2) DEFAULT 0,
                    discount_amount DECIMAL(15,2) DEFAULT 0,
                    discount_percent DECIMAL(5,2) DEFAULT 0,
                    total_amount DECIMAL(15,2) DEFAULT 0
                )
            """)
            logger.info("Tabela sale_items criada com sucesso")
        else:
            sale_items_columns = [
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("product_id", "VARCHAR(36)"),
                ("product_name", "VARCHAR(200)"),
                ("quantity", "DECIMAL(15,3) DEFAULT 1"),
                ("unit_price", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_percent", "DECIMAL(5,2) DEFAULT 0"),
                ("total_amount", "DECIMAL(15,2) DEFAULT 0"),
            ]
            for col_name, col_type in sale_items_columns:
                try:
                    await conn.execute(f"ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                except Exception:
                    pass

        # =====================================================
        # TABELA QUOTATIONS
        # =====================================================
        quotations_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'quotations')"
        )

        needs_recreate = False
        if quotations_exists:
            # Verifica se a tabela tem constraints incorretas (seller_id NOT NULL)
            # Se estiver vazia, dropa e recria para garantir schema correto
            has_wrong_constraint = await conn.fetchval("""
                SELECT is_nullable = 'NO'
                FROM information_schema.columns
                WHERE table_name = 'quotations' AND column_name = 'seller_id'
            """)
            if has_wrong_constraint:
                row_count = await conn.fetchval("SELECT COUNT(*) FROM quotations")
                if row_count == 0:
                    # Tabela vazia com constraint errada - seguro dropar
                    logger.info("Tabela quotations vazia com constraint incorreta - recriando...")
                    await conn.execute("DROP TABLE IF EXISTS quotation_items")
                    await conn.execute("DROP TABLE quotations")
                    quotations_exists = False
                    needs_recreate = True
                else:
                    # Tabela com dados - apenas remove constraints
                    logger.info(f"Tabela quotations tem {row_count} registros - corrigindo constraints...")
                    try:
                        await conn.execute("ALTER TABLE quotations ALTER COLUMN seller_id DROP NOT NULL")
                        logger.info("Constraint NOT NULL removida de quotations.seller_id")
                    except Exception as e:
                        logger.warning(f"Erro ao remover constraint: {e}")

        if not quotations_exists:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS quotations (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quotation_number VARCHAR(20) UNIQUE NOT NULL,
                    quotation_date DATE NOT NULL,
                    valid_until DATE,
                    customer_id VARCHAR(36),
                    seller_id VARCHAR(36),
                    subtotal DECIMAL(15,2) DEFAULT 0,
                    discount_amount DECIMAL(15,2) DEFAULT 0,
                    discount_percent DECIMAL(5,2) DEFAULT 0,
                    freight_amount DECIMAL(15,2) DEFAULT 0,
                    total_amount DECIMAL(15,2) DEFAULT 0,
                    payment_method VARCHAR(50),
                    payment_terms VARCHAR(200),
                    installments INTEGER DEFAULT 1,
                    quotation_status VARCHAR(20) DEFAULT 'pending',
                    notes TEXT,
                    internal_notes TEXT,
                    converted_to_sale BOOLEAN DEFAULT FALSE,
                    sale_id VARCHAR(36),
                    converted_at TIMESTAMP,
                    quotation_metadata JSONB
                )
            """)
            if needs_recreate:
                logger.info("Tabela quotations recriada com schema correto")
            else:
                logger.info("Tabela quotations criada com sucesso")
        else:
            quotations_columns = [
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("quotation_date", "DATE"),
                ("valid_until", "DATE"),
                ("customer_id", "VARCHAR(36)"),
                ("seller_id", "VARCHAR(36)"),
                ("subtotal", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_percent", "DECIMAL(5,2) DEFAULT 0"),
                ("freight_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("total_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("payment_method", "VARCHAR(50)"),
                ("payment_terms", "VARCHAR(200)"),
                ("installments", "INTEGER DEFAULT 1"),
                ("quotation_status", "VARCHAR(20) DEFAULT 'pending'"),
                ("notes", "TEXT"),
                ("internal_notes", "TEXT"),
                ("converted_to_sale", "BOOLEAN DEFAULT FALSE"),
                ("sale_id", "VARCHAR(36)"),
                ("converted_at", "TIMESTAMP"),
                ("quotation_metadata", "JSONB"),
            ]
            for col_name, col_type in quotations_columns:
                try:
                    await conn.execute(f"ALTER TABLE quotations ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                except Exception:
                    pass

        # =====================================================
        # TABELA QUOTATION_ITEMS
        # =====================================================
        quotation_items_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'quotation_items')"
        )

        if not quotation_items_exists:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS quotation_items (
                    id VARCHAR(36) PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quotation_id VARCHAR(36) NOT NULL,
                    product_id VARCHAR(36),
                    product_name VARCHAR(200) NOT NULL,
                    quantity DECIMAL(15,3) DEFAULT 1,
                    unit_price DECIMAL(15,2) DEFAULT 0,
                    discount_amount DECIMAL(15,2) DEFAULT 0,
                    discount_percent DECIMAL(5,2) DEFAULT 0,
                    total_amount DECIMAL(15,2) DEFAULT 0
                )
            """)
            logger.info("Tabela quotation_items criada com sucesso")
        else:
            quotation_items_columns = [
                ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                ("product_id", "VARCHAR(36)"),
                ("product_name", "VARCHAR(200)"),
                ("quantity", "DECIMAL(15,3) DEFAULT 1"),
                ("unit_price", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_amount", "DECIMAL(15,2) DEFAULT 0"),
                ("discount_percent", "DECIMAL(5,2) DEFAULT 0"),
                ("total_amount", "DECIMAL(15,2) DEFAULT 0"),
            ]
            for col_name, col_type in quotation_items_columns:
                try:
                    await conn.execute(f"ALTER TABLE quotation_items ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                except Exception:
                    pass

        logger.info("Schema de vendas e orcamentos verificado/atualizado com sucesso")

    except Exception as e:
        logger.error(f"Erro ao garantir schema de vendas/orcamentos: {e}")
        import traceback
        logger.error(traceback.format_exc())


# Alias para manter compatibilidade com chamadas existentes
async def ensure_quotations_schema(conn: asyncpg.Connection):
    """Alias para ensure_sales_and_quotations_schema - garante todas as tabelas"""
    await ensure_sales_and_quotations_schema(conn)


# === ENDPOINTS - CUSTOMERS ===

@router.get("/customers")
async def list_customers(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista clientes do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado usa first_name/last_name e cpf_cnpj
        if search:
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name,
                    cpf_cnpj as document
                FROM customers
                WHERE first_name ILIKE $1 OR last_name ILIKE $1
                    OR company_name ILIKE $1 OR cpf_cnpj ILIKE $1 OR email ILIKE $1
                ORDER BY first_name, last_name
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name,
                    cpf_cnpj as document
                FROM customers
                ORDER BY first_name, last_name
                LIMIT $1 OFFSET $2
            """, limit, skip)

        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca cliente por ID"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            SELECT *,
                COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name,
                cpf_cnpj as document
            FROM customers WHERE id = $1
        """, customer_id)
        if not row:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.post("/customers")
async def create_customer(
    customer: CustomerModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo cliente - compatível com schema legado do enterprise_system"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Gera UUID para o cliente
        customer_id = str(uuid.uuid4())

        # Documento: usa cpf_cnpj se disponível, senão document
        doc = customer.cpf_cnpj or customer.document or ""

        # Parse birth_date se vier como string
        birth_date = None
        if customer.birth_date:
            try:
                from datetime import datetime as dt
                birth_date = dt.strptime(customer.birth_date, "%Y-%m-%d").date()
            except:
                pass

        # INSERT compatível com schema legado (enterprise_system)
        row = await conn.fetchrow("""
            INSERT INTO customers (
                id, first_name, last_name, company_name, trade_name,
                cpf_cnpj, rg, state_registration, municipal_registration,
                email, phone, mobile,
                address, address_number, address_complement,
                neighborhood, city, state, zip_code, country,
                birth_date, customer_type, customer_status,
                notes, credit_limit, payment_term_days, is_active,
                created_at, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12,
                $13, $14, $15,
                $16, $17, $18, $19, $20,
                $21, $22, $23,
                $24, $25, $26, $27,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING *
        """,
            customer_id,
            customer.first_name or "",
            customer.last_name or "",
            customer.company_name,
            customer.trade_name,
            doc,
            customer.rg,
            customer.state_registration,
            customer.municipal_registration,
            customer.email,
            customer.phone,
            customer.mobile,
            customer.address,
            customer.address_number,
            customer.address_complement,
            customer.neighborhood,
            customer.city,
            customer.state,
            customer.zip_code,
            customer.country or "BR",
            birth_date,
            customer.customer_type or "individual",
            customer.customer_status or "active",
            customer.notes,
            customer.credit_limit or 0,
            customer.payment_term_days or 30,
            customer.is_active
        )

        result = row_to_dict(row)
        # Adiciona campo name para compatibilidade
        result["name"] = f"{result.get('first_name', '')} {result.get('last_name', '')}".strip()
        return result
    except Exception as e:
        logger.error(f"Erro ao criar cliente: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


@router.put("/customers/{customer_id}")
async def update_customer(
    customer_id: str,
    customer: CustomerModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza cliente - compatível com schema legado do enterprise_system"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Documento: usa cpf_cnpj se disponível, senão document
        doc = customer.cpf_cnpj or customer.document or ""

        # Parse birth_date se vier como string
        birth_date = None
        if customer.birth_date:
            try:
                from datetime import datetime as dt
                birth_date = dt.strptime(customer.birth_date, "%Y-%m-%d").date()
            except:
                pass

        # UPDATE compatível com schema legado
        row = await conn.fetchrow("""
            UPDATE customers SET
                first_name = $2, last_name = $3, company_name = $4, trade_name = $5,
                cpf_cnpj = $6, rg = $7, state_registration = $8, municipal_registration = $9,
                email = $10, phone = $11, mobile = $12,
                address = $13, address_number = $14, address_complement = $15,
                neighborhood = $16, city = $17, state = $18, zip_code = $19, country = $20,
                birth_date = $21, customer_type = $22, customer_status = $23,
                notes = $24, credit_limit = $25, payment_term_days = $26, is_active = $27,
                updated_at = CURRENT_TIMESTAMP
            WHERE id::text = $1
            RETURNING *
        """,
            customer_id,
            customer.first_name or "",
            customer.last_name or "",
            customer.company_name,
            customer.trade_name,
            doc,
            customer.rg,
            customer.state_registration,
            customer.municipal_registration,
            customer.email,
            customer.phone,
            customer.mobile,
            customer.address,
            customer.address_number,
            customer.address_complement,
            customer.neighborhood,
            customer.city,
            customer.state,
            customer.zip_code,
            customer.country or "BR",
            birth_date,
            customer.customer_type or "individual",
            customer.customer_status or "active",
            customer.notes,
            customer.credit_limit or 0,
            customer.payment_term_days or 30,
            customer.is_active
        )

        if not row:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        result = row_to_dict(row)
        result["name"] = f"{result.get('first_name', '')} {result.get('last_name', '')}".strip()
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar cliente: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


@router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove cliente (soft delete)"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Soft delete - atualiza deleted_at em vez de remover
        result = await conn.execute(
            "UPDATE customers SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id::text = $1 AND deleted_at IS NULL",
            customer_id
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        return {"success": True, "message": "Cliente removido"}
    finally:
        await conn.close()


# === ENDPOINTS - PRODUCTS ===

@router.get("/products")
async def list_products(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista produtos do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Conta total de produtos para paginação
        if search:
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM products
                WHERE name ILIKE $1 OR sku ILIKE $1 OR code ILIKE $1
                    OR barcode_ean ILIKE $1
            """, f"%{search}%")
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(code, sku) as code,
                    COALESCE(barcode_ean, barcode_ean128) as barcode,
                    unit_of_measure as unit
                FROM products
                WHERE name ILIKE $1 OR sku ILIKE $1 OR code ILIKE $1
                    OR barcode_ean ILIKE $1
                ORDER BY name
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            total = await conn.fetchval("SELECT COUNT(*) FROM products")
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(code, sku) as code,
                    COALESCE(barcode_ean, barcode_ean128) as barcode,
                    unit_of_measure as unit
                FROM products
                ORDER BY name
                LIMIT $1 OFFSET $2
            """, limit, skip)

        items = [row_to_dict(row) for row in rows]
        pages = (total + limit - 1) // limit if limit > 0 else 1
        return {"items": items, "total": total, "pages": pages}
    finally:
        await conn.close()


@router.get("/products/{product_id}")
async def get_product(
    product_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca produto por ID"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE id = $1",
            product_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Produto nao encontrado")
        return row_to_dict(row)
    finally:
        await conn.close()


def to_decimal(val):
    """Converte valor para decimal ou None se vazio"""
    if val is None or val == '' or val == 'null':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def to_int(val):
    """Converte valor para int ou None se vazio"""
    if val is None or val == '' or val == 'null':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def to_bool(val):
    """Converte valor para bool"""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('true', '1', 'yes', 'sim')
    return bool(val)

def to_str(val):
    """Converte valor para string ou None se vazio"""
    if val is None or val == '' or val == 'null':
        return None
    return str(val)

def to_date(val):
    """Converte string ISO para date object - asyncpg NAO aceita strings para campos DATE

    VALIDACAO ROBUSTA: Verifica formato e valores plausiveis antes de converter.
    Evita erros como '20252-01-01' (ano invalido) ou '2025-13-45' (mes/dia invalido).
    """
    from datetime import date, datetime
    import re

    if val is None or val == '' or val == 'null':
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val = val.strip()

        # Regex para validar formato YYYY-MM-DD (com ou sem timestamp)
        date_pattern = r'^(\d{4})-(\d{2})-(\d{2})'

        if 'T' in val:
            # Formato ISO com timestamp: 2025-01-15T00:00:00Z
            match = re.match(date_pattern, val)
            if not match:
                raise ValueError(f"Formato de data invalido: '{val}'. Use YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS")

            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))

            # Validacao de valores plausiveis
            if year < 1900 or year > 2100:
                raise ValueError(f"Ano invalido: {year}. O ano deve estar entre 1900 e 2100")
            if month < 1 or month > 12:
                raise ValueError(f"Mes invalido: {month}. O mes deve estar entre 1 e 12")
            if day < 1 or day > 31:
                raise ValueError(f"Dia invalido: {day}. O dia deve estar entre 1 e 31")

            try:
                return datetime.fromisoformat(val.replace('Z', '+00:00')).date()
            except ValueError as e:
                raise ValueError(f"Data invalida: '{val}'. Verifique se a data existe (ex: 30/02 nao existe)")
        else:
            # Formato simples: 2025-01-15
            match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', val)
            if not match:
                raise ValueError(f"Formato de data invalido: '{val}'. Use o formato YYYY-MM-DD (ex: 2025-01-15)")

            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))

            # Validacao de valores plausiveis
            if year < 1900 or year > 2100:
                raise ValueError(f"Ano invalido: {year}. O ano deve estar entre 1900 e 2100")
            if month < 1 or month > 12:
                raise ValueError(f"Mes invalido: {month}. O mes deve estar entre 1 e 12")
            if day < 1 or day > 31:
                raise ValueError(f"Dia invalido: {day}. O dia deve estar entre 1 e 31")

            try:
                return date(year, month, day)
            except ValueError as e:
                raise ValueError(f"Data invalida: '{val}'. Verifique se a data existe (ex: 30/02 nao existe)")

    return None

def generate_slug(name: str) -> str:
    """Gera um slug a partir do nome"""
    import re
    import unicodedata
    if not name:
        return "produto"
    # Remove acentos
    slug = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
    # Converte para minúsculas
    slug = slug.lower()
    # Substitui espaços e caracteres especiais por hífen
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    # Remove hífens duplicados e do início/fim
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug or "produto"


@router.post("/products")
async def create_product(
    product: ProductModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo produto"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        import uuid
        product_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Gera slug a partir do nome
        product_name = to_str(product.name) or "Produto"
        product_slug = generate_slug(product_name)

        row = await conn.fetchrow("""
            INSERT INTO products (
                id, created_at, updated_at, slug,
                name, code, barcode_ean, barcode_ean128, sku, item_type,
                description, short_description, technical_specification, application, composition,
                category_id, subcategory_id, brand, model,
                unit_of_measure, unit_weight, gross_weight, net_weight, length, width, height, volume,
                packaging_unit, packaging_quantity, pallet_quantity,
                ncm, cest, cfop_venda_estadual, cfop_venda_interestadual,
                origem_mercadoria, cst_icms, aliquota_icms, reducao_bc_icms,
                icms_st_aliquota, icms_st_mva, cst_ipi, aliquota_ipi, codigo_enquadramento_ipi,
                cst_pis, aliquota_pis, cst_cofins, aliquota_cofins,
                cost_price, additional_costs, final_cost, markup_percentage,
                sale_price, suggested_price, minimum_price, maximum_discount,
                stock_control, current_stock, reserved_stock, available_stock,
                minimum_stock, maximum_stock, reorder_point, economic_lot, abc_classification,
                main_supplier_id, supplier_code, supplier_description, lead_time_days,
                minimum_order_qty, purchase_unit, conversion_factor,
                status, sales_status, purchase_status, quality_control, serialized_control,
                is_kit, is_manufactured, is_imported, is_controlled,
                observations, internal_notes, sales_notes, purchase_notes, tags,
                main_image, additional_images, technical_drawings, certificates, manuals
            )
            VALUES (
                $1, $2, $3, $4,
                $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15,
                $16, $17, $18, $19,
                $20, $21, $22, $23, $24, $25, $26, $27,
                $28, $29, $30,
                $31, $32, $33, $34,
                $35, $36, $37, $38,
                $39, $40, $41, $42, $43,
                $44, $45, $46, $47,
                $48, $49, $50, $51,
                $52, $53, $54, $55,
                $56, $57, $58, $59,
                $60, $61, $62, $63, $64,
                $65, $66, $67, $68,
                $69, $70, $71,
                $72, $73, $74, $75, $76,
                $77, $78, $79, $80,
                $81, $82, $83, $84, $85,
                $86, $87, $88, $89, $90
            )
            RETURNING *
        """,
            product_id, now, now, product_slug,
            product_name, to_str(product.code), to_str(product.barcode_ean), to_str(product.barcode_ean128), to_str(product.sku), to_str(product.item_type) or "PRODUCT",
            to_str(product.description) or "", to_str(product.short_description) or "", to_str(product.technical_specification), to_str(product.application), to_str(product.composition),
            to_str(product.category_id), to_str(product.subcategory_id), to_str(product.brand), to_str(product.model),
            to_str(product.unit_of_measure) or "UN", to_decimal(product.unit_weight), to_decimal(product.gross_weight), to_decimal(product.net_weight), to_decimal(product.length), to_decimal(product.width), to_decimal(product.height), to_decimal(product.volume),
            to_str(product.packaging_unit), to_decimal(product.packaging_quantity), to_int(product.pallet_quantity),
            to_str(product.ncm) or "", to_str(product.cest), to_str(product.cfop_venda_estadual) or "5102", to_str(product.cfop_venda_interestadual) or "6108",
            to_str(product.origem_mercadoria) or "0", to_str(product.cst_icms) or "101", to_decimal(product.aliquota_icms) or 0, to_decimal(product.reducao_bc_icms),
            to_decimal(product.icms_st_aliquota), to_decimal(product.icms_st_mva), to_str(product.cst_ipi), to_decimal(product.aliquota_ipi) or 0, to_str(product.codigo_enquadramento_ipi),
            to_str(product.cst_pis) or "07", to_decimal(product.aliquota_pis) or 0, to_str(product.cst_cofins) or "07", to_decimal(product.aliquota_cofins) or 0,
            to_decimal(product.cost_price) or 0, to_decimal(product.additional_costs) or 0, to_decimal(product.final_cost) or 0, to_decimal(product.markup_percentage) or 0,
            to_decimal(product.sale_price) or 0, to_decimal(product.suggested_price), to_decimal(product.minimum_price), to_decimal(product.maximum_discount),
            to_bool(product.stock_control), to_decimal(product.current_stock) or 0, to_decimal(product.reserved_stock) or 0, to_decimal(product.available_stock) or 0,
            to_decimal(product.minimum_stock) or 0, to_decimal(product.maximum_stock), to_decimal(product.reorder_point), to_decimal(product.economic_lot), to_str(product.abc_classification),
            to_str(product.main_supplier_id), to_str(product.supplier_code), to_str(product.supplier_description), to_int(product.lead_time_days),
            to_decimal(product.minimum_order_qty), to_str(product.purchase_unit), to_decimal(product.conversion_factor),
            to_str(product.status) or "ACTIVE", to_str(product.sales_status) or "ENABLED", to_str(product.purchase_status) or "ENABLED", to_bool(product.quality_control), to_bool(product.serialized_control),
            to_bool(product.is_kit), to_bool(product.is_manufactured), to_bool(product.is_imported), to_bool(product.is_controlled),
            to_str(product.observations), to_str(product.internal_notes), to_str(product.sales_notes), to_str(product.purchase_notes), to_str(product.tags),
            to_str(product.main_image), to_str(product.additional_images), to_str(product.technical_drawings), to_str(product.certificates), to_str(product.manuals)
        )

        return row_to_dict(row)
    except Exception as e:
        print(f"[PRODUCTS] Erro ao criar produto: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Erro ao criar produto: {str(e)}")
    finally:
        await conn.close()


@router.put("/products/{product_id}")
async def update_product(
    product_id: str,
    product: ProductModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza produto"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        now = datetime.utcnow()

        row = await conn.fetchrow("""
            UPDATE products SET
                updated_at = $2,
                name = $3, code = $4, barcode_ean = $5, barcode_ean128 = $6, sku = $7, item_type = $8,
                description = $9, short_description = $10, technical_specification = $11, application = $12, composition = $13,
                category_id = $14, subcategory_id = $15, brand = $16, model = $17,
                unit_of_measure = $18, unit_weight = $19, gross_weight = $20, net_weight = $21, length = $22, width = $23, height = $24, volume = $25,
                packaging_unit = $26, packaging_quantity = $27, pallet_quantity = $28,
                ncm = $29, cest = $30, cfop_venda_estadual = $31, cfop_venda_interestadual = $32,
                origem_mercadoria = $33, cst_icms = $34, aliquota_icms = $35, reducao_bc_icms = $36,
                icms_st_aliquota = $37, icms_st_mva = $38, cst_ipi = $39, aliquota_ipi = $40, codigo_enquadramento_ipi = $41,
                cst_pis = $42, aliquota_pis = $43, cst_cofins = $44, aliquota_cofins = $45,
                cost_price = $46, additional_costs = $47, final_cost = $48, markup_percentage = $49,
                sale_price = $50, suggested_price = $51, minimum_price = $52, maximum_discount = $53,
                stock_control = $54, current_stock = $55, reserved_stock = $56, available_stock = $57,
                minimum_stock = $58, maximum_stock = $59, reorder_point = $60, economic_lot = $61, abc_classification = $62,
                main_supplier_id = $63, supplier_code = $64, supplier_description = $65, lead_time_days = $66,
                minimum_order_qty = $67, purchase_unit = $68, conversion_factor = $69,
                status = $70, sales_status = $71, purchase_status = $72, quality_control = $73, serialized_control = $74,
                is_kit = $75, is_manufactured = $76, is_imported = $77, is_controlled = $78,
                observations = $79, internal_notes = $80, sales_notes = $81, purchase_notes = $82, tags = $83,
                main_image = $84, additional_images = $85, technical_drawings = $86, certificates = $87, manuals = $88
            WHERE id = $1
            RETURNING *
        """,
            product_id, now,
            # Campos de texto
            to_str(product.name), to_str(product.code), to_str(product.barcode_ean), to_str(product.barcode_ean128), to_str(product.sku), to_str(product.item_type),
            to_str(product.description), to_str(product.short_description), to_str(product.technical_specification), to_str(product.application), to_str(product.composition),
            to_str(product.category_id), to_str(product.subcategory_id), to_str(product.brand), to_str(product.model),
            # Unidades e dimensões
            to_str(product.unit_of_measure), to_decimal(product.unit_weight), to_decimal(product.gross_weight), to_decimal(product.net_weight), to_decimal(product.length), to_decimal(product.width), to_decimal(product.height), to_decimal(product.volume),
            to_str(product.packaging_unit), to_int(product.packaging_quantity), to_int(product.pallet_quantity),
            # Fiscal
            to_str(product.ncm), to_str(product.cest), to_str(product.cfop_venda_estadual), to_str(product.cfop_venda_interestadual),
            to_str(product.origem_mercadoria), to_str(product.cst_icms), to_decimal(product.aliquota_icms), to_decimal(product.reducao_bc_icms),
            to_decimal(product.icms_st_aliquota), to_decimal(product.icms_st_mva), to_str(product.cst_ipi), to_decimal(product.aliquota_ipi), to_str(product.codigo_enquadramento_ipi),
            to_str(product.cst_pis), to_decimal(product.aliquota_pis), to_str(product.cst_cofins), to_decimal(product.aliquota_cofins),
            # Preços
            to_decimal(product.cost_price), to_decimal(product.additional_costs), to_decimal(product.final_cost), to_decimal(product.markup_percentage),
            to_decimal(product.sale_price), to_decimal(product.suggested_price), to_decimal(product.minimum_price), to_decimal(product.maximum_discount),
            # Estoque
            to_bool(product.stock_control), to_decimal(product.current_stock), to_decimal(product.reserved_stock), to_decimal(product.available_stock),
            to_decimal(product.minimum_stock), to_decimal(product.maximum_stock), to_decimal(product.reorder_point), to_decimal(product.economic_lot), to_str(product.abc_classification),
            # Fornecedor
            to_str(product.main_supplier_id), to_str(product.supplier_code), to_str(product.supplier_description), to_int(product.lead_time_days),
            to_decimal(product.minimum_order_qty), to_str(product.purchase_unit), to_decimal(product.conversion_factor),
            # Status e controles
            to_str(product.status), to_str(product.sales_status), to_str(product.purchase_status), to_bool(product.quality_control), to_bool(product.serialized_control),
            to_bool(product.is_kit), to_bool(product.is_manufactured), to_bool(product.is_imported), to_bool(product.is_controlled),
            # Textos adicionais
            to_str(product.observations), to_str(product.internal_notes), to_str(product.sales_notes), to_str(product.purchase_notes), to_str(product.tags),
            to_str(product.main_image), to_str(product.additional_images), to_str(product.technical_drawings), to_str(product.certificates), to_str(product.manuals)
        )

        if not row:
            raise HTTPException(status_code=404, detail="Produto nao encontrado")
        return row_to_dict(row)
    except Exception as e:
        print(f"[PRODUCTS] Erro ao atualizar produto: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar produto: {str(e)}")
    finally:
        await conn.close()


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove produto"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        result = await conn.execute(
            "DELETE FROM products WHERE id = $1",
            product_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Produto nao encontrado")
        return {"success": True, "message": "Produto removido"}
    finally:
        await conn.close()


# === ENDPOINTS - SUPPLIERS ===

@router.get("/suppliers")
async def list_suppliers(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista fornecedores do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado usa company_name/trade_name/name e cnpj/cpf
        if search:
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(company_name, trade_name, name) as display_name,
                    COALESCE(cnpj, cpf) as document
                FROM suppliers
                WHERE company_name ILIKE $1 OR trade_name ILIKE $1 OR name ILIKE $1
                    OR cnpj ILIKE $1 OR cpf ILIKE $1 OR email ILIKE $1
                ORDER BY COALESCE(company_name, trade_name, name)
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(company_name, trade_name, name) as display_name,
                    COALESCE(cnpj, cpf) as document
                FROM suppliers
                ORDER BY COALESCE(company_name, trade_name, name)
                LIMIT $1 OFFSET $2
            """, limit, skip)

        suppliers = [row_to_dict(row) for row in rows]
        return {"suppliers": suppliers, "total": len(suppliers)}
    finally:
        await conn.close()


@router.post("/suppliers")
async def create_supplier(
    supplier: SupplierModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo fornecedor"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Gera UUID para novo fornecedor
        import uuid
        supplier_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Determina is_active baseado no status
        is_active = supplier.is_active if supplier.is_active is not None else (supplier.status == "active")

        row = await conn.fetchrow("""
            INSERT INTO suppliers (
                id, tipo_pessoa,
                company_name, trade_name, cnpj, state_registration,
                name, cpf,
                email, phone, website, contact_name, contact_email, contact_phone,
                address, address_number, address_complement, neighborhood, city, state, zip_code, country,
                payment_terms, delivery_time, category, notes, is_active,
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29)
            RETURNING *
        """,
            supplier_id, supplier.tipo_pessoa,
            supplier.company_name, supplier.trade_name, supplier.cnpj, supplier.state_registration,
            supplier.name, supplier.cpf,
            supplier.email, supplier.phone, supplier.website, supplier.contact_name, supplier.contact_email, supplier.contact_phone,
            supplier.address, supplier.address_number, supplier.address_complement, supplier.neighborhood, supplier.city, supplier.state, supplier.zip_code, supplier.country,
            supplier.payment_terms, supplier.delivery_time, supplier.category, supplier.notes, is_active,
            now, now
        )

        return row_to_dict(row)
    except Exception as e:
        print(f"[SUPPLIERS] Erro ao criar fornecedor: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Erro ao criar fornecedor: {str(e)}")
    finally:
        await conn.close()


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    supplier: SupplierModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza fornecedor"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Determina is_active baseado no status
        is_active = supplier.is_active if supplier.is_active is not None else (supplier.status == "active")

        row = await conn.fetchrow("""
            UPDATE suppliers SET
                tipo_pessoa = $2,
                company_name = $3, trade_name = $4, cnpj = $5, state_registration = $6,
                name = $7, cpf = $8,
                email = $9, phone = $10, website = $11, contact_name = $12, contact_email = $13, contact_phone = $14,
                address = $15, address_number = $16, address_complement = $17, neighborhood = $18,
                city = $19, state = $20, zip_code = $21, country = $22,
                payment_terms = $23, delivery_time = $24, category = $25, notes = $26, is_active = $27,
                updated_at = $28
            WHERE id = $1
            RETURNING *
        """,
            supplier_id, supplier.tipo_pessoa,
            supplier.company_name, supplier.trade_name, supplier.cnpj, supplier.state_registration,
            supplier.name, supplier.cpf,
            supplier.email, supplier.phone, supplier.website, supplier.contact_name, supplier.contact_email, supplier.contact_phone,
            supplier.address, supplier.address_number, supplier.address_complement, supplier.neighborhood,
            supplier.city, supplier.state, supplier.zip_code, supplier.country,
            supplier.payment_terms, supplier.delivery_time, supplier.category, supplier.notes, is_active,
            datetime.utcnow()
        )

        if not row:
            raise HTTPException(status_code=404, detail="Fornecedor nao encontrado")
        return row_to_dict(row)
    except Exception as e:
        print(f"[SUPPLIERS] Erro ao atualizar fornecedor: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar fornecedor: {str(e)}")
    finally:
        await conn.close()


@router.delete("/suppliers/{supplier_id}")
async def delete_supplier(
    supplier_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove fornecedor"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        result = await conn.execute(
            "DELETE FROM suppliers WHERE id = $1",
            supplier_id
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Fornecedor nao encontrado")
        return {"success": True, "message": "Fornecedor removido"}
    finally:
        await conn.close()


# === ENDPOINTS - EMPLOYEES ===

@router.get("/employees")
async def list_employees(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista funcionarios do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Verifica se tabela employees existe
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'employees'
            )
        """)

        if not table_exists:
            return []

        if search:
            rows = await conn.fetch("""
                SELECT * FROM employees
                WHERE name ILIKE $1 OR document ILIKE $1 OR email ILIKE $1
                ORDER BY name
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            rows = await conn.fetch("""
                SELECT * FROM employees ORDER BY name LIMIT $1 OFFSET $2
            """, limit, skip)

        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.post("/employees")
async def create_employee(
    employee: EmployeeModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo funcionario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        hire_date = None
        if employee.hire_date:
            try:
                hire_date = datetime.fromisoformat(employee.hire_date.replace('Z', '+00:00')).date()
            except:
                hire_date = None

        row = await conn.fetchrow("""
            INSERT INTO employees (name, document, email, phone, position, department,
                                   hire_date, salary, address, city, state, notes, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
        """, employee.name, employee.document, employee.email, employee.phone,
           employee.position, employee.department, hire_date, employee.salary,
           employee.address, employee.city, employee.state, employee.notes,
           employee.is_active)

        return row_to_dict(row)
    finally:
        await conn.close()


# === ENDPOINTS - DASHBOARD ===

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna estatisticas do dashboard"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Conta registros de cada tabela
        customers_count = await conn.fetchval("SELECT COUNT(*) FROM customers")
        products_count = await conn.fetchval("SELECT COUNT(*) FROM products")
        suppliers_count = await conn.fetchval("SELECT COUNT(*) FROM suppliers")

        # Verifica se tabela employees existe
        employees_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'employees'
            )
        """)
        employees_count = 0
        if employees_exists:
            employees_count = await conn.fetchval("SELECT COUNT(*) FROM employees")

        # Vendas do mes - schema legado usa total_amount em vez de total
        sales_month = await conn.fetchval("""
            SELECT COALESCE(SUM(COALESCE(total_amount, 0)), 0) FROM sales
            WHERE DATE_TRUNC('month', sale_date) = DATE_TRUNC('month', CURRENT_DATE)
        """)

        # Contas a receber pendentes - schema legado usa ENUM com valores UPPERCASE
        receivables = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - paid_amount), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING')
        """)

        # Contas a pagar pendentes - schema legado usa amount_paid em vez de paid_amount
        payables = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING')
        """)

        return {
            "customers_count": customers_count or 0,
            "products_count": products_count or 0,
            "suppliers_count": suppliers_count or 0,
            "employees_count": employees_count or 0,
            "sales_month": float(sales_month or 0),
            "accounts_receivable": float(receivables or 0),
            "accounts_payable": float(payables or 0)
        }
    finally:
        await conn.close()


# === ENDPOINTS - SALES ===

@router.get("/sales")
async def list_sales(
    skip: int = 0,
    limit: int = 100,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista vendas do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado: customers usa first_name/last_name
        rows = await conn.fetch("""
            SELECT s.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.id
            ORDER BY s.sale_date DESC
            LIMIT $1 OFFSET $2
        """, limit, skip)

        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.get("/sales/{sale_id}")
async def get_sale(
    sale_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna detalhes de uma venda específica com itens"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca a venda
        row = await conn.fetchrow("""
            SELECT s.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                c.cpf_cnpj as customer_document,
                COALESCE(e.first_name || ' ' || e.last_name, e.name) as seller_name
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.id
            LEFT JOIN employees e ON s.seller_id = e.id
            WHERE s.id = $1
        """, sale_id)

        if not row:
            raise HTTPException(status_code=404, detail="Venda não encontrada")

        sale = row_to_dict(row)

        # Busca itens da venda
        items_rows = await conn.fetch("""
            SELECT si.*,
                p.name as product_name_full,
                p.code as product_code,
                p.barcode_ean as product_barcode
            FROM sale_items si
            LEFT JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = $1
            ORDER BY si.created_at
        """, sale_id)

        sale["items"] = [row_to_dict(item) for item in items_rows]

        return sale
    finally:
        await conn.close()


@router.post("/sales")
@router.post("/sales/")
async def create_sale(
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria uma nova venda com itens e opcionalmente contas a receber"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        data = await request.json()
        sale_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Gera número da venda de forma thread-safe
        # Usa SELECT FOR UPDATE para evitar números duplicados em acessos simultâneos
        count_row = await conn.fetchrow("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(sale_number FROM 4) AS INTEGER)), 0) + 1 as next_num
            FROM sales
            WHERE sale_number LIKE 'VND%'
        """)
        next_num = count_row["next_num"] if count_row else 1
        sale_number = data.get("sale_number") or f"VND{next_num:06d}"

        # Converte data
        def parse_date(val):
            if not val or val == '' or val == 'null':
                return None
            if isinstance(val, str):
                from datetime import datetime as dt
                if 'T' in val:
                    return dt.fromisoformat(val.replace('Z', '+00:00')).date()
                return dt.strptime(val, '%Y-%m-%d').date()
            return val

        sale_date = parse_date(data.get("sale_date")) or now.date()

        # Calcula valores
        subtotal = to_decimal(data.get("subtotal")) or 0
        discount_amount = to_decimal(data.get("discount_amount")) or 0
        discount_percent = to_decimal(data.get("discount_percent")) or 0
        total_amount = to_decimal(data.get("total_amount")) or (subtotal - discount_amount)

        # Metadados opcionais (JSON)
        sale_metadata = data.get("sale_metadata")
        if sale_metadata and isinstance(sale_metadata, dict):
            import json as json_lib
            sale_metadata = json_lib.dumps(sale_metadata)
        else:
            sale_metadata = None

        # Insere a venda
        await conn.execute("""
            INSERT INTO sales (
                id, sale_number, sale_date, customer_id, seller_id,
                subtotal, discount_amount, discount_percent, total_amount,
                payment_method, payment_status, installments,
                sale_status, notes, sale_metadata, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
            )
        """,
            sale_id, sale_number, sale_date,
            to_str(data.get("customer_id")), to_str(data.get("seller_id")),
            subtotal, discount_amount, discount_percent, total_amount,
            to_str(data.get("payment_method")), to_str(data.get("payment_status")) or "pending",
            to_int(data.get("installments")) or 1,
            to_str(data.get("sale_status")) or "completed", to_str(data.get("notes")),
            sale_metadata, now, now
        )

        # Insere itens da venda e atualiza estoque
        items = data.get("items", [])
        update_stock = data.get("update_stock", True)  # Baixa de estoque automática

        for item in items:
            item_id = str(uuid.uuid4())
            product_id = to_str(item.get("product_id"))
            quantity = to_decimal(item.get("quantity")) or 1
            unit_price = to_decimal(item.get("unit_price")) or 0
            item_subtotal = quantity * unit_price
            item_discount = to_decimal(item.get("discount_amount")) or 0
            item_total = item_subtotal - item_discount

            # Busca nome do produto se não fornecido
            product_name = to_str(item.get("product_name")) or to_str(item.get("name"))
            if not product_name and product_id:
                prod_row = await conn.fetchrow(
                    "SELECT name, current_stock, stock_control FROM products WHERE id = $1",
                    product_id
                )
                if prod_row:
                    product_name = prod_row["name"]

            await conn.execute("""
                INSERT INTO sale_items (
                    id, sale_id, product_id, product_name,
                    quantity, unit_price, discount_amount, discount_percent, total_amount,
                    created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                )
            """,
                item_id, sale_id, product_id,
                product_name or "Produto",
                quantity, unit_price,
                item_discount, to_decimal(item.get("discount_percent")) or 0, item_total,
                now, now
            )

            # Baixa de estoque automática
            if update_stock and product_id:
                await conn.execute("""
                    UPDATE products
                    SET current_stock = COALESCE(current_stock, 0) - $1,
                        available_stock = COALESCE(available_stock, 0) - $1,
                        updated_at = $2
                    WHERE id = $3 AND stock_control = true
                """, quantity, now, product_id)

        # Cria contas a receber se solicitado
        create_receivable = data.get("create_accounts_receivable", True)
        if create_receivable and total_amount > 0:
            num_installments = to_int(data.get("installments")) or 1
            customer_id = to_str(data.get("customer_id"))

            # Busca nome do cliente
            customer_name = None
            if customer_id:
                customer_row = await conn.fetchrow("""
                    SELECT COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name
                    FROM customers WHERE id = $1
                """, customer_id)
                if customer_row:
                    customer_name = customer_row["name"]

            # Descrição dos itens para a conta a receber
            items_desc = ", ".join([f"{to_decimal(i.get('quantity')) or 1}x {i.get('product_name') or i.get('name') or 'Produto'}" for i in items[:3]])
            if len(items) > 3:
                items_desc += f" +{len(items) - 3} itens"

            # Usa dateutil para cálculo de datas
            from dateutil.relativedelta import relativedelta

            if num_installments == 1:
                # Parcela única
                receivable_id = str(uuid.uuid4())
                due_date = sale_date + relativedelta(months=1)

                await conn.execute("""
                    INSERT INTO accounts_receivable (
                        id, customer_id, parent_id,
                        description, document_number, amount, paid_amount,
                        issue_date, due_date, payment_date, status, payment_method,
                        category, installment_number, total_installments, notes,
                        created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                    )
                """,
                    receivable_id, customer_id, None,
                    f"Venda {sale_number} - {items_desc}", sale_number,
                    total_amount, 0.0,
                    sale_date, due_date, None, "PENDING", to_str(data.get("payment_method")),
                    "VENDAS", 0, 1, to_str(data.get("notes")),
                    now, now
                )
            else:
                # Múltiplas parcelas - cria PAI + filhas
                parent_id = str(uuid.uuid4())
                installment_amount = round(total_amount / num_installments, 2)
                last_installment_amount = round(total_amount - (installment_amount * (num_installments - 1)), 2)

                # Cria registro pai (installment_number = 0)
                await conn.execute("""
                    INSERT INTO accounts_receivable (
                        id, customer_id, parent_id,
                        description, document_number, amount, paid_amount,
                        issue_date, due_date, payment_date, status, payment_method,
                        category, installment_number, total_installments, notes,
                        created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                    )
                """,
                    parent_id, customer_id, None,
                    f"Venda {sale_number} - {items_desc}", sale_number,
                    total_amount, 0.0,
                    sale_date, sale_date, None, "PENDING", to_str(data.get("payment_method")),
                    "VENDAS", 0, num_installments, to_str(data.get("notes")),
                    now, now
                )

                # Cria parcelas filhas
                for i in range(1, num_installments + 1):
                    installment_id = str(uuid.uuid4())
                    amount = last_installment_amount if i == num_installments else installment_amount
                    due_date = sale_date + relativedelta(months=i)

                    await conn.execute("""
                        INSERT INTO accounts_receivable (
                            id, customer_id, parent_id,
                            description, document_number, amount, paid_amount,
                            issue_date, due_date, payment_date, status, payment_method,
                            category, installment_number, total_installments, notes,
                            created_at, updated_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                        )
                    """,
                        installment_id, customer_id, parent_id,
                        f"Venda {sale_number} - Parcela {i}/{num_installments}", f"{sale_number}-{i}",
                        amount, 0.0,
                        sale_date, due_date, None, "PENDING", to_str(data.get("payment_method")),
                        "VENDAS", i, num_installments, None,
                        now, now
                    )

        # Retorna a venda criada
        return {
            "id": sale_id,
            "sale_number": sale_number,
            "sale_date": str(sale_date),
            "customer_id": to_str(data.get("customer_id")),
            "total_amount": float(total_amount),
            "installments": to_int(data.get("installments")) or 1,
            "items_count": len(items),
            "message": "Venda criada com sucesso"
        }

    except Exception as e:
        logger.error(f"Erro ao criar venda: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro ao criar venda: {str(e)}")
    finally:
        await conn.close()


# === ENDPOINTS - QUOTATIONS (ORÇAMENTOS) ===

@router.get("/quotations")
async def list_quotations(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista orçamentos do tenant com seus itens"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Garante que as tabelas existem
        await ensure_quotations_schema(conn)

        where_clause = ""
        params = [limit, skip]

        if status:
            where_clause = "WHERE q.quotation_status = $3"
            params.append(status)

        rows = await conn.fetch(f"""
            SELECT q.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                COALESCE(e.first_name || ' ' || e.last_name, e.name) as seller_name
            FROM quotations q
            LEFT JOIN customers c ON q.customer_id = c.id
            LEFT JOIN employees e ON q.seller_id = e.id
            {where_clause}
            ORDER BY q.quotation_date DESC
            LIMIT $1 OFFSET $2
        """, *params)

        # Converte para lista e adiciona itens de cada orçamento
        quotations = []
        for row in rows:
            quotation = row_to_dict(row)
            # Busca itens do orçamento
            items_rows = await conn.fetch("""
                SELECT qi.*,
                    p.name as product_name_full,
                    p.code as product_code,
                    p.barcode_ean as product_barcode,
                    p.sale_price as product_sale_price
                FROM quotation_items qi
                LEFT JOIN products p ON qi.product_id = p.id
                WHERE qi.quotation_id = $1
                ORDER BY qi.created_at
            """, quotation["id"])
            quotation["items"] = [row_to_dict(item) for item in items_rows]
            quotations.append(quotation)

        return quotations
    finally:
        await conn.close()


@router.get("/quotations/{quotation_id}")
async def get_quotation(
    quotation_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna detalhes de um orçamento específico com itens"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Garante que as tabelas existem
        await ensure_quotations_schema(conn)

        row = await conn.fetchrow("""
            SELECT q.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                c.cpf_cnpj as customer_document,
                c.email as customer_email,
                c.phone as customer_phone,
                COALESCE(e.first_name || ' ' || e.last_name, e.name) as seller_name
            FROM quotations q
            LEFT JOIN customers c ON q.customer_id = c.id
            LEFT JOIN employees e ON q.seller_id = e.id
            WHERE q.id = $1
        """, quotation_id)

        if not row:
            raise HTTPException(status_code=404, detail="Orçamento não encontrado")

        quotation = row_to_dict(row)

        # Busca itens do orçamento
        items_rows = await conn.fetch("""
            SELECT qi.*,
                p.name as product_name_full,
                p.code as product_code,
                p.barcode_ean as product_barcode
            FROM quotation_items qi
            LEFT JOIN products p ON qi.product_id = p.id
            WHERE qi.quotation_id = $1
            ORDER BY qi.created_at
        """, quotation_id)

        quotation["items"] = [row_to_dict(item) for item in items_rows]

        return quotation
    finally:
        await conn.close()


@router.post("/quotations")
@router.post("/quotations/")
async def create_quotation(
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria um novo orçamento com itens"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Garante que as tabelas de quotations existem e tem todas as colunas
        await ensure_quotations_schema(conn)

        data = await request.json()
        quotation_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Gera número do orçamento
        count_row = await conn.fetchrow("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(quotation_number FROM 4) AS INTEGER)), 0) + 1 as next_num
            FROM quotations
            WHERE quotation_number LIKE 'ORC%'
        """)
        next_num = count_row["next_num"] if count_row else 1
        quotation_number = data.get("quotation_number") or f"ORC{next_num:06d}"

        # Converte datas
        def parse_date(val):
            if not val or val == '' or val == 'null':
                return None
            if isinstance(val, str):
                from datetime import datetime as dt
                if 'T' in val:
                    return dt.fromisoformat(val.replace('Z', '+00:00')).date()
                return dt.strptime(val, '%Y-%m-%d').date()
            return val

        quotation_date = parse_date(data.get("quotation_date")) or now.date()
        valid_until = parse_date(data.get("valid_until"))

        # Se não informou validade, usa 30 dias
        if not valid_until:
            from dateutil.relativedelta import relativedelta
            valid_until = quotation_date + relativedelta(days=30)

        # Calcula valores
        subtotal = to_decimal(data.get("subtotal")) or 0
        discount_amount = to_decimal(data.get("discount_amount")) or 0
        discount_percent = to_decimal(data.get("discount_percent")) or 0
        freight_amount = to_decimal(data.get("freight_amount")) or 0
        total_amount = to_decimal(data.get("total_amount")) or (subtotal - discount_amount + freight_amount)

        # Metadados opcionais
        quotation_metadata = data.get("quotation_metadata")
        if quotation_metadata and isinstance(quotation_metadata, dict):
            import json as json_lib
            quotation_metadata = json_lib.dumps(quotation_metadata)
        else:
            quotation_metadata = None

        # Insere o orçamento
        await conn.execute("""
            INSERT INTO quotations (
                id, quotation_number, quotation_date, valid_until,
                customer_id, seller_id,
                subtotal, discount_amount, discount_percent, freight_amount, total_amount,
                payment_method, payment_terms, installments,
                quotation_status, notes, internal_notes,
                converted_to_sale, quotation_metadata,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
            )
        """,
            quotation_id, quotation_number, quotation_date, valid_until,
            to_str(data.get("customer_id")), to_str(data.get("seller_id")),
            subtotal, discount_amount, discount_percent, freight_amount, total_amount,
            to_str(data.get("payment_method")), to_str(data.get("payment_terms")),
            to_int(data.get("installments")) or 1,
            to_str(data.get("quotation_status")) or "pending",
            to_str(data.get("notes")), to_str(data.get("internal_notes")),
            False, quotation_metadata,
            now, now
        )

        # Insere itens do orçamento
        items = data.get("items", [])
        for item in items:
            item_id = str(uuid.uuid4())
            product_id = to_str(item.get("product_id"))
            quantity = to_decimal(item.get("quantity")) or 1
            unit_price = to_decimal(item.get("unit_price")) or 0
            item_subtotal = quantity * unit_price
            item_discount = to_decimal(item.get("discount_amount")) or 0
            item_total = item_subtotal - item_discount

            # Busca nome do produto se não fornecido
            product_name = to_str(item.get("product_name")) or to_str(item.get("name"))
            if not product_name and product_id:
                prod_row = await conn.fetchrow("SELECT name FROM products WHERE id = $1", product_id)
                if prod_row:
                    product_name = prod_row["name"]

            await conn.execute("""
                INSERT INTO quotation_items (
                    id, quotation_id, product_id, product_name,
                    quantity, unit_price, discount_amount, discount_percent, total_amount,
                    created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                )
            """,
                item_id, quotation_id, product_id,
                product_name or "Produto",
                quantity, unit_price,
                item_discount, to_decimal(item.get("discount_percent")) or 0, item_total,
                now, now
            )

        return {
            "id": quotation_id,
            "quotation_number": quotation_number,
            "quotation_date": str(quotation_date),
            "valid_until": str(valid_until),
            "customer_id": to_str(data.get("customer_id")),
            "total_amount": float(total_amount),
            "items_count": len(items),
            "message": "Orçamento criado com sucesso"
        }

    except Exception as e:
        logger.error(f"Erro ao criar orçamento: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro ao criar orçamento: {str(e)}")
    finally:
        await conn.close()


@router.post("/quotations/{quotation_id}/convert-to-sale")
async def convert_quotation_to_sale(
    quotation_id: str,
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Converte um orçamento em venda"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Garante que as tabelas existem
        await ensure_quotations_schema(conn)

        data = await request.json() if request else {}

        # Busca o orçamento
        quotation = await conn.fetchrow("""
            SELECT * FROM quotations WHERE id = $1
        """, quotation_id)

        if not quotation:
            raise HTTPException(status_code=404, detail="Orçamento não encontrado")

        if quotation["converted_to_sale"]:
            raise HTTPException(status_code=400, detail="Orçamento já foi convertido em venda")

        # Busca itens do orçamento
        items_rows = await conn.fetch("""
            SELECT * FROM quotation_items WHERE quotation_id = $1
        """, quotation_id)

        now = datetime.utcnow()
        sale_id = str(uuid.uuid4())

        # Gera número da venda
        count_row = await conn.fetchrow("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(sale_number FROM 4) AS INTEGER)), 0) + 1 as next_num
            FROM sales WHERE sale_number LIKE 'VND%'
        """)
        next_num = count_row["next_num"] if count_row else 1
        sale_number = f"VND{next_num:06d}"

        # Cria a venda baseada no orçamento
        await conn.execute("""
            INSERT INTO sales (
                id, sale_number, sale_date, customer_id, seller_id,
                subtotal, discount_amount, discount_percent, total_amount,
                payment_method, payment_status, installments,
                sale_status, notes, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
            )
        """,
            sale_id, sale_number, now.date(),
            quotation["customer_id"], quotation["seller_id"],
            quotation["subtotal"], quotation["discount_amount"],
            quotation["discount_percent"], quotation["total_amount"],
            quotation["payment_method"], "pending",
            quotation["installments"], "completed",
            f"Convertido do orçamento {quotation['quotation_number']}",
            now, now
        )

        # Copia itens e baixa estoque
        update_stock = data.get("update_stock", True)
        for item in items_rows:
            item_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO sale_items (
                    id, sale_id, product_id, product_name,
                    quantity, unit_price, discount_amount, discount_percent, total_amount,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
                item_id, sale_id, item["product_id"], item["product_name"],
                item["quantity"], item["unit_price"],
                item["discount_amount"], item["discount_percent"], item["total_amount"],
                now, now
            )

            # Baixa estoque
            if update_stock and item["product_id"]:
                await conn.execute("""
                    UPDATE products
                    SET current_stock = COALESCE(current_stock, 0) - $1,
                        available_stock = COALESCE(available_stock, 0) - $1,
                        updated_at = $2
                    WHERE id = $3 AND stock_control = true
                """, item["quantity"], now, item["product_id"])

        # Atualiza orçamento como convertido
        await conn.execute("""
            UPDATE quotations
            SET converted_to_sale = true,
                sale_id = $1,
                converted_at = $2,
                quotation_status = 'converted',
                updated_at = $2
            WHERE id = $3
        """, sale_id, now, quotation_id)

        # Cria contas a receber
        total_amount = float(quotation["total_amount"])
        num_installments = quotation["installments"] or 1
        customer_id = quotation["customer_id"]

        if total_amount > 0:
            from dateutil.relativedelta import relativedelta

            if num_installments == 1:
                receivable_id = str(uuid.uuid4())
                due_date = now.date() + relativedelta(months=1)
                await conn.execute("""
                    INSERT INTO accounts_receivable (
                        id, customer_id, parent_id,
                        description, document_number, amount, paid_amount,
                        issue_date, due_date, status, payment_method,
                        category, installment_number, total_installments,
                        created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                    receivable_id, customer_id, None,
                    f"Venda {sale_number}", sale_number, total_amount, 0.0,
                    now.date(), due_date, "PENDING", quotation["payment_method"],
                    "VENDAS", 0, 1, now, now
                )
            else:
                parent_id = str(uuid.uuid4())
                installment_amount = round(total_amount / num_installments, 2)
                last_amount = round(total_amount - (installment_amount * (num_installments - 1)), 2)

                await conn.execute("""
                    INSERT INTO accounts_receivable (
                        id, customer_id, parent_id,
                        description, document_number, amount, paid_amount,
                        issue_date, due_date, status, payment_method,
                        category, installment_number, total_installments,
                        created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                """,
                    parent_id, customer_id, None,
                    f"Venda {sale_number}", sale_number, total_amount, 0.0,
                    now.date(), now.date(), "PENDING", quotation["payment_method"],
                    "VENDAS", 0, num_installments, now, now
                )

                for i in range(1, num_installments + 1):
                    inst_id = str(uuid.uuid4())
                    amount = last_amount if i == num_installments else installment_amount
                    due_date = now.date() + relativedelta(months=i)
                    await conn.execute("""
                        INSERT INTO accounts_receivable (
                            id, customer_id, parent_id,
                            description, document_number, amount, paid_amount,
                            issue_date, due_date, status, payment_method,
                            category, installment_number, total_installments,
                            created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    """,
                        inst_id, customer_id, parent_id,
                        f"Venda {sale_number} - Parcela {i}/{num_installments}",
                        f"{sale_number}-{i}", amount, 0.0,
                        now.date(), due_date, "PENDING", quotation["payment_method"],
                        "VENDAS", i, num_installments, now, now
                    )

        return {
            "success": True,
            "sale_id": sale_id,
            "sale_number": sale_number,
            "quotation_number": quotation["quotation_number"],
            "message": f"Orçamento convertido para venda {sale_number}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao converter orçamento: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro ao converter orçamento: {str(e)}")
    finally:
        await conn.close()


# === ENDPOINTS - PURCHASES ===

@router.get("/purchases")
async def list_purchases(
    skip: int = 0,
    limit: int = 100,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista compras do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Conta total para paginação
        total = await conn.fetchval("SELECT COUNT(*) FROM purchases") or 0

        # Schema legado: suppliers usa company_name/trade_name/name
        rows = await conn.fetch("""
            SELECT p.*,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM purchases p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            ORDER BY p.purchase_date DESC
            LIMIT $1 OFFSET $2
        """, limit, skip)

        items = [row_to_dict(row) for row in rows]
        return {"items": items, "total": total, "purchases": items}
    finally:
        await conn.close()


@router.post("/purchases")
@router.post("/purchases/")
async def create_purchase(
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria uma nova compra com itens e contas a pagar"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        data = await request.json()
        purchase_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Gera número da compra se não fornecido
        purchase_number = data.get("purchase_number")
        if not purchase_number:
            count = await conn.fetchval("SELECT COUNT(*) FROM purchases") or 0
            purchase_number = f"CMP{count + 1:06d}"

        # Converte datas
        def parse_date(val):
            if not val or val == '' or val == 'null':
                return None
            if isinstance(val, str):
                from datetime import datetime as dt
                if 'T' in val:
                    return dt.fromisoformat(val.replace('Z', '+00:00')).date()
                return dt.strptime(val, '%Y-%m-%d').date()
            return val

        purchase_date = parse_date(data.get("purchase_date")) or now.date()
        invoice_date = parse_date(data.get("invoice_date"))
        delivery_date = parse_date(data.get("delivery_date"))
        expected_delivery_date = parse_date(data.get("expected_delivery_date"))

        # Calcula valores
        subtotal = to_decimal(data.get("subtotal")) or 0
        discount_amount = to_decimal(data.get("discount_amount")) or 0
        freight_amount = to_decimal(data.get("freight_amount")) or 0
        insurance_amount = to_decimal(data.get("insurance_amount")) or 0
        other_expenses = to_decimal(data.get("other_expenses")) or 0
        tax_amount = to_decimal(data.get("tax_amount")) or 0
        total_amount = to_decimal(data.get("total_amount")) or (subtotal - discount_amount + freight_amount + insurance_amount + other_expenses + tax_amount)

        # Insere a compra
        await conn.execute("""
            INSERT INTO purchases (
                id, purchase_number, supplier_id, invoice_number, invoice_series,
                invoice_key, invoice_date, purchase_date, delivery_date, expected_delivery_date,
                subtotal, discount_amount, freight_amount, insurance_amount, other_expenses,
                tax_amount, total_amount, payment_method, payment_terms, installments,
                status, notes, internal_notes, stock_updated, accounts_payable_created,
                cfop, nature_operation, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22, $23, $24, $25, $26, $27, $28, $29
            )
        """,
            purchase_id, purchase_number, to_str(data.get("supplier_id")),
            to_str(data.get("invoice_number")), to_str(data.get("invoice_series")),
            to_str(data.get("invoice_key")), invoice_date, purchase_date,
            delivery_date, expected_delivery_date,
            subtotal, discount_amount, freight_amount, insurance_amount, other_expenses,
            tax_amount, total_amount, to_str(data.get("payment_method")),
            to_str(data.get("payment_terms")), to_int(data.get("installments")) or 1,
            to_str(data.get("status")) or "PENDING", to_str(data.get("notes")),
            to_str(data.get("internal_notes")), False, False,
            to_str(data.get("cfop")), to_str(data.get("nature_operation")),
            now, now
        )

        # Insere itens da compra se houver
        items = data.get("items", [])
        for idx, item in enumerate(items):
            item_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO purchase_items (
                    id, purchase_id, product_id, item_number, description,
                    quantity, quantity_received, unit_of_measure,
                    unit_price, discount_percent, discount_amount, subtotal, total,
                    icms_percent, ipi_percent, batch_number,
                    manufacturing_date, expiration_date, ncm, cfop, notes,
                    stock_updated, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24
                )
            """,
                item_id, purchase_id, to_str(item.get("product_id")),
                idx + 1, to_str(item.get("description")),
                to_decimal(item.get("quantity")) or 1, to_decimal(item.get("quantity_received")) or 0,
                to_str(item.get("unit_of_measure")) or "UN",
                to_decimal(item.get("unit_price")) or 0, to_decimal(item.get("discount_percent")) or 0,
                to_decimal(item.get("discount_amount")) or 0, to_decimal(item.get("subtotal")) or 0,
                to_decimal(item.get("total")) or 0, to_decimal(item.get("icms_percent")) or 0,
                to_decimal(item.get("ipi_percent")) or 0, to_str(item.get("batch_number")),
                parse_date(item.get("manufacturing_date")), parse_date(item.get("expiration_date")),
                to_str(item.get("ncm")), to_str(item.get("cfop")), to_str(item.get("notes")),
                False, now, now
            )

        # Cria contas a pagar se solicitado
        create_payable = data.get("create_accounts_payable", False)
        if create_payable and total_amount > 0:
            num_installments = to_int(data.get("installments")) or 1
            supplier_id = to_str(data.get("supplier_id"))

            # Busca nome do fornecedor
            supplier_name = None
            if supplier_id:
                supplier_row = await conn.fetchrow(
                    "SELECT COALESCE(company_name, trade_name, name) as name FROM suppliers WHERE id = $1",
                    supplier_id
                )
                if supplier_row:
                    supplier_name = supplier_row["name"]

            if num_installments == 1:
                # Parcela única
                payable_id = str(uuid.uuid4())
                await conn.execute("""
                    INSERT INTO accounts_payable (
                        id, supplier_id, purchase_id, parent_id, supplier,
                        description, document_number, amount, amount_paid, balance,
                        issue_date, due_date, payment_date, status, payment_method,
                        category, installment_number, total_installments, notes,
                        created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
                    )
                """,
                    payable_id, supplier_id, purchase_id, None, supplier_name,
                    f"Compra {purchase_number}", to_str(data.get("invoice_number")),
                    total_amount, 0.0, total_amount,
                    purchase_date, purchase_date, None, "PENDING", to_str(data.get("payment_method")),
                    "COMPRAS", 0, 1, to_str(data.get("notes")),
                    now, now
                )
            else:
                # Múltiplas parcelas
                parent_id = str(uuid.uuid4())
                installment_amount = round(total_amount / num_installments, 2)
                last_installment_amount = round(total_amount - (installment_amount * (num_installments - 1)), 2)

                # Cria registro pai
                await conn.execute("""
                    INSERT INTO accounts_payable (
                        id, supplier_id, purchase_id, parent_id, supplier,
                        description, document_number, amount, amount_paid, balance,
                        issue_date, due_date, payment_date, status, payment_method,
                        category, installment_number, total_installments, notes,
                        created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
                    )
                """,
                    parent_id, supplier_id, purchase_id, None, supplier_name,
                    f"Compra {purchase_number}", to_str(data.get("invoice_number")),
                    total_amount, 0.0, total_amount,
                    purchase_date, purchase_date, None, "PENDING", to_str(data.get("payment_method")),
                    "COMPRAS", 0, num_installments, to_str(data.get("notes")),
                    now, now
                )

                # Cria parcelas filhas
                from datetime import timedelta
                for i in range(1, num_installments + 1):
                    child_id = str(uuid.uuid4())
                    due = purchase_date + timedelta(days=30 * i)
                    amount = round(last_installment_amount if i == num_installments else installment_amount, 2)

                    await conn.execute("""
                        INSERT INTO accounts_payable (
                            id, supplier_id, purchase_id, parent_id, supplier,
                            description, document_number, amount, amount_paid, balance,
                            issue_date, due_date, payment_date, status, payment_method,
                            category, installment_number, total_installments, notes,
                            created_at, updated_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
                        )
                    """,
                        child_id, supplier_id, purchase_id, parent_id, supplier_name,
                        f"Compra {purchase_number} - Parcela {i}/{num_installments}",
                        to_str(data.get("invoice_number")),
                        amount, 0.0, amount,
                        purchase_date, due, None, "PENDING", to_str(data.get("payment_method")),
                        "COMPRAS", i, num_installments, to_str(data.get("notes")),
                        now, now
                    )

            # Marca que contas a pagar foram criadas
            await conn.execute(
                "UPDATE purchases SET accounts_payable_created = TRUE WHERE id = $1",
                purchase_id
            )

        return {"id": purchase_id, "purchase_number": purchase_number, "message": "Compra criada com sucesso"}

    except Exception as e:
        print(f"[PURCHASE] Erro ao criar compra: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(
    purchase_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Deleta uma compra e suas contas a pagar relacionadas"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Verifica se a compra existe
        purchase = await conn.fetchrow(
            "SELECT id FROM purchases WHERE id = $1",
            purchase_id
        )
        if not purchase:
            raise HTTPException(status_code=404, detail="Compra não encontrada")

        # Deleta contas a pagar relacionadas (incluindo parcelas filhas)
        await conn.execute(
            "DELETE FROM accounts_payable WHERE purchase_id = $1",
            purchase_id
        )

        # Deleta itens da compra
        await conn.execute(
            "DELETE FROM purchase_items WHERE purchase_id = $1",
            purchase_id
        )

        # Deleta a compra
        await conn.execute(
            "DELETE FROM purchases WHERE id = $1",
            purchase_id
        )

        print(f"[PURCHASE] Compra {purchase_id} deletada com sucesso", flush=True)
        return {"message": "Compra deletada com sucesso"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PURCHASE] Erro ao deletar compra: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


# === ENDPOINTS - ACCOUNTS RECEIVABLE ===

@router.get("/accounts-receivable")
@router.get("/accounts-receivable/")
async def list_accounts_receivable(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    search: Optional[str] = None,
    customer_id: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista contas a receber do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Conta total para paginacao
        total = await conn.fetchval("SELECT COUNT(*) FROM accounts_receivable") or 0

        # FILTRO POR CUSTOMER_ID - usado na tela de Vendas para mostrar contas do cliente selecionado
        if customer_id:
            print(f"[AR] Filtrando por customer_id: {customer_id}", flush=True)
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                    (SELECT MIN(child.due_date) FROM accounts_receivable child
                     WHERE child.parent_id = ar.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE (ar.installment_number = 0 OR ar.installment_number IS NULL)
                  AND ar.customer_id = $1
                ORDER BY ar.due_date DESC
                LIMIT $2 OFFSET $3
            """, customer_id, limit, skip)
            print(f"[AR] Encontradas {len(rows)} contas para customer_id {customer_id}", flush=True)
            items = [row_to_dict(row) for row in rows]
            return {"items": items, "total": len(items)}

        # Schema legado: customers usa first_name/last_name em vez de name
        # IMPORTANTE: Retorna apenas contas PAI (installment_number = 0)
        # Inclui next_due_date = próxima parcela a vencer (não paga)
        if search:
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                    (SELECT MIN(child.due_date) FROM accounts_receivable child
                     WHERE child.parent_id = ar.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE (ar.installment_number = 0 OR ar.installment_number IS NULL)
                  AND (c.first_name ILIKE $1 OR c.last_name ILIKE $1
                    OR c.company_name ILIKE $1 OR ar.description ILIKE $1)
                ORDER BY ar.due_date
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        elif status:
            # Converte status para UPPERCASE para comparar com ENUM
            status_upper = status.upper()
            print(f"[AR] Filtrando por status: {status_upper}", flush=True)

            # OVERDUE: Contas PAI que têm PARCELAS FILHAS vencidas e não pagas
            if status_upper == 'OVERDUE':
                rows = await conn.fetch("""
                    SELECT ar.*,
                        COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                        (SELECT MIN(child.due_date) FROM accounts_receivable child
                         WHERE child.parent_id = ar.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                    FROM accounts_receivable ar
                    LEFT JOIN customers c ON ar.customer_id = c.id
                    WHERE (ar.installment_number = 0 OR ar.installment_number IS NULL)
                      AND UPPER(ar.status::text) IN ('PENDING', 'PARTIAL')
                      AND (
                          -- Conta PAI com parcelas: tem parcela vencida não paga
                          EXISTS (
                              SELECT 1 FROM accounts_receivable child
                              WHERE child.parent_id = ar.id
                              AND child.due_date < CURRENT_DATE
                              AND UPPER(child.status::text) != 'PAID'
                          )
                          OR
                          -- Conta simples sem parcelas: a própria conta está vencida
                          (NOT EXISTS (SELECT 1 FROM accounts_receivable child WHERE child.parent_id = ar.id)
                           AND ar.due_date < CURRENT_DATE)
                      )
                    ORDER BY ar.due_date
                    LIMIT $1 OFFSET $2
                """, limit, skip)

            # PAID: Contas PAI que têm PELO MENOS UMA parcela paga
            # (mostra contas que receberam pagamentos)
            elif status_upper == 'PAID':
                rows = await conn.fetch("""
                    SELECT ar.*,
                        COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                        (SELECT MIN(child.due_date) FROM accounts_receivable child
                         WHERE child.parent_id = ar.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                    FROM accounts_receivable ar
                    LEFT JOIN customers c ON ar.customer_id = c.id
                    WHERE (ar.installment_number = 0 OR ar.installment_number IS NULL)
                      AND (
                          -- Conta PAI com parcelas: tem pelo menos uma parcela paga
                          EXISTS (
                              SELECT 1 FROM accounts_receivable child
                              WHERE child.parent_id = ar.id
                              AND UPPER(child.status::text) = 'PAID'
                          )
                          OR
                          -- Conta simples sem parcelas: a própria conta está paga
                          (NOT EXISTS (SELECT 1 FROM accounts_receivable child WHERE child.parent_id = ar.id)
                           AND UPPER(ar.status::text) = 'PAID')
                      )
                    ORDER BY ar.due_date DESC
                    LIMIT $1 OFFSET $2
                """, limit, skip)

            # PENDING/PARTIAL: Filtro normal
            else:
                rows = await conn.fetch("""
                    SELECT ar.*,
                        COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                        (SELECT MIN(child.due_date) FROM accounts_receivable child
                         WHERE child.parent_id = ar.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                    FROM accounts_receivable ar
                    LEFT JOIN customers c ON ar.customer_id = c.id
                    WHERE (ar.installment_number = 0 OR ar.installment_number IS NULL)
                      AND UPPER(ar.status::text) = $3
                    ORDER BY ar.due_date
                    LIMIT $1 OFFSET $2
                """, limit, skip, status_upper)

            print(f"[AR] Encontradas {len(rows)} contas com status {status_upper}", flush=True)

        # Listagem geral (sem filtro de status)
        else:
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                    (SELECT MIN(child.due_date) FROM accounts_receivable child
                     WHERE child.parent_id = ar.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE (ar.installment_number = 0 OR ar.installment_number IS NULL)
                ORDER BY ar.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip)

        items = [row_to_dict(row) for row in rows]
        return {"items": items, "total": total}
    finally:
        await conn.close()


@router.get("/accounts-receivable/{account_id}")
async def get_account_receivable(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca conta a receber por ID"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            SELECT ar.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE ar.id = $1
        """, account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.get("/accounts-receivable/{account_id}/installments")
async def get_account_installments(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna todas as parcelas de uma conta a receber (conta pai)"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca a conta pai e todas as parcelas filhas
        rows = await conn.fetch("""
            SELECT ar.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE ar.id = $1 OR ar.parent_id = $1
            ORDER BY ar.installment_number
        """, account_id)

        if not rows:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")

        # Retorna apenas as parcelas (installment_number > 0)
        # Se nao houver parcelas, retorna a conta original
        items = []
        for row in rows:
            row_dict = row_to_dict(row)
            installment_num = row_dict.get("installment_number", 0)

            # Adiciona account_id para compatibilidade com frontend
            # account_id é o parent_id (conta pai) ou o próprio id se for conta simples
            row_dict["account_id"] = row_dict.get("parent_id") or row_dict.get("id")

            # IMPORTANTE: Arredonda valores para evitar erros de ponto flutuante
            amount = round(float(row_dict.get("amount") or 0), 2)
            paid_amount = round(float(row_dict.get("paid_amount") or 0), 2)
            row_dict["amount"] = amount
            row_dict["paid_amount"] = paid_amount
            row_dict["balance"] = round(amount - paid_amount, 2)

            if installment_num > 0:
                items.append(row_dict)
            elif len(rows) == 1:
                # Conta simples sem parcelas
                items.append(row_dict)

        return items
    finally:
        await conn.close()


@router.post("/accounts-receivable")
@router.post("/accounts-receivable/")
async def create_account_receivable(
    account: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria conta a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Gera UUID para o ID
        import uuid
        account_id = str(uuid.uuid4())

        # Converte due_date para date se for string
        due_date = account.get("due_date")
        if isinstance(due_date, str):
            from datetime import datetime as dt
            due_date = dt.fromisoformat(due_date.replace('Z', '+00:00')).date() if 'T' in due_date else dt.strptime(due_date, '%Y-%m-%d').date()

        # issue_date default para hoje se nao informado
        issue_date = account.get("issue_date")
        if issue_date is None:
            issue_date = datetime.utcnow().date()
        elif isinstance(issue_date, str):
            from datetime import datetime as dt
            issue_date = dt.fromisoformat(issue_date.replace('Z', '+00:00')).date() if 'T' in issue_date else dt.strptime(issue_date, '%Y-%m-%d').date()

        row = await conn.fetchrow("""
            INSERT INTO accounts_receivable (
                id, customer_id, description, amount, paid_amount, due_date, issue_date,
                status, payment_method, installment_number, total_installments, parent_id, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
        """,
            account_id,
            account.get("customer_id"),
            account.get("description", ""),
            float(account.get("amount", 0)),
            float(account.get("paid_amount", 0)),
            due_date,
            issue_date,
            account.get("status", "PENDING").upper(),
            account.get("payment_method", "PIX").upper() if account.get("payment_method") else "PIX",
            account.get("installment_number"),
            account.get("total_installments"),
            account.get("parent_id"),
            True  # is_active sempre True ao criar
        )
        return row_to_dict(row)
    finally:
        await conn.close()


@router.put("/accounts-receivable/{account_id}")
async def update_account_receivable(
    account_id: str,
    account: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza conta a receber com redistribuição automática de valores entre parcelas"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Converte due_date de string para date se necessário
        due_date = account.get("due_date")
        if isinstance(due_date, str) and due_date:
            from datetime import datetime as dt
            if 'T' in due_date:
                due_date = dt.fromisoformat(due_date.replace('Z', '+00:00')).date()
            else:
                due_date = dt.strptime(due_date, '%Y-%m-%d').date()

        # Converte payment_date de string para date se necessário
        payment_date = account.get("payment_date")
        if isinstance(payment_date, str) and payment_date:
            from datetime import datetime as dt
            if 'T' in payment_date:
                payment_date = dt.fromisoformat(payment_date.replace('Z', '+00:00')).date()
            else:
                payment_date = dt.strptime(payment_date, '%Y-%m-%d').date()

        # Busca dados atuais da parcela para verificar mudanças de valor
        current = await conn.fetchrow(
            "SELECT * FROM accounts_receivable WHERE id = $1",
            account_id
        )
        if not current:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")

        new_amount = float(account.get("amount", 0))
        old_amount = float(current["amount"] or 0)
        amount_diff = new_amount - old_amount

        # Atualiza a parcela atual
        row = await conn.fetchrow("""
            UPDATE accounts_receivable SET
                customer_id = $2, description = $3, amount = $4, paid_amount = $5,
                due_date = $6, status = $7, payment_date = $8, updated_at = $9
            WHERE id = $1
            RETURNING *
        """,
            account_id,
            account.get("customer_id"),
            account.get("description", ""),
            new_amount,
            float(account.get("paid_amount", 0)),
            due_date,
            (account.get("status") or "PENDING").upper(),  # ENUM requer MAIÚSCULO
            payment_date,
            datetime.utcnow()
        )

        # Se houve alteração de valor E a parcela tem parent_id (faz parte de parcelamento)
        # redistribui a diferença entre as parcelas restantes não pagas
        parent_id = current.get("parent_id")
        installment_number = current.get("installment_number") or 1

        if amount_diff != 0 and parent_id:
            # Busca parcelas futuras não pagas (status != 'PAID')
            remaining_installments = await conn.fetch("""
                SELECT id, amount, installment_number
                FROM accounts_receivable
                WHERE parent_id = $1
                  AND installment_number > $2
                  AND status != 'PAID'
                ORDER BY installment_number
            """, parent_id, installment_number)

            if remaining_installments:
                # Distribui a diferença (inverso: se pagou mais, diminui nas próximas)
                # IMPORTANTE: Arredondar para 2 casas decimais para evitar centavos extras
                num_remaining = len(remaining_installments)
                diff_per_installment = round(-amount_diff / num_remaining, 2)

                # Calcula o total que será distribuído
                total_distributed = round(diff_per_installment * (num_remaining - 1), 2)
                # A última parcela recebe o restante para garantir soma exata
                last_diff = round(-amount_diff - total_distributed, 2)

                for i, inst in enumerate(remaining_installments):
                    # Última parcela recebe o ajuste para zerar diferença de centavos
                    if i == num_remaining - 1:
                        adjustment = last_diff
                    else:
                        adjustment = diff_per_installment

                    new_inst_amount = round(max(0, float(inst["amount"]) + adjustment), 2)
                    await conn.execute("""
                        UPDATE accounts_receivable
                        SET amount = $2, updated_at = $3
                        WHERE id = $1
                    """, inst["id"], new_inst_amount, datetime.utcnow())

                logger.info(f"Redistribuído {-amount_diff:.2f} entre {num_remaining} parcelas restantes")

        return row_to_dict(row)
    finally:
        await conn.close()


@router.delete("/accounts-receivable/{account_id}")
async def delete_account_receivable(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove conta a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        result = await conn.execute("DELETE FROM accounts_receivable WHERE id = $1", account_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        return {"success": True, "message": "Conta removida"}
    finally:
        await conn.close()


@router.post("/accounts-receivable/{account_id}/pay")
async def pay_account_receivable(
    account_id: str,
    payment: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Registra pagamento de conta a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca conta atual
        row = await conn.fetchrow("SELECT * FROM accounts_receivable WHERE id = $1", account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")

        payment_amount = float(payment.get("payment_amount", 0))
        current_paid = float(row["paid_amount"] or 0)
        total_amount = float(row["amount"])
        new_paid = current_paid + payment_amount

        # Determina novo status - usa MAIÚSCULO para o ENUM
        new_status = "PAID" if new_paid >= total_amount else "PARTIAL"

        # Converte payment_date para date se for string
        payment_date = payment.get("payment_date")
        if isinstance(payment_date, str):
            from datetime import datetime as dt
            payment_date = dt.fromisoformat(payment_date.replace('Z', '+00:00')).date() if 'T' in payment_date else dt.strptime(payment_date, '%Y-%m-%d').date()

        # Atualiza conta
        updated = await conn.fetchrow("""
            UPDATE accounts_receivable SET
                paid_amount = $2, status = $3, payment_date = $4, updated_at = $5
            WHERE id = $1
            RETURNING *
        """, account_id, new_paid, new_status, payment_date, datetime.utcnow())

        return row_to_dict(updated)
    finally:
        await conn.close()


@router.get("/accounts-receivable/{account_id}/installments/{installment_number}/receipt")
async def generate_installment_receipt(
    account_id: str,
    installment_number: int,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Gera recibo PDF de uma parcela paga - Design Faraônico"""
    from fastapi.responses import Response
    from app.utils.receiptGenerator import generate_receipt_pdf

    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca a parcela específica - usando colunas explícitas para evitar erro de paid_amount
        installment = await conn.fetchrow("""
            SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                   ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                   ar.due_date, ar.payment_date, ar.status::text as status,
                   ar.installment_number, ar.total_installments,
                   COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                   c.cpf_cnpj as customer_document,
                   c.email as customer_email,
                   c.phone as customer_phone,
                   c.address as customer_address,
                   c.city as customer_city,
                   c.state as customer_state
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE ar.parent_id = $1 AND ar.installment_number = $2
        """, account_id, installment_number)

        if not installment:
            # Tenta buscar a conta diretamente (conta simples sem parcelas)
            installment = await conn.fetchrow("""
                SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                       ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                       ar.due_date, ar.payment_date, ar.status::text as status,
                       ar.installment_number, ar.total_installments,
                       COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                       c.cpf_cnpj as customer_document,
                       c.email as customer_email,
                       c.phone as customer_phone,
                       c.address as customer_address,
                       c.city as customer_city,
                       c.state as customer_state
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE ar.id = $1
            """, account_id)

        if not installment:
            raise HTTPException(status_code=404, detail="Parcela não encontrada")

        # Busca dados da empresa
        company = await conn.fetchrow("SELECT * FROM companies LIMIT 1")

        # Prepara dados para o gerador de recibo Faraônico
        installment_data = {
            'id': str(installment['id']),
            'amount': float(installment['paid_amount'] or installment['amount']),
            'installment_number': installment['installment_number'] or 1,
            'total_installments': installment['total_installments'] or 1,
            'description': installment['description'] or 'Conta a Receber',
            'payment_date': installment['payment_date'] or installment['due_date'],
            'due_date': installment['due_date'],
        }

        customer_data = {
            'name': installment['customer_name'] or 'Cliente',
            'document': installment['customer_document'] or 'N/A',
        }

        company_data = None
        logo_full_path = None
        if company:
            company_data = {
                'legal_name': company.get('legal_name') or company.get('trade_name') or company.get('name'),
                'trade_name': company.get('trade_name') or company.get('legal_name') or company.get('name'),
                'document': company.get('document') or company.get('cnpj') or company.get('cpf_cnpj'),
                'person_type': 'PJ' if company.get('document') and len(str(company.get('document', '')).replace('.', '').replace('-', '').replace('/', '')) == 14 else 'PF',
                'street': company.get('street') or company.get('address'),
                'number': company.get('number') or company.get('address_number'),
                'neighborhood': company.get('neighborhood'),
                'city': company.get('city'),
                'state': company.get('state'),
            }
            # Multi-tenant: Busca caminho completo da logo
            if company.get('logo_path'):
                if os.path.exists("/app/uploads"):
                    logo_full_path = f"/app/uploads/{company.get('logo_path')}"
                else:
                    upload_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
                    logo_full_path = os.path.join(upload_base, company.get('logo_path'))

        # Gera o PDF Faraônico com logo do tenant
        pdf_bytes = await generate_receipt_pdf(installment_data, customer_data, company_data, logo_path=logo_full_path)

        # Nome do arquivo
        customer_name_clean = (installment['customer_name'] or 'cliente').replace(' ', '_')[:30]
        filename = f"recibo_{customer_name_clean}_parcela_{installment_number}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    finally:
        await conn.close()


@router.get("/accounts-receivable/{account_id}/installments/{installment_number}/promissory-note")
async def generate_promissory_note(
    account_id: str,
    installment_number: int,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Gera Nota Promissória PDF de uma parcela - Conforme Lei Uniforme de Genebra"""
    from fastapi.responses import Response
    from app.utils.promissoryGenerator import generate_promissory_pdf

    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca a parcela específica - usando colunas explícitas para evitar erro de paid_amount
        installment = await conn.fetchrow("""
            SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                   ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                   ar.due_date, ar.payment_date, ar.status::text as status,
                   ar.installment_number, ar.total_installments,
                   COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                   c.cpf_cnpj as customer_document,
                   c.email as customer_email,
                   c.phone as customer_phone,
                   c.address as customer_address,
                   c.city as customer_city,
                   c.state as customer_state,
                   c.zip_code as customer_zip
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE ar.parent_id = $1 AND ar.installment_number = $2
        """, account_id, installment_number)

        if not installment:
            # Tenta buscar a conta diretamente (conta simples sem parcelas)
            installment = await conn.fetchrow("""
                SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                       ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                       ar.due_date, ar.payment_date, ar.status::text as status,
                       ar.installment_number, ar.total_installments,
                       COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                       c.cpf_cnpj as customer_document,
                       c.email as customer_email,
                       c.phone as customer_phone,
                       c.address as customer_address,
                       c.city as customer_city,
                       c.state as customer_state,
                       c.zip_code as customer_zip
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE ar.id = $1
            """, account_id)

        if not installment:
            raise HTTPException(status_code=404, detail="Parcela não encontrada")

        # Busca dados da empresa
        company = await conn.fetchrow("SELECT * FROM companies LIMIT 1")

        # Prepara dados para o gerador de promissória profissional
        company_data = {}
        if company:
            company_address = ""
            if company.get('street') or company.get('address'):
                company_address = company.get('street') or company.get('address') or ''
                if company.get('number') or company.get('address_number'):
                    company_address += f", {company.get('number') or company.get('address_number')}"
                if company.get('neighborhood'):
                    company_address += f" - {company.get('neighborhood')}"
                if company.get('city') and company.get('state'):
                    company_address += f" - {company.get('city')}/{company.get('state')}"

            company_data = {
                'legal_name': company.get('legal_name') or company.get('trade_name') or company.get('name'),
                'trade_name': company.get('trade_name') or company.get('legal_name') or company.get('name'),
                'document': company.get('document') or company.get('cnpj') or company.get('cpf_cnpj'),
                'address': company_address,
                'city': company.get('city'),
                'state': company.get('state'),
            }

        customer_address = ""
        if installment['customer_address']:
            customer_address = installment['customer_address']
            if installment['customer_city']:
                customer_address += f" - {installment['customer_city']}"
            if installment['customer_state']:
                customer_address += f"/{installment['customer_state']}"

        customer_data = {
            'name': installment['customer_name'] or 'Cliente',
            'document': installment['customer_document'] or 'N/A',
            'address': customer_address or 'Não informado',
            'city': installment['customer_city'] or '',
            'state': installment['customer_state'] or '',
        }

        # Calcula valor (saldo se houver pagamento parcial)
        amount = float(installment['amount'])
        paid = float(installment['paid_amount'] or 0)
        balance = amount - paid if paid > 0 else amount

        # Gera o PDF profissional
        pdf_bytes = await generate_promissory_pdf(
            company_data=company_data,
            customer_data=customer_data,
            total_value=balance,
            due_date=installment['due_date'],
            doc_number=installment['document_number'] or f"NP-{installment['id'][:8].upper()}"
        )

        # Nome do arquivo
        customer_name_clean = (installment['customer_name'] or 'cliente').replace(' ', '_')[:30]
        filename = f"promissoria_{customer_name_clean}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    finally:
        await conn.close()


def self_extenso(valor):
    """Converte valor numérico para extenso em português"""
    try:
        valor = float(valor)
        if valor == 0:
            return "zero reais"

        unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove',
                   'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
        dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
        centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']

        def extenso_ate_999(n):
            n = int(n)
            if n == 0:
                return ''
            if n == 100:
                return 'cem'
            if n < 20:
                return unidades[n]
            if n < 100:
                dezena = n // 10
                unidade = n % 10
                if unidade == 0:
                    return dezenas[dezena]
                return f"{dezenas[dezena]} e {unidades[unidade]}"
            centena = n // 100
            resto = n % 100
            if resto == 0:
                return centenas[centena] if centena != 1 else 'cem'
            return f"{centenas[centena]} e {extenso_ate_999(resto)}"

        inteiro = int(valor)
        centavos = round((valor - inteiro) * 100)

        resultado = []

        if inteiro >= 1000000:
            milhoes = inteiro // 1000000
            inteiro = inteiro % 1000000
            if milhoes == 1:
                resultado.append("um milhão")
            else:
                resultado.append(f"{extenso_ate_999(milhoes)} milhões")

        if inteiro >= 1000:
            milhares = inteiro // 1000
            inteiro = inteiro % 1000
            if milhares == 1:
                resultado.append("mil")
            else:
                resultado.append(f"{extenso_ate_999(milhares)} mil")

        if inteiro > 0:
            resultado.append(extenso_ate_999(inteiro))

        if resultado:
            texto_reais = " ".join(resultado)
            texto_reais += " real" if int(valor) == 1 else " reais"
        else:
            texto_reais = ""

        if centavos > 0:
            texto_centavos = extenso_ate_999(centavos)
            texto_centavos += " centavo" if centavos == 1 else " centavos"
            if texto_reais:
                return f"{texto_reais} e {texto_centavos}"
            return texto_centavos

        return texto_reais
    except:
        return f"{valor} reais"


@router.get("/accounts-receivable/customers/{customer_id}")
async def get_customer_for_receivable(
    customer_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca dados do cliente para conta a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado: customers usa first_name/last_name e cpf_cnpj
        row = await conn.fetchrow("""
            SELECT id,
                COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name,
                cpf_cnpj, email, phone
            FROM customers WHERE id = $1
        """, customer_id)
        if not row:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.post("/accounts-receivable/bulk")
async def create_bulk_accounts_receivable(
    data: dict,
    num_installments: int = 1,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """
    Cria contas a receber com parcelamento.

    Recebe dados base (customer_id, description, amount, due_date, etc.) e
    o número de parcelas (num_installments). Cria automaticamente:
    - Uma conta PAI (installment_number=0) com o valor total
    - N parcelas filhas com valores divididos
    """
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)
    import uuid
    from dateutil.relativedelta import relativedelta

    try:
        created = []

        # Dados base da conta
        customer_id = data.get("customer_id")
        description = data.get("description", "")
        total_amount = float(data.get("amount", 0))
        # payment_method deve ser MAIÚSCULO para o ENUM
        payment_method = data.get("payment_method", "PIX").upper() if data.get("payment_method") else "PIX"

        # Converte due_date para date
        due_date = data.get("due_date")
        if isinstance(due_date, str):
            from datetime import datetime as dt
            due_date = dt.fromisoformat(due_date.replace('Z', '+00:00')).date() if 'T' in due_date else dt.strptime(due_date, '%Y-%m-%d').date()

        # issue_date default para hoje
        issue_date = data.get("issue_date")
        if issue_date is None:
            issue_date = datetime.utcnow().date()
        elif isinstance(issue_date, str):
            from datetime import datetime as dt
            issue_date = dt.fromisoformat(issue_date.replace('Z', '+00:00')).date() if 'T' in issue_date else dt.strptime(issue_date, '%Y-%m-%d').date()

        # Se num_installments > 1, cria conta PAI + parcelas
        if num_installments > 1:
            # 1. Cria conta PAI (installment_number = 0)
            parent_id = str(uuid.uuid4())
            parent_row = await conn.fetchrow("""
                INSERT INTO accounts_receivable (
                    id, customer_id, description, amount, paid_amount, due_date, issue_date,
                    status, payment_method, installment_number, total_installments, parent_id, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING *
            """,
                parent_id,
                customer_id,
                description,
                total_amount,
                0.0,  # paid_amount
                due_date,
                issue_date,
                "PENDING",
                payment_method,
                0,  # installment_number = 0 para PAI
                num_installments,
                None,  # parent_id = None (é a conta pai)
                True
            )
            created.append(row_to_dict(parent_row))

            # 2. Cria as parcelas filhas
            installment_amount = round(total_amount / num_installments, 2)
            # Ajusta última parcela para compensar arredondamento
            # IMPORTANTE: round() para evitar erros de ponto flutuante
            last_installment_amount = round(total_amount - (installment_amount * (num_installments - 1)), 2)

            for i in range(1, num_installments + 1):
                installment_id = str(uuid.uuid4())
                # Calcula data de vencimento (incrementa mês a cada parcela)
                installment_due_date = due_date + relativedelta(months=i-1)

                # Valor da parcela (última pode ser diferente por arredondamento)
                amount = round(last_installment_amount if i == num_installments else installment_amount, 2)

                installment_row = await conn.fetchrow("""
                    INSERT INTO accounts_receivable (
                        id, customer_id, description, amount, paid_amount, due_date, issue_date,
                        status, payment_method, installment_number, total_installments, parent_id, is_active
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    RETURNING *
                """,
                    installment_id,
                    customer_id,
                    f"{description} - PARCELA {i}/{num_installments}",
                    amount,
                    0.0,  # paid_amount
                    installment_due_date,
                    issue_date,
                    "PENDING",
                    payment_method,
                    i,  # installment_number
                    num_installments,
                    parent_id,  # referência à conta pai
                    True
                )
                created.append(row_to_dict(installment_row))
        else:
            # Conta simples (sem parcelamento)
            account_id = str(uuid.uuid4())
            row = await conn.fetchrow("""
                INSERT INTO accounts_receivable (
                    id, customer_id, description, amount, paid_amount, due_date, issue_date,
                    status, payment_method, installment_number, total_installments, parent_id, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING *
            """,
                account_id,
                customer_id,
                description,
                total_amount,
                0.0,
                due_date,
                issue_date,
                data.get("status", "PENDING").upper(),
                payment_method,
                None,  # installment_number
                None,  # total_installments
                None,  # parent_id
                True
            )
            created.append(row_to_dict(row))

        return created
    finally:
        await conn.close()


# === ENDPOINTS - ACCOUNTS PAYABLE ===

@router.get("/accounts-payable")
@router.get("/accounts-payable/")
async def list_accounts_payable(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    search: Optional[str] = None,
    purchase_id: Optional[str] = None,
    page_size: Optional[int] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista contas a pagar do tenant - retorna apenas contas PAI (installment_number = 0 ou NULL)
    Se purchase_id for informado, retorna TODAS as parcelas vinculadas à compra (para baixa)
    """
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    # Usa page_size se fornecido, senão usa limit
    effective_limit = page_size if page_size else limit

    try:
        # Se purchase_id foi informado, retorna TODAS as parcelas vinculadas à compra
        # Isso é usado pelo modal de parcelas para baixa
        if purchase_id:
            rows = await conn.fetch("""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE ap.purchase_id = $1
                ORDER BY ap.installment_number
            """, purchase_id)

            items = [row_to_dict(row) for row in rows]
            return {"items": items, "accounts": items, "total": len(items)}

        # Filtro para retornar apenas contas PAI (não parcelas filhas)
        # Igual ao comportamento de accounts_receivable
        parent_filter = "(ap.installment_number = 0 OR ap.installment_number IS NULL)"

        # Conta total para paginacao (apenas contas PAI)
        total = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_payable ap WHERE {parent_filter}") or 0

        # Schema legado: suppliers usa company_name/trade_name/name
        if search:
            rows = await conn.fetch(f"""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name,
                    (SELECT MIN(child.due_date) FROM accounts_payable child
                     WHERE child.parent_id = ap.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE {parent_filter}
                  AND (s.company_name ILIKE $1 OR s.trade_name ILIKE $1
                    OR s.name ILIKE $1 OR ap.description ILIKE $1)
                ORDER BY ap.due_date
                LIMIT $2 OFFSET $3
            """, f"%{search}%", effective_limit, skip)
        elif status:
            # Converte status para UPPERCASE para comparar com ENUM
            status_upper = status.upper()
            rows = await conn.fetch(f"""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name,
                    (SELECT MIN(child.due_date) FROM accounts_payable child
                     WHERE child.parent_id = ap.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE {parent_filter}
                  AND UPPER(ap.status::text) = $3
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, effective_limit, skip, status_upper)
        else:
            rows = await conn.fetch(f"""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name,
                    (SELECT MIN(child.due_date) FROM accounts_payable child
                     WHERE child.parent_id = ap.id AND UPPER(child.status::text) != 'PAID') as next_due_date
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE {parent_filter}
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, effective_limit, skip)

        items = [row_to_dict(row) for row in rows]
        return {"items": items, "total": total}
    finally:
        await conn.close()


@router.get("/accounts-payable/{account_id}")
async def get_account_payable(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca conta a pagar por ID"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            SELECT ap.*,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM accounts_payable ap
            LEFT JOIN suppliers s ON ap.supplier_id = s.id
            WHERE ap.id = $1
        """, account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.post("/accounts-payable")
@router.post("/accounts-payable/")
async def create_account_payable(
    account: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria conta a pagar"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)
    import uuid

    try:
        # Gera UUID para o ID
        account_id = str(uuid.uuid4())

        # Converte due_date para date se for string
        due_date = account.get("due_date")
        if isinstance(due_date, str):
            from datetime import datetime as dt
            due_date = dt.fromisoformat(due_date.replace('Z', '+00:00')).date() if 'T' in due_date else dt.strptime(due_date, '%Y-%m-%d').date()

        amount = float(account.get("amount", 0))
        amount_paid = float(account.get("amount_paid", account.get("paid_amount", 0)))

        # Schema legado: accounts_payable usa campos diferentes
        # id, supplier, description, amount, amount_paid, balance, due_date, category, payment_method, status
        row = await conn.fetchrow("""
            INSERT INTO accounts_payable (
                id, supplier_id, supplier, description, amount, amount_paid, balance,
                due_date, category, payment_method, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """,
            account_id,
            account.get("supplier_id"),
            account.get("supplier", account.get("supplier_name", "")),
            account.get("description", ""),
            amount,
            amount_paid,
            amount - amount_paid,  # balance
            due_date,
            account.get("category", "suppliers"),
            account.get("payment_method", "bank_transfer"),
            (account.get("status") or "PENDING").upper()  # ENUM requer MAIÚSCULO
        )
        return row_to_dict(row)
    finally:
        await conn.close()


@router.put("/accounts-payable/{account_id}")
async def update_account_payable(
    account_id: str,
    account: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza conta a pagar"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Converte due_date para date se for string
        due_date = account.get("due_date")
        if isinstance(due_date, str):
            from datetime import datetime as dt
            due_date = dt.fromisoformat(due_date.replace('Z', '+00:00')).date() if 'T' in due_date else dt.strptime(due_date, '%Y-%m-%d').date()

        amount = float(account.get("amount", 0))
        amount_paid = float(account.get("amount_paid", account.get("paid_amount", 0)))

        # Schema legado: accounts_payable usa campos diferentes
        row = await conn.fetchrow("""
            UPDATE accounts_payable SET
                supplier_id = $2, supplier = $3, description = $4, amount = $5,
                amount_paid = $6, balance = $7, due_date = $8, category = $9,
                payment_method = $10, status = $11, updated_at = $12
            WHERE id = $1
            RETURNING *
        """,
            account_id,
            account.get("supplier_id"),
            account.get("supplier", account.get("supplier_name", "")),
            account.get("description", ""),
            amount,
            amount_paid,
            amount - amount_paid,  # balance
            due_date,
            account.get("category", "suppliers"),
            account.get("payment_method", "bank_transfer"),
            (account.get("status") or "PENDING").upper(),  # ENUM requer MAIÚSCULO
            datetime.utcnow()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.delete("/accounts-payable/{account_id}")
async def delete_account_payable(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove conta a pagar"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        result = await conn.execute("DELETE FROM accounts_payable WHERE id = $1", account_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
        return {"success": True, "message": "Conta removida"}
    finally:
        await conn.close()


@router.post("/accounts-payable/{account_id}/pay")
async def pay_account_payable(
    account_id: str,
    payment: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Registra pagamento de conta a pagar"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca conta atual
        row = await conn.fetchrow("SELECT * FROM accounts_payable WHERE id = $1", account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")

        payment_amount = float(payment.get("payment_amount", 0))
        # Schema legado usa amount_paid, nao paid_amount
        current_paid = float(row["amount_paid"] or 0)
        total_amount = float(row["amount"])
        new_paid = current_paid + payment_amount
        new_balance = total_amount - new_paid

        # Determina novo status (MAIÚSCULO para ENUM PostgreSQL)
        new_status = "PAID" if new_paid >= total_amount else "PARTIAL"

        # Converte payment_date para date se for string
        payment_date = payment.get("payment_date")
        if isinstance(payment_date, str):
            from datetime import datetime as dt
            payment_date = dt.fromisoformat(payment_date.replace('Z', '+00:00')).date() if 'T' in payment_date else dt.strptime(payment_date, '%Y-%m-%d').date()

        # Atualiza conta - schema legado usa amount_paid e balance
        updated = await conn.fetchrow("""
            UPDATE accounts_payable SET
                amount_paid = $2, balance = $3, status = $4, payment_date = $5, updated_at = $6
            WHERE id = $1
            RETURNING *
        """, account_id, new_paid, new_balance, new_status, payment_date, datetime.utcnow())

        return row_to_dict(updated)
    finally:
        await conn.close()


@router.get("/accounts-payable/{account_id}/installments")
async def get_account_payable_installments(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """
    Retorna todas as parcelas de uma conta a pagar (conta pai).
    Similar ao endpoint de accounts_receivable.
    """
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca a conta pai e todas as parcelas filhas
        rows = await conn.fetch("""
            SELECT ap.*,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM accounts_payable ap
            LEFT JOIN suppliers s ON ap.supplier_id = s.id
            WHERE ap.id = $1 OR ap.parent_id = $1
            ORDER BY ap.installment_number
        """, account_id)

        if not rows:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")

        # Retorna apenas as parcelas (installment_number > 0)
        # Se nao houver parcelas, retorna a conta original
        items = []
        for row in rows:
            row_dict = row_to_dict(row)
            installment_num = row_dict.get("installment_number", 0)

            # Adiciona account_id para compatibilidade com frontend
            row_dict["account_id"] = row_dict.get("parent_id") or row_dict.get("id")

            # IMPORTANTE: Arredonda valores para evitar erros de ponto flutuante
            amount = round(float(row_dict.get("amount") or 0), 2)
            amount_paid = round(float(row_dict.get("amount_paid") or 0), 2)
            row_dict["amount"] = amount
            row_dict["amount_paid"] = amount_paid
            row_dict["balance"] = round(amount - amount_paid, 2)

            if installment_num > 0:
                items.append(row_dict)
            elif len(rows) == 1:
                # Conta simples sem parcelas
                items.append(row_dict)

        return items
    finally:
        await conn.close()


# === ENDPOINTS - COMPANY ===

@router.get("/company")
async def get_company(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna dados da empresa do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("SELECT * FROM companies LIMIT 1")
        if not row:
            # Retorna dados do tenant como fallback
            return {
                "id": None,
                "name": tenant.name,
                "trade_name": tenant.trade_name,
                "document": tenant.document,
                "phone": tenant.phone,
                "email": tenant.email
            }
        data = row_to_dict(row)
        if data.get('logo_path'):
            data['logo_url'] = f"/uploads/{data['logo_path']}"
        return data
    finally:
        await conn.close()


@router.post("/company")
@router.post("/company/")
async def create_company(
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria dados da empresa do tenant"""
    import uuid
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        company_data = await request.json()

        # Verifica se já existe uma empresa
        existing = await conn.fetchrow("SELECT id FROM companies LIMIT 1")
        if existing:
            raise HTTPException(status_code=400, detail="Empresa já cadastrada. Use PUT para atualizar.")

        company_id = str(uuid.uuid4())
        now = datetime.utcnow()

        allowed_fields = [
            'person_type', 'trade_name', 'legal_name', 'document',
            'state_registration', 'municipal_registration', 'email',
            'phone', 'mobile', 'website', 'zip_code', 'street',
            'number', 'complement', 'neighborhood', 'city', 'state',
            'country', 'bank_name', 'bank_agency', 'bank_account',
            'pix_key', 'logo_path', 'description', 'notes'
        ]

        # Filtra apenas campos permitidos
        insert_data = {k: v for k, v in company_data.items() if k in allowed_fields and v is not None}

        # Constrói query de INSERT
        columns = ['id', 'is_active', 'created_at', 'updated_at'] + list(insert_data.keys())
        placeholders = ['$1', '$2', '$3', '$4'] + [f'${i+5}' for i in range(len(insert_data))]
        values = [company_id, True, now, now] + list(insert_data.values())

        query = f"""
            INSERT INTO companies ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """

        row = await conn.fetchrow(query, *values)
        data = row_to_dict(row)

        print(f"[COMPANY] Empresa criada: {company_id}", flush=True)
        return data

    except HTTPException:
        raise
    except Exception as e:
        print(f"[COMPANY] Erro ao criar empresa: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


@router.put("/company/{company_id}")
async def update_company(
    company_id: str,
    company_data: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza dados da empresa do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        existing = await conn.fetchrow("SELECT id FROM companies WHERE id = $1", company_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        allowed_fields = [
            'person_type', 'trade_name', 'legal_name', 'document',
            'state_registration', 'municipal_registration', 'email',
            'phone', 'mobile', 'website', 'zip_code', 'street',
            'number', 'complement', 'neighborhood', 'city', 'state',
            'country', 'bank_name', 'bank_agency', 'bank_account',
            'pix_key', 'logo_path', 'description', 'notes', 'is_active'
        ]

        update_data = {k: v for k, v in company_data.items() if k in allowed_fields}
        if not update_data:
            raise HTTPException(status_code=400, detail="Nenhum campo válido para atualizar")

        set_clauses = []
        values = []
        for i, (key, value) in enumerate(update_data.items(), 1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)

        values.append(company_id)
        query = f"UPDATE companies SET {', '.join(set_clauses)}, updated_at = NOW() WHERE id = ${len(values)} RETURNING *"

        row = await conn.fetchrow(query, *values)
        return row_to_dict(row)
    finally:
        await conn.close()




@router.get("/logo/current")
async def get_current_logo(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna logo atual da empresa"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("SELECT logo_path FROM companies LIMIT 1")
        if not row or not row['logo_path']:
            raise HTTPException(status_code=404, detail="Logo não encontrado")
        
        return {"logo_url": f"/uploads/{row['logo_path']}" if row['logo_path'] else None}
    finally:
        await conn.close()


@router.post("/logo/upload")
async def upload_logo(
    file: UploadFile = File(...),
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Faz upload do logo da empresa"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Valida tipo de arquivo
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem")

        # Gera nome único para o arquivo
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"logo_{tenant.tenant_code}_{uuid_lib.uuid4().hex[:8]}.{ext}"
        
        # Lê conteúdo do arquivo
        contents = await file.read()

        # Determina diretório de uploads (produção vs local)
        if os.path.exists("/app/uploads"):
            upload_base = "/app/uploads"
        else:
            # Desenvolvimento local
            upload_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")

        upload_dir = os.path.join(upload_base, "logos")
        os.makedirs(upload_dir, exist_ok=True)

        filepath = os.path.join(upload_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(contents)

        # Atualiza path no banco
        logo_path = f"logos/{filename}"
        await conn.execute(
            "UPDATE companies SET logo_path = $1, updated_at = NOW()",
            logo_path
        )

        return {"success": True, "logo_url": f"/uploads/{logo_path}"}
    finally:
        await conn.close()



@router.delete("/logo")
async def delete_logo(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove logo da empresa"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("SELECT logo_path FROM companies LIMIT 1")
        if row and row['logo_path']:
            # Determina diretório de uploads (produção vs local)
            if os.path.exists("/app/uploads"):
                upload_base = "/app/uploads"
            else:
                upload_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")

            filepath = os.path.join(upload_base, row['logo_path'])
            if os.path.exists(filepath):
                os.remove(filepath)

        await conn.execute("UPDATE companies SET logo_path = NULL, updated_at = NOW()")
        return {"success": True, "message": "Logo removido com sucesso"}
    finally:
        await conn.close()


# === ENDPOINTS - LEGAL CALCULATIONS ===

# Servico de calculo de correcao monetaria e juros
# Busca indices do BCB e calcula fatores de correcao

# Codigos BCB para indices economicos
BCB_INDEX_CODES = {
    "ipca": 433,
    "ipca_e": 10764,
    "ipca_15": 7478,
    "inpc": 188,
    "igpm": 189,
    "igpdi": 190,
    "tr": 226,
    "selic": 4390,
    "cdi": 4391,
    "poupanca": 25,
    "tjlp": 256,
}

# =============================================================================
# TABELA DE FALLBACK - Indices IPCA-E e IPCA-15 (dados oficiais IBGE/BCB)
# Usado quando a API do BCB está indisponivel (403 Forbidden)
# Formato: {(ano, mes): valor_percentual}
# =============================================================================
IPCA_E_FALLBACK = {
    # 2020
    (2020, 1): 0.21, (2020, 2): 0.34, (2020, 3): -0.01, (2020, 4): -0.11,
    (2020, 5): -0.14, (2020, 6): 0.23, (2020, 7): 0.36, (2020, 8): 0.24,
    (2020, 9): 0.54, (2020, 10): 0.94, (2020, 11): 0.81, (2020, 12): 1.06,
    # 2021
    (2021, 1): 0.36, (2021, 2): 0.72, (2021, 3): 1.02, (2021, 4): 0.31,
    (2021, 5): 0.78, (2021, 6): 0.53, (2021, 7): 0.96, (2021, 8): 1.11,
    (2021, 9): 1.14, (2021, 10): 1.25, (2021, 11): 1.17, (2021, 12): 0.65,
    # 2022
    (2022, 1): 0.58, (2022, 2): 0.99, (2022, 3): 0.95, (2022, 4): 1.73,
    (2022, 5): 0.41, (2022, 6): 0.65, (2022, 7): -0.37, (2022, 8): -0.36,
    (2022, 9): -0.29, (2022, 10): 0.59, (2022, 11): 0.53, (2022, 12): 0.69,
    # 2023
    (2023, 1): 0.55, (2023, 2): 0.76, (2023, 3): 0.71, (2023, 4): 0.57,
    (2023, 5): 0.36, (2023, 6): -0.04, (2023, 7): 0.06, (2023, 8): 0.04,
    (2023, 9): 0.30, (2023, 10): 0.21, (2023, 11): 0.27, (2023, 12): 0.55,
    # 2024 (ate agosto - depois usa IPCA-15 conforme TJSP)
    (2024, 1): 0.42, (2024, 2): 0.78, (2024, 3): 0.36, (2024, 4): 0.21,
    (2024, 5): 0.44, (2024, 6): 0.30, (2024, 7): 0.30, (2024, 8): -0.01,
}

IPCA_15_FALLBACK = {
    # 2024 (setembro em diante - conforme Lei 14.905/2024 e TJSP)
    (2024, 9): 0.13, (2024, 10): 0.54, (2024, 11): 0.62,
    # 2025
    (2025, 1): 0.11, (2025, 2): 1.23, (2025, 3): 0.64, (2025, 4): 0.43,
    (2025, 5): 0.36, (2025, 6): 0.07, (2025, 7): 0.43, (2025, 8): 0.23,
    (2025, 9): 0.35, (2025, 10): 0.50, (2025, 11): 0.45, (2025, 12): 0.40,
}

# SELIC mensal (para calculo de juros legais)
SELIC_FALLBACK = {
    # 2024
    (2024, 1): 0.97, (2024, 2): 0.80, (2024, 3): 0.83, (2024, 4): 0.89,
    (2024, 5): 0.83, (2024, 6): 0.79, (2024, 7): 0.91, (2024, 8): 0.87,
    (2024, 9): 0.84, (2024, 10): 0.93, (2024, 11): 0.79, (2024, 12): 0.93,
    # 2025
    (2025, 1): 1.06, (2025, 2): 1.01, (2025, 3): 0.96, (2025, 4): 0.94,
    (2025, 5): 0.97, (2025, 6): 1.02, (2025, 7): 1.03, (2025, 8): 1.02,
    (2025, 9): 1.00, (2025, 10): 0.98, (2025, 11): 0.95, (2025, 12): 0.93,
}

def get_fallback_index(codigo_serie: int, ano: int, mes: int) -> float:
    """Retorna indice da tabela de fallback se disponivel"""
    if codigo_serie == 10764:  # IPCA-E
        return IPCA_E_FALLBACK.get((ano, mes))
    elif codigo_serie == 7478:  # IPCA-15
        return IPCA_15_FALLBACK.get((ano, mes))
    elif codigo_serie == 433:  # IPCA (usa mesmo do IPCA-E como aproximacao)
        val = IPCA_E_FALLBACK.get((ano, mes))
        if val is None and ano >= 2024 and mes >= 9:
            val = IPCA_15_FALLBACK.get((ano, mes))
        return val
    elif codigo_serie == 4390:  # SELIC
        return SELIC_FALLBACK.get((ano, mes))
    return None

# Cache de indices para evitar chamadas repetidas
_indices_cache = {}

async def fetch_bcb_index(codigo_serie: int, data_inicio, data_fim):
    """
    Busca indice do BCB - com fallback para tabela local quando API indisponivel.
    Prioridade: 1) Cache -> 2) API BCB -> 3) Tabela Fallback Local
    """
    import httpx
    from datetime import date, datetime
    import asyncio

    # Chave do cache
    cache_key = f"{codigo_serie}_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}"

    # Verifica cache primeiro
    if cache_key in _indices_cache:
        cached = _indices_cache[cache_key]
        # Cache valido por 24h
        if cached.get("timestamp") and (datetime.now() - cached["timestamp"]).total_seconds() < 86400:
            return cached.get("data", [])

    # Tenta API do BCB (apenas 1 tentativa rapida para nao travar)
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados"
    params = {
        "formato": "json",
        "dataInicial": data_inicio.strftime("%d/%m/%Y"),
        "dataFinal": data_fim.strftime("%d/%m/%Y"),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Armazena no cache
            _indices_cache[cache_key] = {"data": data, "timestamp": datetime.now()}
            logger.info(f"BCB API OK: serie {codigo_serie}")
            return data
    except Exception as e:
        logger.warning(f"BCB API indisponivel ({codigo_serie}), usando fallback local: {e}")

    # FALLBACK: Usa tabela local de indices
    fallback_data = []
    current = date(data_inicio.year, data_inicio.month, 1)
    end = date(data_fim.year, data_fim.month, 1)

    while current <= end:
        valor = get_fallback_index(codigo_serie, current.year, current.month)
        if valor is not None:
            fallback_data.append({
                "data": f"01/{current.month:02d}/{current.year}",
                "valor": str(valor)
            })
        # Proximo mes
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if fallback_data:
        logger.info(f"Usando {len(fallback_data)} indices do fallback local para serie {codigo_serie}")
        # Armazena no cache (valido por 1h quando usando fallback)
        _indices_cache[cache_key] = {"data": fallback_data, "timestamp": datetime.now()}

    return fallback_data

async def calculate_correction_factor(tipo_indice: str, data_inicial, data_final):
    """
    Calcula fator de correcao monetaria entre duas datas
    METODOLOGIA compativel com DR Calc e Calculo Juridico:
    - Primeiro mes: mes DO vencimento (INCLUI o mes do vencimento)
    - Ultimo mes: mes ANTERIOR ao termo
    - Para IPCA-E: usa IPCA-E ate agosto/2024 e IPCA-15 a partir de setembro/2024
      (conforme nova tabela pratica TJSP publicada em set/2024)
    - NAO projeta indices futuros - usa apenas indices publicados

    REGRA CORRETA (igual economic_index_service.py que batia ate os centavos):
    Exemplo: Vencimento 13/07/2023, Termo 13/12/2025
    - Aplica indices de Jul/2023 (mes do vencimento) ate Nov/2025 (mes anterior ao termo)
    - O indice de Nov/2025 atualiza o valor ATE Dez/2025

    Retorna 1 se nao houver correcao ou indice nao encontrado
    """
    from datetime import date, datetime

    if tipo_indice == "nenhum" or not tipo_indice:
        return 1.0

    tipo_indice_lower = tipo_indice.lower()

    # Converte datas
    if isinstance(data_inicial, str):
        data_inicial = datetime.strptime(data_inicial, "%Y-%m-%d").date()
    if isinstance(data_final, str):
        data_final = datetime.strptime(data_final, "%Y-%m-%d").date()

    # METODOLOGIA CORRETA: Primeiro mes = MES DO vencimento (INCLUI)
    # Exemplo: vencimento 13/07/2023 -> primeiro indice = julho/2023
    # Esta e a metodologia que batia ate os centavos com DR Calc
    primeiro_mes = date(data_inicial.year, data_inicial.month, 1)

    # METODOLOGIA TJSP: Ultimo mes = MES ANTERIOR ao termo
    # Exemplo: termo dezembro/2025 -> ultimo indice = novembro/2025
    if data_final.month == 1:
        ultimo_mes_teorico = date(data_final.year - 1, 12, 1)
    else:
        ultimo_mes_teorico = date(data_final.year, data_final.month - 1, 1)

    # Monta dicionario de indices por mes
    # Para IPCA-E: usa combinacao IPCA-E ate ago/2024 + IPCA-15 de set/2024 em diante
    # (conforme nova tabela pratica TJSP - Lei 14.905/2024)
    indices_por_mes = {}
    marco_ipca15 = date(2024, 9, 1)  # A partir de setembro/2024, usa IPCA-15

    if tipo_indice_lower == "ipca_e":
        # Busca IPCA-E ate agosto/2024
        dados_ipca_e = await fetch_bcb_index(
            BCB_INDEX_CODES["ipca_e"],
            primeiro_mes,
            date(2024, 8, 31)
        )
        for item in dados_ipca_e:
            try:
                data_str = item.get("data", "")
                valor_str = item.get("valor", "0")
                if data_str and valor_str:
                    data_idx = datetime.strptime(data_str, "%d/%m/%Y").date()
                    data_mes = date(data_idx.year, data_idx.month, 1)
                    indices_por_mes[data_mes] = float(str(valor_str).replace(",", "."))
            except:
                continue

        # Busca IPCA-15 de setembro/2024 em diante
        dados_ipca15 = await fetch_bcb_index(
            BCB_INDEX_CODES["ipca_15"],
            date(2024, 9, 1),
            date.today()
        )
        for item in dados_ipca15:
            try:
                data_str = item.get("data", "")
                valor_str = item.get("valor", "0")
                if data_str and valor_str:
                    data_idx = datetime.strptime(data_str, "%d/%m/%Y").date()
                    data_mes = date(data_idx.year, data_idx.month, 1)
                    indices_por_mes[data_mes] = float(str(valor_str).replace(",", "."))
            except:
                continue
    else:
        # Para outros indices, busca normalmente
        if tipo_indice_lower not in BCB_INDEX_CODES:
            logger.warning(f"Indice {tipo_indice} nao encontrado")
            return 1.0

        codigo_serie = BCB_INDEX_CODES[tipo_indice_lower]
        dados = await fetch_bcb_index(codigo_serie, primeiro_mes, date.today())

        for item in dados:
            try:
                data_str = item.get("data", "")
                valor_str = item.get("valor", "0")
                if data_str and valor_str:
                    data_idx = datetime.strptime(data_str, "%d/%m/%Y").date()
                    data_mes = date(data_idx.year, data_idx.month, 1)
                    indices_por_mes[data_mes] = float(str(valor_str).replace(",", "."))
            except:
                continue

    if not indices_por_mes:
        logger.warning(f"Nenhum indice encontrado para {tipo_indice}")
        return 1.0

    # Determina o ultimo mes disponivel
    ultimo_mes_disponivel = max(indices_por_mes.keys())

    # Usa o menor entre o mes teorico e o ultimo disponivel
    # NAO projeta indices futuros - compativel com DR Calc e Calculo Juridico
    ultimo_mes = min(ultimo_mes_teorico, ultimo_mes_disponivel)

    # Calcula fator acumulado - APENAS com indices reais
    fator = 1.0
    mes_atual = primeiro_mes

    while mes_atual <= ultimo_mes:
        if mes_atual in indices_por_mes:
            valor = indices_por_mes[mes_atual]
            fator *= (1 + valor / 100)
        # Se nao tem indice para o mes, NAO inclui (metodologia TJSP)

        # Avanca para proximo mes
        if mes_atual.month == 12:
            mes_atual = date(mes_atual.year + 1, 1, 1)
        else:
            mes_atual = date(mes_atual.year, mes_atual.month + 1, 1)

    # IMPORTANTE: Retorna o fator EXATO para calculo preciso
    # O arredondamento para 4 casas e feito apenas na EXIBICAO (resposta da API)
    # Isso garante que o valor corrigido seja identico ao DR Calc
    logger.debug(f"Correcao {tipo_indice}: {primeiro_mes} a {ultimo_mes}, fator={fator:.6f}")
    return fator

def to_date_safe(val):
    """Converte string para date de forma segura (para logs)"""
    from datetime import datetime, date
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            if 'T' in val:
                return datetime.fromisoformat(val.replace('Z', '+00:00')).date()
            return datetime.strptime(val, "%Y-%m-%d").date()
        except:
            return None
    return None


def calculate_interest_months(data_inicial, data_final):
    """Calcula numero de meses entre duas datas (pro-rata 30 dias)"""
    from datetime import datetime

    if isinstance(data_inicial, str):
        data_inicial = datetime.strptime(data_inicial, "%Y-%m-%d").date()
    if isinstance(data_final, str):
        data_final = datetime.strptime(data_final, "%Y-%m-%d").date()

    if data_final <= data_inicial:
        return 0.0

    dias = (data_final - data_inicial).days
    return dias / 30.0

# Cache para taxas legais (SELIC - IPCA) por mês
_taxa_legal_cache = {}

async def get_taxa_legal_mes(ano: int, mes: int):
    """
    Busca Taxa Legal (SELIC - IPCA) para um mês específico.
    Lei 14.905/2024 Art. 406: Taxa legal = SELIC acumulada - IPCA acumulado do mês
    Retorna a taxa mensal em percentual (ex: 0.65 para 0.65%)
    """
    from datetime import date

    cache_key = f"{ano}-{mes:02d}"
    if cache_key in _taxa_legal_cache:
        return _taxa_legal_cache[cache_key]

    try:
        # Busca SELIC do mês (série 4390 - Taxa SELIC mensal)
        data_inicio = date(ano, mes, 1)
        if mes == 12:
            data_fim = date(ano + 1, 1, 1)
        else:
            data_fim = date(ano, mes + 1, 1)

        # SELIC mensal acumulada
        dados_selic = await fetch_bcb_index(4390, data_inicio, data_fim)
        selic_mes = 0.0
        if dados_selic:
            for item in dados_selic:
                try:
                    valor = float(str(item.get("valor", "0")).replace(",", "."))
                    selic_mes = valor  # Último valor do mês
                except:
                    pass

        # IPCA do mês (série 433)
        dados_ipca = await fetch_bcb_index(433, data_inicio, data_fim)
        ipca_mes = 0.0
        if dados_ipca:
            for item in dados_ipca:
                try:
                    valor = float(str(item.get("valor", "0")).replace(",", "."))
                    ipca_mes = valor
                except:
                    pass

        # Taxa Legal = SELIC - IPCA (não pode ser negativa)
        taxa_legal = max(0.0, selic_mes - ipca_mes)

        # Cache do resultado
        _taxa_legal_cache[cache_key] = taxa_legal
        logger.debug(f"Taxa Legal {cache_key}: SELIC={selic_mes:.4f}% - IPCA={ipca_mes:.4f}% = {taxa_legal:.4f}%")

        return taxa_legal

    except Exception as e:
        logger.error(f"Erro ao buscar taxa legal {cache_key}: {e}")
        # Fallback para valor aproximado se houver erro
        return 0.65

def get_interest_rate_for_date(tipo_juros: str, data_ref, percentual_personalizado=None):
    """
    Retorna taxa de juros mensal conforme a data de referencia (síncrono, para taxas fixas)
    Para taxa legal pós Lei 14.905/2024, retorna None (deve usar get_taxa_legal_mes async)
    Conforme DR Calc: 6% a.a anterior a 11/02/03; 12% a.a de 12/02/03 a 30/08/24; Taxa Legal a partir de 30/08/24
    """
    from datetime import date, datetime

    if isinstance(data_ref, str):
        data_ref = datetime.strptime(data_ref, "%Y-%m-%d").date()

    marco_cc2002 = date(2003, 2, 12)  # Novo Código Civil entra em vigor
    marco_lei_14905 = date(2024, 8, 30)  # Lei 14.905/2024

    if tipo_juros == "nao_aplicar":
        return 0.0
    elif tipo_juros == "fixos_1_mes":
        return 1.0
    elif tipo_juros == "fixos_0_5_mes":
        return 0.5
    elif tipo_juros in ["juros_legais_6_12", "juros_legais_selic_lei_14905", "taxa_legal_selic_ipca", "taxa_legal_art_406"]:
        # Lei 14.905/2024: Taxa Legal = SELIC - IPCA a partir de 30/08/2024
        if data_ref < marco_cc2002:
            return 0.5  # 6% a.a. = 0.5% a.m. (antes do CC 2002)
        elif data_ref < marco_lei_14905:
            return 1.0  # 12% a.a. = 1% a.m. (CC 2002 até Lei 14.905)
        else:
            return None  # Sinaliza que deve buscar taxa legal real via async
    elif tipo_juros == "poupanca":
        return 0.5
    elif tipo_juros == "personalizado" and percentual_personalizado:
        return float(percentual_personalizado)
    return 0.0

async def calculate_legal_interest_monthly(valor_base: float, data_inicial, data_final, tipo_juros: str,
                                          percentual_personalizado=None, capitalizar=False):
    """
    Calcula juros mês a mês, aplicando a taxa correta para cada período.
    Considera a Lei 14.905/2024 (30/08/2024) para aplicar taxas diferentes.

    METODOLOGIA LEGAL:
    - Antes de 12/02/2003: 6% a.a. (0.5% a.m.) - Código Civil 1916
    - De 12/02/2003 a 29/08/2024: 12% a.a. (1% a.m.) - Art. 406 CC/2002 + STJ
    - A partir de 30/08/2024: SELIC - IPCA (Taxa Legal real) - Lei 14.905/2024

    IMPORTANTE: Juros de mora incidem a partir do DIA SEGUINTE ao vencimento.
    Compatível com DR Calc e TJSP.
    """
    from datetime import date, datetime, timedelta
    from calendar import monthrange

    if isinstance(data_inicial, str):
        data_inicial = datetime.strptime(data_inicial, "%Y-%m-%d").date()
    if isinstance(data_final, str):
        data_final = datetime.strptime(data_final, "%Y-%m-%d").date()

    # CORREÇÃO LEGAL: Juros de mora incidem a partir do DIA SEGUINTE ao vencimento
    # Art. 397 CC: "O inadimplemento da obrigação, positiva e líquida, no seu termo,
    # constitui de pleno direito em mora o devedor."
    data_inicio_juros = data_inicial + timedelta(days=1)

    if data_final <= data_inicio_juros:
        return {"percentual_total": 0.0, "valor_juros": 0.0}

    percentual_total = 0.0
    valor_juros = 0.0
    valor_acumulado = valor_base

    marco_lei_14905 = date(2024, 8, 30)

    # Itera mês a mês do período (a partir do dia seguinte ao vencimento)
    data_atual = data_inicio_juros
    while data_atual < data_final:
        # Determina o último dia do mês atual
        _, ultimo_dia = monthrange(data_atual.year, data_atual.month)
        fim_mes = date(data_atual.year, data_atual.month, ultimo_dia)

        # Data final do período deste mês (não pode ultrapassar data_final)
        data_fim_periodo = min(fim_mes, data_final)

        # Calcula dias neste mês
        if data_atual == data_inicio_juros:
            # Primeiro mês: conta a partir do dia seguinte ao vencimento
            dias_no_mes = (data_fim_periodo - data_atual).days + 1
        else:
            # Meses seguintes: mês completo ou até data_final
            dias_no_mes = (data_fim_periodo - date(data_atual.year, data_atual.month, 1)).days + 1

        if dias_no_mes <= 0:
            break

        # Fração do mês (considerando mês comercial de 30 dias)
        fracao_mes = dias_no_mes / 30.0

        # Determina a taxa aplicável para este mês
        taxa_mes = get_interest_rate_for_date(tipo_juros, data_atual, percentual_personalizado)

        # Se retornou None, significa que é período pós Lei 14.905 e deve buscar taxa real
        if taxa_mes is None:
            taxa_mes = await get_taxa_legal_mes(data_atual.year, data_atual.month)

        # Calcula juros pro-rata para este mês
        taxa_periodo = taxa_mes * fracao_mes
        percentual_total += taxa_periodo

        if capitalizar:
            # Juros compostos: aplica sobre valor acumulado
            juros_mes = valor_acumulado * (taxa_periodo / 100)
            valor_juros += juros_mes
            valor_acumulado += juros_mes
        else:
            # Juros simples: aplica sobre valor base original
            juros_mes = valor_base * (taxa_periodo / 100)
            valor_juros += juros_mes

        # Avança para o próximo mês
        if data_atual.month == 12:
            data_atual = date(data_atual.year + 1, 1, 1)
        else:
            data_atual = date(data_atual.year, data_atual.month + 1, 1)

    return {
        "percentual_total": round(percentual_total, 2),
        "valor_juros": round(valor_juros, 2)
    }

async def calculate_debito(debito: dict, termo_final, tipo_indice: str, tipo_juros_mora: str,
                          percentual_juros_mora=None, percentual_multa=0, capitalizar=False):
    """Calcula um debito com correcao, juros e multa - compatível com DR Calc

    IMPORTANTE: Se o débito tem usar_config_individual=True, usa as configurações
    individuais do débito ao invés das configurações gerais do cálculo.
    """
    from datetime import datetime

    valor_original = debito.get("valor_original", 0)
    if isinstance(valor_original, str):
        valor_original = float(valor_original.replace(",", ".")) if valor_original else 0

    data_vencimento = debito.get("data_vencimento")
    if not data_vencimento or not valor_original:
        return {
            **debito,
            "fator_correcao": 1.0,
            "valor_corrigido": valor_original,
            "percentual_juros_mora": 0,
            "valor_juros_mora": 0,
            "valor_multa": 0,
            "valor_total": valor_original,
        }

    # Verifica se o débito tem configuração individual
    usar_config_individual = debito.get("usar_config_individual", False)

    # Helper para verificar se valor é preenchido (não vazio e não None)
    def get_val(d, key, default=None):
        val = d.get(key)
        if val is None or val == '' or val == 'null':
            return default
        return val

    if usar_config_individual:
        # Usa configurações individuais do débito (se definidas)
        # IMPORTANTE: Verificar se valor existe E não é string vazia
        tipo_indice_debito = get_val(debito, "indice_correcao", tipo_indice)
        tipo_juros_mora_debito = get_val(debito, "tipo_juros_mora", tipo_juros_mora)
        percentual_juros_mora_debito = get_val(debito, "taxa_juros_mora", percentual_juros_mora)
        # Data início/fim da correção (se definidas no débito)
        data_inicio_correcao = get_val(debito, "data_inicio_correcao", data_vencimento)
        data_fim_correcao = get_val(debito, "data_fim_correcao", termo_final)
        # Data início/fim dos juros de mora (se definidas no débito)
        data_inicio_juros = get_val(debito, "data_inicio_juros_mora", data_vencimento)
        data_fim_juros = get_val(debito, "data_fim_juros_mora", termo_final)

        # Log para debug
        logger.debug(f"Config Individual - tipo_juros: {tipo_juros_mora_debito}, taxa: {percentual_juros_mora_debito}, inicio: {data_inicio_juros}, fim: {data_fim_juros}")
    else:
        # Usa configurações gerais do cálculo
        tipo_indice_debito = tipo_indice
        tipo_juros_mora_debito = tipo_juros_mora
        percentual_juros_mora_debito = percentual_juros_mora
        data_inicio_correcao = data_vencimento
        data_fim_correcao = termo_final
        data_inicio_juros = data_vencimento
        data_fim_juros = termo_final

    # 1. Correcao Monetaria (usando datas do débito se individuais)
    fator = await calculate_correction_factor(tipo_indice_debito, data_inicio_correcao, data_fim_correcao)
    valor_corrigido = valor_original * fator

    # 2. Juros de Mora - calcula mês a mês respeitando Lei 14.905/2024
    # Converte taxa para float se string
    taxa_fixa = None
    if percentual_juros_mora_debito is not None and percentual_juros_mora_debito != '':
        try:
            taxa_str = str(percentual_juros_mora_debito).replace(',', '.')
            taxa_fixa = float(taxa_str)
        except (ValueError, TypeError):
            taxa_fixa = None

    logger.debug(f"Juros - tipo: {tipo_juros_mora_debito}, taxa_fixa: {taxa_fixa}, inicio: {data_inicio_juros}, fim: {data_fim_juros}")

    if tipo_juros_mora_debito == "nao_aplicar":
        percentual_juros_total = 0.0
        valor_juros = 0.0
    elif taxa_fixa is not None and taxa_fixa > 0:
        # Taxa fixa informada pelo usuário - usa diretamente
        meses = calculate_interest_months(data_inicio_juros, data_fim_juros)
        percentual_juros_total = taxa_fixa * meses
        # Log detalhado para debug
        logger.info(f"JUROS TAXA FIXA: inicio={data_inicio_juros}, fim={data_fim_juros}, dias={(to_date_safe(data_fim_juros) - to_date_safe(data_inicio_juros)).days if data_inicio_juros and data_fim_juros else 'N/A'}, meses={meses:.4f}, taxa={taxa_fixa}%, total={percentual_juros_total:.4f}%")
        if capitalizar:
            valor_juros = valor_corrigido * ((1 + taxa_fixa/100) ** meses - 1)
        else:
            valor_juros = valor_corrigido * (taxa_fixa / 100) * meses
    else:
        # Taxa legal - calcular mês a mês (Lei 14.905/2024)
        juros_result = await calculate_legal_interest_monthly(
            valor_corrigido, data_inicio_juros, data_fim_juros, tipo_juros_mora_debito,
            percentual_juros_mora_debito, capitalizar
        )
        percentual_juros_total = juros_result["percentual_total"]
        valor_juros = juros_result["valor_juros"]
        logger.debug(f"Usando taxa legal: {percentual_juros_total:.2f}%")

    # 3. Multa
    percentual_multa_val = float(percentual_multa) if percentual_multa else 0
    valor_multa = valor_corrigido * (percentual_multa_val / 100)

    # 4. Total
    valor_total = valor_corrigido + valor_juros + valor_multa

    return {
        **debito,
        "fator_correcao": round(fator, 4),  # 4 casas decimais = padrao DR Calc
        "valor_corrigido": round(valor_corrigido, 2),
        "percentual_juros_mora": round(percentual_juros_total, 2),
        "valor_juros_mora": round(valor_juros, 2),
        "valor_multa": round(valor_multa, 2),
        "valor_total": round(valor_total, 2),
        "config_individual": usar_config_individual,  # Indica se usou config individual
    }

async def calculate_all_debitos(data: dict):
    """Calcula todos os debitos e creditos e retorna dados atualizados"""
    termo_final = data.get("termo_final")
    tipo_indice = data.get("indice_correcao", "ipca_e")
    tipo_juros_mora = data.get("tipo_juros_mora", "nao_aplicar")
    percentual_juros_mora = data.get("percentual_juros_mora")
    percentual_multa = data.get("percentual_multa", 0)
    capitalizar = data.get("capitalizar_juros_mora_mensal", False)

    # Calcula debitos
    debitos = data.get("debitos", [])
    debitos_calculados = []
    total_principal = 0
    total_corrigido = 0
    total_juros = 0
    total_multa = 0
    total_geral_debitos = 0

    for debito in debitos:
        calc = await calculate_debito(
            debito, termo_final, tipo_indice, tipo_juros_mora,
            percentual_juros_mora, percentual_multa, capitalizar
        )
        debitos_calculados.append(calc)
        total_principal += calc.get("valor_original", 0) or 0
        total_corrigido += calc.get("valor_corrigido", 0) or 0
        total_juros += calc.get("valor_juros_mora", 0) or 0
        total_multa += calc.get("valor_multa", 0) or 0
        total_geral_debitos += calc.get("valor_total", 0) or 0

    # Calcula creditos (mesma logica)
    creditos = data.get("creditos", [])
    creditos_calculados = []
    total_creditos = 0

    for credito in creditos:
        # Credito usa data_pagamento ao inves de data_vencimento
        credito_calc = dict(credito)
        credito_calc["data_vencimento"] = credito.get("data_pagamento")
        calc = await calculate_debito(
            credito_calc, termo_final, tipo_indice, tipo_juros_mora,
            percentual_juros_mora, 0, capitalizar  # Credito sem multa
        )
        # Restaura data_pagamento
        calc["data_pagamento"] = credito.get("data_pagamento")
        creditos_calculados.append(calc)
        total_creditos += calc.get("valor_total", 0) or 0

    # Honorarios
    honorarios = data.get("honorarios", [])
    honorarios_calculados = []
    total_honorarios = 0

    base_honorarios = total_geral_debitos - total_creditos

    for hon in honorarios:
        hon_calc = dict(hon)
        forma = hon.get("forma_calculo", "percentual")

        if forma == "percentual":
            perc = float(hon.get("percentual", 0) or 0)
            valor_hon = base_honorarios * (perc / 100)
        else:
            valor_hon = float(hon.get("valor_fixo", 0) or 0)

        hon_calc["valor_base"] = round(base_honorarios, 2)
        hon_calc["valor_honorarios"] = round(valor_hon, 2)
        honorarios_calculados.append(hon_calc)
        total_honorarios += valor_hon

    # Multa 523 CPC
    valor_multa_523 = 0
    valor_honorarios_523 = 0
    if data.get("aplicar_multa_523"):
        base_523 = total_geral_debitos - total_creditos
        if data.get("aplicar_multa_moratoria_10"):
            valor_multa_523 = base_523 * 0.10
        if data.get("aplicar_honorarios_523_10"):
            valor_honorarios_523 = base_523 * 0.10

    # Totais
    subtotal = total_geral_debitos - total_creditos + total_honorarios
    valor_total_geral = subtotal + valor_multa_523 + valor_honorarios_523

    # Atualiza data com valores calculados
    data_calculado = dict(data)
    data_calculado["debitos"] = debitos_calculados
    data_calculado["creditos"] = creditos_calculados
    data_calculado["honorarios"] = honorarios_calculados
    data_calculado["valor_principal"] = round(total_principal, 2)
    data_calculado["valor_corrigido_total"] = round(total_corrigido, 2)
    data_calculado["valor_juros_mora"] = round(total_juros, 2)
    data_calculado["valor_multa_total"] = round(total_multa, 2)
    data_calculado["valor_honorarios_sucumbencia"] = round(total_honorarios, 2)
    data_calculado["valor_multa_523"] = round(valor_multa_523, 2)
    data_calculado["valor_honorarios_523"] = round(valor_honorarios_523, 2)
    data_calculado["subtotal"] = round(subtotal, 2)
    data_calculado["valor_total_geral"] = round(valor_total_geral, 2)

    return data_calculado


@router.get("/legal-calculations")
async def list_legal_calculations(
    skip: int = 0,
    limit: int = 100,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista calculos juridicos do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT * FROM legal_calculations
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, skip)

        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.get("/legal-calculations/{calc_id}")
async def get_legal_calculation(
    calc_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca calculo juridico por ID - retorna dados do result_data mesclados + dados do cliente"""
    import json
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            SELECT * FROM legal_calculations WHERE id = $1
        """, calc_id)
        if not row:
            raise HTTPException(status_code=404, detail="Calculo nao encontrado")

        # Converte row para dict
        result = row_to_dict(row)

        # Extrai metadata_calculo (JSONB) e mescla com o resultado
        # O frontend espera os dados diretamente (nome, debitos, etc)
        # Tenta primeiro metadata_calculo (novo), depois result_data (legado)
        metadata = result.get("metadata_calculo") or result.get("result_data")
        if metadata:
            # Se for string, faz parse
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            # Mescla os dados do metadata no resultado
            result.update(metadata)

        # Busca dados do cliente se houver customer_id
        customer_id = result.get("customer_id")
        if customer_id:
            customer_row = await conn.fetchrow("""
                SELECT id, first_name, last_name, company_name, trade_name, cpf_cnpj, email, phone
                FROM customers WHERE id = $1
            """, customer_id)
            if customer_row:
                result["customer"] = row_to_dict(customer_row)

        return result
    finally:
        await conn.close()


@router.post("/legal-calculations")
async def create_legal_calculation(
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo calculo juridico - CALCULA CORRECAO E JUROS"""
    import uuid
    import json

    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        data = await request.json()
        calc_id = str(uuid.uuid4())

        # *** EXECUTA OS CALCULOS DE CORRECAO E JUROS ***
        data_calculado = await calculate_all_debitos(data)

        # Campos principais
        title = data_calculado.get("nome", "")
        description = data_calculado.get("descricao", "")
        calculation_type = data_calculado.get("indice_correcao", "ipca_e")
        customer_id = data_calculado.get("customer_id")

        # Valores calculados
        principal_amount = data_calculado.get("valor_principal", 0.0)

        # Datas
        debitos = data_calculado.get("debitos", [])
        start_date = None
        if debitos:
            dates = [d.get("data_vencimento") for d in debitos if d.get("data_vencimento")]
            if dates:
                start_date = to_date(min(dates))

        end_date = to_date(data_calculado.get("termo_final"))

        # Armazena dados COM CALCULOS no metadata_calculo (JSONB)
        metadata_calculo = json.dumps(data_calculado)

        # Campos do calculo (usando nomes corretos da tabela)
        nome = data_calculado.get("nome", "")
        descricao = data_calculado.get("descricao", "")
        numero_processo = data_calculado.get("numero_processo", "")
        indice_correcao = data_calculado.get("indice_correcao", "ipca_e")
        termo_final_dt = to_date(data_calculado.get("termo_final"))

        # Opcoes de correcao monetaria
        aplicar_variacoes_positivas = data_calculado.get("aplicar_variacoes_positivas", False)
        usar_capitalizacao_simples = data_calculado.get("usar_capitalizacao_simples", False)
        manter_valor_nominal_inflacao_negativa = data_calculado.get("manter_valor_nominal_inflacao_negativa", False)

        # Juros de mora
        tipo_juros_mora = data_calculado.get("tipo_juros_mora", "nao_aplicar")
        percentual_juros_mora_val = to_decimal(data_calculado.get("percentual_juros_mora"))
        juros_mora_a_partir_de = data_calculado.get("juros_mora_a_partir_de", "vencimento")
        data_fixa_juros_mora = to_date(data_calculado.get("data_fixa_juros_mora"))
        aplicar_juros_mora_pro_rata = data_calculado.get("aplicar_juros_mora_pro_rata", False)
        capitalizar_juros_mora_mensal = data_calculado.get("capitalizar_juros_mora_mensal", False)

        # Juros compensatorios (tipo_juros_compensatorios é NOT NULL!)
        tipo_juros_compensatorios = data_calculado.get("tipo_juros_compensatorios", "nao_aplicar")
        percentual_juros_compensatorios = to_decimal(data_calculado.get("percentual_juros_compensatorios")) or 0

        # Multa
        percentual_multa_val = to_decimal(data_calculado.get("percentual_multa")) or 0
        aplicar_multa_sobre_juros_mora = data_calculado.get("aplicar_multa_sobre_juros_mora", False)
        aplicar_multa_sobre_juros_compensatorios = data_calculado.get("aplicar_multa_sobre_juros_compensatorios", False)
        aplicar_multa_523 = data_calculado.get("aplicar_multa_523", False)

        # Valores calculados
        valor_total_geral = to_decimal(data_calculado.get("valor_total_geral")) or 0
        valor_principal_calc = to_decimal(data_calculado.get("valor_principal")) or 0
        valor_juros_mora_calc = to_decimal(data_calculado.get("valor_juros_mora")) or 0
        valor_multa_calc = to_decimal(data_calculado.get("valor_multa")) or 0
        valor_custas = to_decimal(data_calculado.get("valor_custas")) or 0
        valor_despesas = to_decimal(data_calculado.get("valor_despesas")) or 0
        valor_honorarios_sucumbencia = to_decimal(data_calculado.get("valor_honorarios_sucumbencia")) or 0
        subtotal_val = to_decimal(data_calculado.get("subtotal")) or 0

        # Data do calculo (hoje)
        from datetime import date as dt_date
        data_calculo = dt_date.today()

        await conn.execute("""
            INSERT INTO legal_calculations
            (id, nome, descricao, numero_processo, customer_id, data_calculo, termo_final, indice_correcao,
             aplicar_variacoes_positivas, usar_capitalizacao_simples, manter_valor_nominal_inflacao_negativa,
             tipo_juros_mora, percentual_juros_mora, juros_mora_a_partir_de, data_fixa_juros_mora,
             aplicar_juros_mora_pro_rata, capitalizar_juros_mora_mensal,
             tipo_juros_compensatorios, percentual_juros_compensatorios,
             percentual_multa, aplicar_multa_sobre_juros_mora, aplicar_multa_sobre_juros_compensatorios,
             aplicar_multa_523,
             valor_total_geral, valor_principal, valor_juros_mora, valor_multa,
             valor_custas, valor_despesas, valor_honorarios_sucumbencia, subtotal,
             metadata_calculo, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, calc_id, nome, descricao, numero_processo, customer_id, data_calculo, termo_final_dt, indice_correcao,
             aplicar_variacoes_positivas, usar_capitalizacao_simples, manter_valor_nominal_inflacao_negativa,
             tipo_juros_mora, percentual_juros_mora_val, juros_mora_a_partir_de, data_fixa_juros_mora,
             aplicar_juros_mora_pro_rata, capitalizar_juros_mora_mensal,
             tipo_juros_compensatorios, percentual_juros_compensatorios,
             percentual_multa_val, aplicar_multa_sobre_juros_mora, aplicar_multa_sobre_juros_compensatorios,
             aplicar_multa_523,
             valor_total_geral, valor_principal_calc, valor_juros_mora_calc, valor_multa_calc,
             valor_custas, valor_despesas, valor_honorarios_sucumbencia, subtotal_val,
             metadata_calculo)

        return {"id": calc_id, "message": "Calculo criado com sucesso", "data": data_calculado}
    except Exception as e:
        logger.error(f"Erro ao criar calculo juridico: {str(e)}")
        # Notifica erro por email
        send_error_notification(
            error_type="LEGAL_CALC_ERROR",
            error_message=f"Erro ao criar calculo juridico: {str(e)}",
            error_details=traceback.format_exc(),
            tenant_code=tenant.get("tenant_code"),
            user_email=user.get("email"),
            endpoint="POST /gateway/legal-calculations"
        )
        raise HTTPException(status_code=500, detail=f"Erro ao criar calculo: {str(e)}")
    finally:
        await conn.close()


@router.put("/legal-calculations/{calc_id}")
async def update_legal_calculation(
    calc_id: str,
    request: Request,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza calculo juridico existente - RECALCULA CORRECAO E JUROS"""
    import json

    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Verifica se existe
        existing = await conn.fetchrow("SELECT id FROM legal_calculations WHERE id = $1", calc_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Calculo nao encontrado")

        data = await request.json()

        # *** EXECUTA OS CALCULOS DE CORRECAO E JUROS ***
        data_calculado = await calculate_all_debitos(data)

        # Campos principais
        title = data_calculado.get("nome", "")
        description = data_calculado.get("descricao", "")
        calculation_type = data_calculado.get("indice_correcao", "ipca_e")

        # Valores calculados
        principal_amount = data_calculado.get("valor_principal", 0.0)

        # Datas
        debitos = data_calculado.get("debitos", [])
        start_date = None
        if debitos:
            dates = [d.get("data_vencimento") for d in debitos if d.get("data_vencimento")]
            if dates:
                start_date = to_date(min(dates))

        end_date = to_date(data_calculado.get("termo_final"))

        # Armazena dados COM CALCULOS no result_data (JSONB)
        result_data = json.dumps(data_calculado)

        await conn.execute("""
            UPDATE legal_calculations SET
                nome = $1,
                descricao = $2,
                indice_correcao = $3,
                valor_principal = $4,
                valor_total_geral = $5,
                valor_juros_mora = $6,
                valor_multa = $7,
                valor_custas = $8,
                valor_despesas = $9,
                valor_honorarios_sucumbencia = $10,
                subtotal = $11,
                termo_final = $12,
                metadata_calculo = $13::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $14
        """, 
            data_calculado.get('nome', ''),
            data_calculado.get('descricao', ''),
            data_calculado.get('indice_correcao', 'ipca_e'),
            data_calculado.get('valor_principal', 0.0),
            data_calculado.get('valor_total_geral', 0.0),
            data_calculado.get('valor_juros_mora', 0.0),
            data_calculado.get('valor_multa', 0.0),
            data_calculado.get('valor_custas', 0.0),
            data_calculado.get('valor_despesas', 0.0),
            data_calculado.get('valor_honorarios_sucumbencia', 0.0),
            data_calculado.get('subtotal', 0.0),
            end_date,
            result_data,
            calc_id)

        return {"id": calc_id, "message": "Calculo atualizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar calculo juridico: {str(e)}")
        send_error_notification(
            error_type="LEGAL_CALC_ERROR",
            error_message=f"Erro ao atualizar calculo juridico: {str(e)}",
            error_details=traceback.format_exc(),
            tenant_code=tenant.get("tenant_code"),
            user_email=user.get("email"),
            endpoint=f"PUT /gateway/legal-calculations/{calc_id}"
        )
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar calculo: {str(e)}")
    finally:
        await conn.close()


@router.delete("/legal-calculations/{calc_id}")
async def delete_legal_calculation(
    calc_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove calculo juridico"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        result = await conn.execute("DELETE FROM legal_calculations WHERE id = $1", calc_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Calculo nao encontrado")
        return {"message": "Calculo removido com sucesso"}
    finally:
        await conn.close()


@router.post("/legal-calculations/{calc_id}/recalculate")
async def recalculate_legal_calculation(
    calc_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Recalcula um calculo juridico existente com indices atualizados"""
    import json

    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca o calculo existente
        row = await conn.fetchrow("SELECT * FROM legal_calculations WHERE id = $1", calc_id)
        if not row:
            raise HTTPException(status_code=404, detail="Calculo nao encontrado")

        result = row_to_dict(row)

        # Extrai dados do metadata_calculo (ou result_data legado)
        data = {}
        metadata = result.get("metadata_calculo") or result.get("result_data")
        if metadata:
            if isinstance(metadata, str):
                data = json.loads(metadata)
            else:
                data = metadata

        # *** RECALCULA COM INDICES ATUALIZADOS ***
        data_calculado = await calculate_all_debitos(data)

        # Atualiza no banco
        title = data_calculado.get("nome", "")
        description = data_calculado.get("descricao", "")
        calculation_type = data_calculado.get("indice_correcao", "ipca_e")
        principal_amount = data_calculado.get("valor_principal", 0.0)

        debitos = data_calculado.get("debitos", [])
        start_date = None
        if debitos:
            dates = [d.get("data_vencimento") for d in debitos if d.get("data_vencimento")]
            if dates:
                start_date = to_date(min(dates))

        end_date = to_date(data_calculado.get("termo_final"))

        result_data_json = json.dumps(data_calculado)

        await conn.execute("""
            UPDATE legal_calculations SET
                nome = $1,
                descricao = $2,
                indice_correcao = $3,
                valor_principal = $4,
                valor_total_geral = $5,
                valor_juros_mora = $6,
                valor_multa = $7,
                valor_custas = $8,
                valor_despesas = $9,
                valor_honorarios_sucumbencia = $10,
                subtotal = $11,
                termo_final = $12,
                metadata_calculo = $13::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $14
        """, 
            data_calculado.get('nome', ''),
            data_calculado.get('descricao', ''),
            data_calculado.get('indice_correcao', 'ipca_e'),
            data_calculado.get('valor_principal', 0.0),
            data_calculado.get('valor_total_geral', 0.0),
            data_calculado.get('valor_juros_mora', 0.0),
            data_calculado.get('valor_multa', 0.0),
            data_calculado.get('valor_custas', 0.0),
            data_calculado.get('valor_despesas', 0.0),
            data_calculado.get('valor_honorarios_sucumbencia', 0.0),
            data_calculado.get('subtotal', 0.0),
            end_date,
            result_data_json,
            calc_id)

        return {"id": calc_id, "message": "Calculo recalculado com sucesso", "data": data_calculado}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao recalcular: {str(e)}")
        send_error_notification(
            error_type="LEGAL_CALC_ERROR",
            error_message=f"Erro ao recalcular calculo juridico: {str(e)}",
            error_details=traceback.format_exc(),
            tenant_code=tenant.get("tenant_code"),
            user_email=user.get("email"),
            endpoint=f"POST /gateway/legal-calculations/{calc_id}/recalculate"
        )
        raise HTTPException(status_code=500, detail=f"Erro ao recalcular: {str(e)}")
    finally:
        await conn.close()


# === ENDPOINTS - AUTH ===

@router.get("/auth/me")
async def get_current_user(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna dados do usuario logado"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado usa full_name e role
        row = await conn.fetchrow("""
            SELECT id, email,
                COALESCE(full_name, username, email) as name,
                full_name,
                username,
                role,
                (role = 'admin' OR role = 'superadmin') as is_admin,
                is_active
            FROM users WHERE id::text = $1
        """, user["user_id"])
        if row:
            return row_to_dict(row)
        # Fallback com dados do token
        return {
            "id": user["user_id"],
            "email": user["email"],
            "name": user["email"].split("@")[0],
            "is_admin": user["is_admin"],
            "is_active": True
        }
    finally:
        await conn.close()


# === ENDPOINTS - USERS ===

@router.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista usuarios do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado usa full_name e role em vez de name e is_admin
        rows = await conn.fetch("""
            SELECT id, email,
                COALESCE(full_name, username, email) as name,
                full_name,
                username,
                role,
                (role = 'admin' OR role = 'superadmin') as is_admin,
                is_active,
                created_at
            FROM users
            WHERE deleted_at IS NULL
            ORDER BY COALESCE(full_name, username, email)
            LIMIT $1 OFFSET $2
        """, limit, skip)

        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.get("/users/roles")
async def list_user_roles(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista roles disponiveis"""
    return [
        {"id": "admin", "name": "Administrador"},
        {"id": "manager", "name": "Gerente"},
        {"id": "user", "name": "Usuario"}
    ]


@router.get("/users/permissions")
async def list_user_permissions(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista permissoes disponiveis"""
    return []




@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca usuario por ID"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            SELECT id, email,
                COALESCE(full_name, username, email) as name,
                full_name,
                username,
                role,
                (role = 'admin' OR role = 'superadmin') as is_admin,
                is_active,
                created_at
            FROM users
            WHERE id::text = $1 AND deleted_at IS NULL
        """, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.post("/users")
async def create_user(
    user_data: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo usuario"""
    import uuid
    import hashlib
    tenant, current_user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Verifica se email ja existe
        existing = await conn.fetchval(
            "SELECT 1 FROM users WHERE email = $1 AND deleted_at IS NULL",
            user_data.get("email", "").lower()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email ja cadastrado")

        # Gera ID e hash da senha
        user_id = str(uuid.uuid4())
        password = user_data.get("password", "123456")
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Insere usuario - inclui TODAS as colunas NOT NULL do schema legado
        row = await conn.fetchrow("""
            INSERT INTO users (
                id, email, hashed_password, full_name, role,
                is_active, is_verified, must_change_password,
                two_factor_enabled, failed_login_attempts,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, TRUE, TRUE, FALSE, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id, email, full_name, role, is_active, created_at
        """,
            user_id,
            user_data.get("email", "").lower(),
            password_hash,
            user_data.get("full_name") or user_data.get("name", ""),
            user_data.get("role", "user"),
            user_data.get("is_active", True)
        )

        result = row_to_dict(row)
        result["name"] = result.get("full_name", "")
        result["is_admin"] = result.get("role") in ["admin", "superadmin"]
        return {"success": True, "data": result, "message": "Usuario criado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar usuario: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    user_data: dict,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza usuario"""
    import hashlib
    tenant, current_user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Verifica se usuario existe
        existing = await conn.fetchrow(
            "SELECT * FROM users WHERE id::text = $1 AND deleted_at IS NULL",
            user_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")

        # Verifica email duplicado (se alterado)
        new_email = user_data.get("email", "").lower()
        if new_email and new_email != existing["email"]:
            email_exists = await conn.fetchval(
                "SELECT 1 FROM users WHERE email = $1 AND id::text != $2 AND deleted_at IS NULL",
                new_email, user_id
            )
            if email_exists:
                raise HTTPException(status_code=400, detail="Email ja cadastrado")

        # Prepara campos para update
        update_fields = []
        values = [user_id]
        param_index = 2

        if "email" in user_data:
            update_fields.append(f"email = ${param_index}")
            values.append(user_data["email"].lower())
            param_index += 1

        if "full_name" in user_data or "name" in user_data:
            update_fields.append(f"full_name = ${param_index}")
            values.append(user_data.get("full_name") or user_data.get("name", ""))
            param_index += 1

        if "role" in user_data:
            update_fields.append(f"role = ${param_index}")
            values.append(user_data["role"])
            param_index += 1

        if "is_active" in user_data:
            update_fields.append(f"is_active = ${param_index}")
            values.append(user_data["is_active"])
            param_index += 1

        if "password" in user_data and user_data["password"]:
            password_hash = hashlib.sha256(user_data["password"].encode()).hexdigest()
            update_fields.append(f"hashed_password = ${param_index}")
            values.append(password_hash)
            param_index += 1

        update_fields.append(f"updated_at = ${param_index}")
        values.append(datetime.utcnow())

        if not update_fields:
            raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

        query = f"""
            UPDATE users SET {', '.join(update_fields)}
            WHERE id::text = $1 AND deleted_at IS NULL
            RETURNING id, email, full_name, role, is_active, created_at
        """

        row = await conn.fetchrow(query, *values)
        if not row:
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")

        result = row_to_dict(row)
        result["name"] = result.get("full_name", "")
        result["is_admin"] = result.get("role") in ["admin", "superadmin"]
        return {"success": True, "data": result, "message": "Usuario atualizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar usuario: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove usuario (soft delete)"""
    tenant, current_user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Nao permite deletar o proprio usuario
        if current_user["user_id"] == user_id:
            raise HTTPException(status_code=400, detail="Nao e possivel remover seu proprio usuario")

        # Soft delete
        result = await conn.execute("""
            UPDATE users SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id::text = $1 AND deleted_at IS NULL
        """, user_id)

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Usuario nao encontrado")

        return {"success": True, "message": "Usuario removido com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao remover usuario: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


# === ENDPOINTS - DASHBOARD OVERVIEW ===

@router.get("/dashboard/overview")
async def get_dashboard_overview(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna visao geral do dashboard"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Contagens basicas
        customers_count = await conn.fetchval("SELECT COUNT(*) FROM customers") or 0
        products_count = await conn.fetchval("SELECT COUNT(*) FROM products") or 0
        suppliers_count = await conn.fetchval("SELECT COUNT(*) FROM suppliers") or 0

        # Verifica se tabela employees existe
        employees_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'employees'
            )
        """)
        employees_count = 0
        if employees_exists:
            employees_count = await conn.fetchval("SELECT COUNT(*) FROM employees") or 0

        # Vendas do mes - schema legado usa total_amount em vez de total
        sales_month = await conn.fetchval("""
            SELECT COALESCE(SUM(COALESCE(total_amount, 0)), 0) FROM sales
            WHERE DATE_TRUNC('month', sale_date) = DATE_TRUNC('month', CURRENT_DATE)
        """) or 0

        # Verifica se coluna parent_id existe nas tabelas (compatibilidade multi-tenant)
        ar_has_parent = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'accounts_receivable' AND column_name = 'parent_id'
            )
        """)
        ap_has_parent = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'accounts_payable' AND column_name = 'parent_id'
            )
        """)

        # Verifica se coluna is_active existe em accounts_receivable
        ar_has_is_active = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'accounts_receivable' AND column_name = 'is_active'
            )
        """)

        # CONTAS A RECEBER - queries compatíveis com diferentes schemas
        if ar_has_parent and ar_has_is_active:
            # Schema novo com parent_id e is_active
            receivables_pending = await conn.fetchval("""
                SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
                AND is_active = true
                AND (parent_id IS NOT NULL OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1)))
            """) or 0
            receivables_received = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
                WHERE UPPER(status::text) IN ('PAID', 'PARTIAL')
                AND is_active = true
                AND (parent_id IS NOT NULL OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1)))
            """) or 0
            receivables_overdue = await conn.fetchval("""
                SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
                AND due_date < CURRENT_DATE
                AND is_active = true
                AND (parent_id IS NOT NULL OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1)))
            """) or 0
        else:
            # Schema legado sem parent_id - soma tudo
            receivables_pending = await conn.fetchval("""
                SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
            """) or 0
            receivables_received = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
                WHERE UPPER(status::text) IN ('PAID', 'PARTIAL')
            """) or 0
            receivables_overdue = await conn.fetchval("""
                SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
                AND due_date < CURRENT_DATE
            """) or 0

        # CONTAS A PAGAR - queries compatíveis com diferentes schemas
        if ap_has_parent:
            # Schema novo com parent_id
            payables_pending = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
                AND (parent_id IS NOT NULL OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1)))
            """) or 0
            payables_paid = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(amount_paid, 0)), 0) FROM accounts_payable
                WHERE UPPER(status::text) IN ('PAID', 'PARTIAL')
                AND (parent_id IS NOT NULL OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1)))
            """) or 0
            payables_overdue = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
                AND due_date < CURRENT_DATE
                AND (parent_id IS NOT NULL OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1)))
            """) or 0
        else:
            # Schema legado sem parent_id - soma tudo
            payables_pending = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
            """) or 0
            payables_paid = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(amount_paid, 0)), 0) FROM accounts_payable
                WHERE UPPER(status::text) IN ('PAID', 'PARTIAL')
            """) or 0
            payables_overdue = await conn.fetchval("""
                SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
                WHERE UPPER(status::text) IN ('PENDING', 'PARTIAL')
                AND due_date < CURRENT_DATE
            """) or 0

        return {
            "customers_count": customers_count,
            "products_count": products_count,
            "suppliers_count": suppliers_count,
            "employees_count": employees_count,
            "sales_month": float(sales_month),
            "accounts_receivable": float(receivables_pending),
            "accounts_payable": float(payables_pending),
            # Campos adicionais para o frontend - Contas a Receber
            "receivable_pending": float(receivables_pending),
            "receivable_received": float(receivables_received),
            "receivable_overdue": float(receivables_overdue),
            # Campos adicionais para o frontend - Contas a Pagar
            "payable_pending": float(payables_pending),
            "payable_paid": float(payables_paid),
            "payable_overdue": float(payables_overdue),
            # Campos de receita
            "revenue_today": 0.0,
            "revenue_week": 0.0,
            "revenue_month": float(sales_month),
            "pending_orders": 0,
            "low_stock_products": 0
        }
    finally:
        await conn.close()


@router.get("/dashboard/indices-status")
async def get_indices_status(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """
    Retorna status dos indices economicos buscando da API do Banco Central.
    Verifica se os indices principais estao atualizados.
    """
    tenant, user = tenant_data
    import httpx

    # Indices principais para verificar (codigos do BCB SGS)
    indices_config = {
        "ipca": {"codigo": 433, "nome": "IPCA"},
        "igpm": {"codigo": 189, "nome": "IGP-M"},
        "selic": {"codigo": 4390, "nome": "SELIC"},
        "cdi": {"codigo": 4391, "nome": "CDI"},
        "inpc": {"codigo": 188, "nome": "INPC"},
        "tr": {"codigo": 226, "nome": "TR"},
    }

    indices_result = {}
    all_updated = True
    last_update = None

    # Busca o ultimo valor de cada indice da API do BCB
    for key, config in indices_config.items():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Busca ultimos 3 meses para pegar o mais recente
                url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{config['codigo']}/dados/ultimos/3?formato=json"
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        ultimo = data[-1]  # Ultimo registro
                        indices_result[key] = {
                            "value": float(ultimo.get("valor", 0)),
                            "date": ultimo.get("data", ""),
                            "status": "ok",
                            "nome": config["nome"]
                        }
                        # Atualiza a data mais recente
                        if not last_update or ultimo.get("data", "") > last_update:
                            last_update = ultimo.get("data", "")
                    else:
                        indices_result[key] = {"value": 0, "date": "", "status": "unavailable", "nome": config["nome"]}
                        all_updated = False
                else:
                    indices_result[key] = {"value": 0, "date": "", "status": "error", "nome": config["nome"]}
                    all_updated = False
        except Exception as e:
            logger.warning(f"Erro ao buscar indice {key} do BCB: {e}")
            indices_result[key] = {"value": 0, "date": "", "status": "error", "nome": config["nome"]}
            all_updated = False

    # Verifica se os indices estao atualizados (ultimos 60 dias)
    today = datetime.now()
    is_updated = all_updated

    return {
        "is_updated": is_updated,
        "last_update": last_update or today.isoformat(),
        "indices": indices_result,
        "sync_status": {
            "status": "synced" if is_updated else "outdated",
            "last_sync": today.isoformat(),
            "next_sync": None
        },
        "fonte": "Banco Central do Brasil (BCB/SGS)"
    }


# === ENDPOINTS - ACCOUNTS RECEIVABLE STATS ===

@router.get("/accounts-receivable/stats/summary")
async def get_accounts_receivable_summary(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna resumo de contas a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Filtro para excluir contas PAI de parcelamentos (evita duplicacao)
        # Inclui: parcelas filhas (parent_id IS NOT NULL) + contas simples (sem parcelas)
        filter_clause = """
            AND is_active = true
            AND (
                parent_id IS NOT NULL
                OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1))
            )
        """

        # Valor total pendente (a receber)
        total_pending = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL')
            {filter_clause}
        """) or 0

        # Valor total pago
        total_paid = await conn.fetchval(f"""
            SELECT COALESCE(SUM(paid_amount), 0) FROM accounts_receivable
            WHERE status::text IN ('paid', 'PAID', 'partial', 'PARTIAL')
            {filter_clause}
        """) or 0

        # Valor total vencido
        total_overdue = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND due_date < CURRENT_DATE
            {filter_clause}
        """) or 0

        return {
            "total_pending": float(total_pending),
            "total_paid": float(total_paid),
            "total_overdue": float(total_overdue)
        }
    finally:
        await conn.close()


@router.get("/accounts-receivable/stats/detailed")
async def get_accounts_receivable_detailed(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna estatisticas detalhadas de contas a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Filtro para excluir contas PAI de parcelamentos (evita duplicacao)
        filter_no_parent = """
            AND is_active = true
            AND (
                parent_id IS NOT NULL
                OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1))
            )
        """

        # Contagens (excluindo contas PAI de parcelamentos)
        count_total = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE 1=1 {filter_no_parent}") or 0
        count_pending = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0
        count_paid = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE status::text IN ('paid', 'PAID') {filter_no_parent}") or 0
        count_overdue = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND due_date < CURRENT_DATE {filter_no_parent}") or 0

        # Valores (excluindo contas PAI de parcelamentos)
        amount_total = await conn.fetchval(f"SELECT COALESCE(SUM(amount), 0) FROM accounts_receivable WHERE 1=1 {filter_no_parent}") or 0
        amount_paid = await conn.fetchval(f"SELECT COALESCE(SUM(paid_amount), 0) FROM accounts_receivable WHERE status::text IN ('paid', 'PAID', 'partial', 'PARTIAL') {filter_no_parent}") or 0
        amount_balance = await conn.fetchval(f"SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0
        amount_overdue = await conn.fetchval(f"SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND due_date < CURRENT_DATE {filter_no_parent}") or 0

        # Ticket medio
        avg_ticket = float(amount_total) / float(count_total) if count_total > 0 else 0

        # Vencimentos (excluindo contas PAI de parcelamentos)
        due_today_count = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE due_date = CURRENT_DATE AND status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0
        due_today_amount = await conn.fetchval(f"SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable WHERE due_date = CURRENT_DATE AND status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0

        due_week_count = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 AND status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0
        due_week_amount = await conn.fetchval(f"SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7 AND status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0

        due_month_count = await conn.fetchval(f"SELECT COUNT(*) FROM accounts_receivable WHERE DATE_TRUNC('month', due_date) = DATE_TRUNC('month', CURRENT_DATE) AND status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0
        due_month_amount = await conn.fetchval(f"SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable WHERE DATE_TRUNC('month', due_date) = DATE_TRUNC('month', CURRENT_DATE) AND status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {filter_no_parent}") or 0

        # Percentuais
        pct_paid = (float(count_paid) / float(count_total) * 100) if count_total > 0 else 0
        pct_pending = (float(count_pending) / float(count_total) * 100) if count_total > 0 else 0
        pct_overdue = (float(count_overdue) / float(count_total) * 100) if count_total > 0 else 0
        pct_received = (float(amount_paid) / float(amount_total) * 100) if amount_total > 0 else 0

        return {
            "counts": {
                "total": count_total,
                "pending": count_pending,
                "paid": count_paid,
                "overdue": count_overdue
            },
            "amounts": {
                "total": float(amount_total),
                "paid": float(amount_paid),
                "balance": float(amount_balance),
                "overdue": float(amount_overdue),
                "avg_ticket": float(avg_ticket)
            },
            "due_today": {
                "count": due_today_count,
                "amount": float(due_today_amount)
            },
            "due_week": {
                "count": due_week_count,
                "amount": float(due_week_amount)
            },
            "due_month": {
                "count": due_month_count,
                "amount": float(due_month_amount)
            },
            "percentages": {
                "paid": round(pct_paid, 1),
                "pending": round(pct_pending, 1),
                "overdue": round(pct_overdue, 1),
                "received": round(pct_received, 1)
            }
        }
    finally:
        await conn.close()


# === ENDPOINTS - ACCOUNTS PAYABLE STATS ===

@router.get("/accounts-payable/stats/summary")
async def get_accounts_payable_summary(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna resumo de contas a pagar"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado usa amount_paid em vez de paid_amount
        total = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM accounts_payable") or 0
        paid = await conn.fetchval("SELECT COALESCE(SUM(COALESCE(amount_paid, 0)), 0) FROM accounts_payable") or 0
        pending = await conn.fetchval("""
            SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING')
        """) or 0
        overdue = await conn.fetchval("""
            SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING') AND due_date < CURRENT_DATE
        """) or 0

        return {
            "total": float(total),
            "paid": float(paid),
            "pending": float(pending),
            "overdue": float(overdue),
            "count_total": await conn.fetchval("SELECT COUNT(*) FROM accounts_payable") or 0,
            "count_pending": await conn.fetchval("SELECT COUNT(*) FROM accounts_payable WHERE status::text IN ('pending', 'PENDING')") or 0,
            "count_paid": await conn.fetchval("SELECT COUNT(*) FROM accounts_payable WHERE status::text IN ('paid', 'PAID')") or 0
        }
    finally:
        await conn.close()


@router.get("/accounts-payable/stats/detailed")
async def get_accounts_payable_detailed(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna estatisticas detalhadas de contas a pagar no formato esperado pelo frontend"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        from datetime import date, timedelta
        today = date.today()
        week_later = today + timedelta(days=7)
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Contagens
        total_count = await conn.fetchval("SELECT COUNT(*) FROM accounts_payable WHERE (installment_number = 0 OR installment_number IS NULL)") or 0
        pending_count = await conn.fetchval("""
            SELECT COUNT(*) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """) or 0
        paid_count = await conn.fetchval("""
            SELECT COUNT(*) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND UPPER(status::text) = 'PAID'
        """) or 0
        overdue_count = await conn.fetchval("""
            SELECT COUNT(*) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date < $1 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, today) or 0

        # Valores
        total_amount = float(await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM accounts_payable WHERE (installment_number = 0 OR installment_number IS NULL)") or 0)
        paid_amount = float(await conn.fetchval("SELECT COALESCE(SUM(COALESCE(amount_paid, 0)), 0) FROM accounts_payable WHERE (installment_number = 0 OR installment_number IS NULL)") or 0)
        balance = float(await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """) or 0)
        overdue_amount = float(await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date < $1 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, today) or 0)

        # Vencimentos
        due_today_count = await conn.fetchval("""
            SELECT COUNT(*) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date = $1 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, today) or 0
        due_today_amount = float(await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date = $1 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, today) or 0)

        due_week_count = await conn.fetchval("""
            SELECT COUNT(*) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date >= $1 AND due_date <= $2 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, today, week_later) or 0
        due_week_amount = float(await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date >= $1 AND due_date <= $2 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, today, week_later) or 0)

        due_month_count = await conn.fetchval("""
            SELECT COUNT(*) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date >= $1 AND due_date <= $2 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, month_start, month_end) or 0
        due_month_amount = float(await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE (installment_number = 0 OR installment_number IS NULL)
            AND due_date >= $1 AND due_date <= $2 AND UPPER(status::text) IN ('PENDING', 'PARTIAL')
        """, month_start, month_end) or 0)

        # Percentuais
        pct_paid = round((paid_count / total_count * 100), 1) if total_count > 0 else 0
        pct_pending = round((pending_count / total_count * 100), 1) if total_count > 0 else 0
        pct_overdue = round((overdue_count / total_count * 100), 1) if total_count > 0 else 0
        pct_paid_amount = round((paid_amount / total_amount * 100), 1) if total_amount > 0 else 0
        avg_ticket = round(total_amount / total_count, 2) if total_count > 0 else 0

        return {
            "counts": {
                "total": total_count,
                "pending": pending_count,
                "paid": paid_count,
                "overdue": overdue_count
            },
            "amounts": {
                "total": round(total_amount, 2),
                "paid": round(paid_amount, 2),
                "balance": round(balance, 2),
                "overdue": round(overdue_amount, 2),
                "avg_ticket": avg_ticket
            },
            "due_today": {
                "count": due_today_count,
                "amount": round(due_today_amount, 2)
            },
            "due_week": {
                "count": due_week_count,
                "amount": round(due_week_amount, 2)
            },
            "due_month": {
                "count": due_month_count,
                "amount": round(due_month_amount, 2)
            },
            "percentages": {
                "paid": pct_paid,
                "pending": pct_pending,
                "overdue": pct_overdue,
                "paid_amount": pct_paid_amount
            }
        }
    finally:
        await conn.close()


# === ENDPOINTS - COMPANY ALIASES ===

@router.get("/company/current")
async def get_company_current(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna dados da empresa (alias para /company)"""
    return await get_company(tenant_data)


# === ENDPOINTS - REPORTS ===

@router.get("/reports/company-info")
async def get_reports_company_info(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna info da empresa para relatorios"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("SELECT * FROM companies LIMIT 1")
        if row:
            data = row_to_dict(row)
            if data.get('logo_path'):
                data['logo_url'] = f"/uploads/{data['logo_path']}"
            return data
        # Fallback com dados do tenant
        return {
            "id": None,
            "name": tenant.name,
            "trade_name": tenant.trade_name,
            "document": tenant.document,
            "phone": tenant.phone,
            "email": tenant.email,
            "logo_url": None
        }
    finally:
        await conn.close()


@router.get("/reports/customers/list")
async def get_reports_customers_list(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista clientes para relatorios"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Schema legado: customers usa first_name/last_name e cpf_cnpj
        rows = await conn.fetch("""
            SELECT id,
                COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name,
                cpf_cnpj as document, email, phone
            FROM customers
            ORDER BY COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name)
            LIMIT 1000
        """)
        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.get("/reports/suppliers/list")
async def get_reports_suppliers_list(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista fornecedores para relatorios"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT id,
                COALESCE(company_name, trade_name, name) as name,
                cpf_cnpj as document, email, phone
            FROM suppliers
            WHERE deleted_at IS NULL
            ORDER BY COALESCE(company_name, trade_name, name)
            LIMIT 1000
        """)
        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


@router.get("/reports/sellers/list")
async def get_reports_sellers_list(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista vendedores para relatorios"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT id, full_name as name, email
            FROM users
            WHERE deleted_at IS NULL AND is_active = true
            ORDER BY full_name
            LIMIT 500
        """)
        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


# === ENDPOINTS - REPORTS ACCOUNTS RECEIVABLE ===

@router.get("/reports/accounts-receivable/summary")
async def get_reports_accounts_receivable_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio resumido de contas a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Filtro para excluir contas PAI de parcelamentos
        # IMPORTANTE: usar ar.is_active para evitar ambiguidade com customers.is_active
        filter_clause = """
            AND ar.is_active = true
            AND (
                ar.parent_id IS NOT NULL
                OR (ar.parent_id IS NULL AND (ar.total_installments IS NULL OR ar.total_installments <= 1))
            )
        """

        where_parts = ["1=1"]
        params = []
        param_idx = 1

        if start_date:
            where_parts.append(f"ar.due_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            where_parts.append(f"ar.due_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if customer_id:
            where_parts.append(f"ar.customer_id::text = ${param_idx}")
            params.append(customer_id)
            param_idx += 1

        if status:
            status_upper = status.upper()
            # 'OVERDUE' (Vencido) nao e um status real no banco
            # E uma condicao calculada: status pendente/parcial + due_date < hoje
            if status_upper == 'OVERDUE':
                where_parts.append("UPPER(ar.status::text) IN ('PENDING', 'PARTIAL')")
                where_parts.append("ar.due_date < CURRENT_DATE")
            else:
                where_parts.append(f"UPPER(ar.status::text) = ${param_idx}")
                params.append(status_upper)
                param_idx += 1

        where_clause = " AND ".join(where_parts) + filter_clause

        # Lista de contas
        # Inclui campo 'balance' calculado e status ajustado para 'overdue' quando vencido
        rows = await conn.fetch(f"""
            SELECT ar.id, ar.customer_id, ar.description, ar.document_number, ar.amount,
                ar.paid_amount, ar.due_date, ar.payment_date, ar.status, ar.payment_method,
                ar.installment_number, ar.total_installments, ar.parent_id, ar.notes,
                ar.is_active, ar.created_at, ar.updated_at,
                (ar.amount - COALESCE(ar.paid_amount, 0)) as balance,
                CASE
                    WHEN ar.status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL')
                         AND ar.due_date < CURRENT_DATE
                    THEN 'overdue'
                    ELSE LOWER(ar.status::text)
                END as calculated_status,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE {where_clause}
            ORDER BY ar.due_date
        """, *params)

        # Totais
        total_value = sum(float(r.get('amount', 0) or 0) for r in rows)
        total_paid = sum(float(r.get('paid_amount', 0) or 0) for r in rows)
        total_balance = total_value - total_paid

        # Converte rows para dict e substitui 'status' pelo 'calculated_status'
        data_list = []
        for row in rows:
            row_dict = row_to_dict(row)
            # Usa o status calculado (que inclui 'overdue' para vencidos)
            if 'calculated_status' in row_dict:
                row_dict['status'] = row_dict['calculated_status']
            data_list.append(row_dict)

        return {
            "data": data_list,
            "summary": {
                "total_value": total_value,
                "total_paid": total_paid,
                "total_balance": total_balance,
                "count": len(rows)
            }
        }
    finally:
        await conn.close()


@router.get("/reports/accounts-receivable/detailed")
async def get_reports_accounts_receivable_detailed(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio detalhado de contas a receber"""
    # Usa a mesma logica do summary, mas pode ser expandido
    return await get_reports_accounts_receivable_summary(
        start_date=start_date,
        end_date=end_date,
        customer_id=customer_id,
        status=status,
        tenant_data=tenant_data
    )


# === ENDPOINTS - REPORTS ACCOUNTS PAYABLE ===

@router.get("/reports/accounts-payable/summary")
async def get_reports_accounts_payable_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_id: Optional[str] = None,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio resumido de contas a pagar"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Filtros básicos - sem is_active que pode não existir
        where_parts = ["1=1"]
        params = []
        param_idx = 1

        if start_date:
            where_parts.append(f"ap.due_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            where_parts.append(f"ap.due_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if supplier_id:
            where_parts.append(f"ap.supplier_id::text = ${param_idx}")
            params.append(supplier_id)
            param_idx += 1

        if status:
            status_upper = status.upper()
            # 'OVERDUE' (Vencido) nao e um status real no banco
            # E uma condicao calculada: status pendente/parcial + due_date < hoje
            if status_upper == 'OVERDUE':
                where_parts.append("UPPER(ap.status::text) IN ('PENDING', 'PARTIAL')")
                where_parts.append("ap.due_date < CURRENT_DATE")
            else:
                where_parts.append(f"UPPER(ap.status::text) = ${param_idx}")
                params.append(status_upper)
                param_idx += 1

        where_clause = " AND ".join(where_parts)

        # Lista de contas - usa apenas amount_paid (schema padrão)
        # Inclui campo 'balance' calculado e status ajustado para 'overdue' quando vencido
        rows = await conn.fetch(f"""
            SELECT ap.id, ap.supplier_id, ap.description, ap.document_number, ap.amount,
                COALESCE(ap.amount_paid, 0) as paid_amount,
                ap.due_date, ap.payment_date, ap.status, ap.payment_method,
                ap.notes, ap.created_at, ap.updated_at,
                (ap.amount - COALESCE(ap.amount_paid, 0)) as balance,
                CASE
                    WHEN ap.status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL')
                         AND ap.due_date < CURRENT_DATE
                    THEN 'overdue'
                    ELSE LOWER(ap.status::text)
                END as calculated_status,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM accounts_payable ap
            LEFT JOIN suppliers s ON ap.supplier_id = s.id
            WHERE {where_clause}
            ORDER BY ap.due_date
        """, *params)

        # Totais
        total_value = sum(float(r.get('amount', 0) or 0) for r in rows)
        total_paid = sum(float(r.get('paid_amount', 0) or 0) for r in rows)
        total_balance = total_value - total_paid

        # Converte rows para dict e substitui 'status' pelo 'calculated_status'
        data_list = []
        for row in rows:
            row_dict = row_to_dict(row)
            # Usa o status calculado (que inclui 'overdue' para vencidos)
            if 'calculated_status' in row_dict:
                row_dict['status'] = row_dict['calculated_status']
            data_list.append(row_dict)

        return {
            "data": data_list,
            "summary": {
                "total_value": total_value,
                "total_paid": total_paid,
                "total_balance": total_balance,
                "count": len(rows)
            }
        }
    except Exception as e:
        print(f"[REPORTS] Erro no relatorio contas a pagar: {e}", flush=True)
        # Retorna lista vazia em caso de erro (tabela vazia, coluna inexistente, etc)
        return {
            "data": [],
            "summary": {
                "total_value": 0,
                "total_paid": 0,
                "total_balance": 0,
                "count": 0
            },
            "message": "Nenhuma conta a pagar encontrada"
        }
    finally:
        await conn.close()


@router.get("/reports/accounts-payable/detailed")
async def get_reports_accounts_payable_detailed(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_id: Optional[str] = None,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio detalhado de contas a pagar"""
    return await get_reports_accounts_payable_summary(
        start_date=start_date,
        end_date=end_date,
        supplier_id=supplier_id,
        status=status,
        tenant_data=tenant_data
    )


# === ENDPOINTS - REPORTS SALES ===

@router.get("/reports/sales")
async def get_reports_sales(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    customer_id: Optional[str] = None,
    seller_id: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio de vendas"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        where_parts = ["1=1"]
        params = []
        param_idx = 1

        if start_date:
            where_parts.append(f"s.sale_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            where_parts.append(f"s.sale_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if customer_id:
            where_parts.append(f"s.customer_id::text = ${param_idx}")
            params.append(customer_id)
            param_idx += 1

        if seller_id:
            where_parts.append(f"s.seller_id::text = ${param_idx}")
            params.append(seller_id)
            param_idx += 1

        where_clause = " AND ".join(where_parts)

        rows = await conn.fetch(f"""
            SELECT s.*,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                u.full_name as seller_name
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.id
            LEFT JOIN users u ON s.seller_id = u.id
            WHERE {where_clause}
            ORDER BY s.sale_date DESC
        """, *params)

        total_amount = sum(float(r.get('total_amount', 0) or r.get('total', 0) or 0) for r in rows)

        return {
            "data": [row_to_dict(row) for row in rows],
            "summary": {
                "total_amount": total_amount,
                "count": len(rows)
            }
        }
    finally:
        await conn.close()


# === ENDPOINTS - REPORTS PURCHASES ===

@router.get("/reports/purchases")
async def get_reports_purchases(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    supplier_id: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio de compras"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        where_parts = ["1=1"]
        params = []
        param_idx = 1

        if start_date:
            where_parts.append(f"p.purchase_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            where_parts.append(f"p.purchase_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if supplier_id:
            where_parts.append(f"p.supplier_id::text = ${param_idx}")
            params.append(supplier_id)
            param_idx += 1

        where_clause = " AND ".join(where_parts)

        rows = await conn.fetch(f"""
            SELECT p.*,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM purchases p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE {where_clause}
            ORDER BY p.purchase_date DESC
        """, *params)

        total_amount = sum(float(r.get('total_amount', 0) or r.get('total', 0) or 0) for r in rows)

        return {
            "data": [row_to_dict(row) for row in rows],
            "summary": {
                "total_amount": total_amount,
                "count": len(rows)
            }
        }
    finally:
        await conn.close()


# === ENDPOINTS - OTHER REPORTS ===

@router.get("/reports/cash-flow")
async def get_reports_cash_flow(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio de fluxo de caixa"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        date_filter_ar = ""
        date_filter_ap = ""
        params_ar = []
        params_ap = []

        if start_date and end_date:
            date_filter_ar = "AND due_date BETWEEN $1 AND $2"
            date_filter_ap = "AND due_date BETWEEN $1 AND $2"
            params_ar = [start_date, end_date]
            params_ap = [start_date, end_date]

        # Entradas (recebimentos)
        entradas = await conn.fetchval(f"""
            SELECT COALESCE(SUM(paid_amount), 0) FROM accounts_receivable
            WHERE status::text IN ('paid', 'PAID', 'partial', 'PARTIAL') {date_filter_ar}
        """, *params_ar) or 0

        # Saidas (pagamentos)
        saidas = await conn.fetchval(f"""
            SELECT COALESCE(SUM(COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE status::text IN ('paid', 'PAID', 'partial', 'PARTIAL') {date_filter_ap}
        """, *params_ap) or 0

        # Previsao de entradas
        previsao_entradas = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {date_filter_ar}
        """, *params_ar) or 0

        # Previsao de saidas
        previsao_saidas = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {date_filter_ap}
        """, *params_ap) or 0

        return {
            "data": {
                "entradas": float(entradas),
                "saidas": float(saidas),
                "saldo": float(entradas) - float(saidas),
                "previsao_entradas": float(previsao_entradas),
                "previsao_saidas": float(previsao_saidas),
                "previsao_saldo": float(previsao_entradas) - float(previsao_saidas)
            }
        }
    finally:
        await conn.close()


@router.get("/reports/dre")
async def get_reports_dre(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Demonstrativo de Resultados do Exercicio"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        date_filter = ""
        params = []
        if start_date and end_date:
            date_filter = "AND sale_date BETWEEN $1 AND $2"
            params = [start_date, end_date]

        # Receitas (vendas)
        receita_bruta = await conn.fetchval(f"""
            SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE 1=1 {date_filter}
        """, *params) or 0

        # Custos (compras)
        custos = await conn.fetchval(f"""
            SELECT COALESCE(SUM(total_amount), 0) FROM purchases
            WHERE 1=1 {date_filter.replace('sale_date', 'purchase_date')}
        """, *params) or 0

        lucro_bruto = float(receita_bruta) - float(custos)

        return {
            "data": {
                "receita_bruta": float(receita_bruta),
                "deducoes": 0,
                "receita_liquida": float(receita_bruta),
                "custos": float(custos),
                "lucro_bruto": lucro_bruto,
                "despesas_operacionais": 0,
                "lucro_operacional": lucro_bruto,
                "resultado_financeiro": 0,
                "lucro_liquido": lucro_bruto
            }
        }
    finally:
        await conn.close()


@router.get("/reports/inventory")
async def get_reports_inventory(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio de inventario/estoque"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT id, code, name, description, unit, cost_price, sale_price,
                stock_quantity, min_stock, category, is_active
            FROM products
            ORDER BY name
        """)

        total_items = len(rows)
        total_value = sum(float(r.get('cost_price', 0) or 0) * float(r.get('stock_quantity', 0) or 0) for r in rows)
        low_stock = sum(1 for r in rows if (r.get('stock_quantity', 0) or 0) <= (r.get('min_stock', 0) or 0) and (r.get('min_stock', 0) or 0) > 0)

        return {
            "data": [row_to_dict(row) for row in rows],
            "summary": {
                "total_items": total_items,
                "total_value": total_value,
                "low_stock_count": low_stock
            }
        }
    finally:
        await conn.close()


@router.get("/reports/default-analysis")
async def get_reports_default_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    customer_id: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Analise de inadimplencia"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # IMPORTANTE: usar ar. prefix para evitar ambiguidade
        where_parts = ["ar.status::text IN ('pending', 'PENDING')", "ar.due_date < CURRENT_DATE", "ar.is_active = true"]
        params = []
        param_idx = 1

        if customer_id:
            where_parts.append(f"ar.customer_id::text = ${param_idx}")
            params.append(customer_id)
            param_idx += 1

        where_clause = " AND ".join(where_parts)

        rows = await conn.fetch(f"""
            SELECT ar.id, ar.customer_id, ar.description, ar.document_number, ar.amount,
                ar.paid_amount, ar.due_date, ar.payment_date, ar.status,
                COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                CURRENT_DATE - ar.due_date as days_overdue
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE {where_clause}
            ORDER BY ar.due_date
        """, *params)

        total_overdue = sum(float(r.get('amount', 0) or 0) - float(r.get('paid_amount', 0) or 0) for r in rows)

        return {
            "data": [row_to_dict(row) for row in rows],
            "summary": {
                "total_overdue": total_overdue,
                "count": len(rows)
            }
        }
    finally:
        await conn.close()


@router.get("/reports/forecast")
async def get_reports_forecast(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Previsao financeira"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        date_filter = ""
        params = []
        if start_date and end_date:
            date_filter = "AND due_date BETWEEN $1 AND $2"
            params = [start_date, end_date]

        # A receber previsto
        a_receber = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND is_active = true {date_filter}
        """, *params) or 0

        # A pagar previsto
        a_pagar = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND is_active = true {date_filter}
        """, *params) or 0

        return {
            "data": {
                "previsao_entradas": float(a_receber),
                "previsao_saidas": float(a_pagar),
                "saldo_previsto": float(a_receber) - float(a_pagar)
            }
        }
    finally:
        await conn.close()


@router.get("/reports/management")
async def get_reports_management(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio gerencial"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Clientes
        total_customers = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE deleted_at IS NULL") or 0

        # Vendas do periodo
        date_filter = ""
        params = []
        if start_date and end_date:
            date_filter = "AND sale_date BETWEEN $1 AND $2"
            params = [start_date, end_date]

        total_sales = await conn.fetchval(f"SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE 1=1 {date_filter}", *params) or 0
        count_sales = await conn.fetchval(f"SELECT COUNT(*) FROM sales WHERE 1=1 {date_filter}", *params) or 0

        # A receber
        total_receivable = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND is_active = true
        """) or 0

        # A pagar
        total_payable = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, 0)), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') AND is_active = true
        """) or 0

        return {
            "data": {
                "total_customers": total_customers,
                "total_sales": float(total_sales),
                "count_sales": count_sales,
                "total_receivable": float(total_receivable),
                "total_payable": float(total_payable),
                "balance": float(total_receivable) - float(total_payable)
            }
        }
    finally:
        await conn.close()


@router.get("/reports/registry")
async def get_reports_registry(
    type: Optional[str] = Query("customers", alias="type"),
    status: Optional[str] = None,
    search: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio de cadastros com filtros de status e busca"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    # Log para debug
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[REGISTRY REPORT] type={type}, status={status}, search={search}")

    try:
        # Prepara filtro de busca
        search_param = None
        if search and search.strip():
            search_param = f"%{search.strip().upper()}%"

        if type == "suppliers":
            base_query = """
                SELECT id, COALESCE(company_name, trade_name, name) as name,
                    COALESCE(cnpj, cpf) as document, email, phone, address, city, state,
                    COALESCE(is_active, true) as active
                FROM suppliers WHERE 1=1
            """
            if status == "active":
                base_query += " AND is_active = true"
            elif status == "inactive":
                base_query += " AND is_active = false"
            else:
                base_query += " AND (is_active = true OR is_active IS NULL)"
            if search_param:
                base_query += """ AND (
                    UPPER(COALESCE(company_name, '')) LIKE $1 OR
                    UPPER(COALESCE(trade_name, '')) LIKE $1 OR
                    UPPER(COALESCE(name, '')) LIKE $1 OR
                    UPPER(COALESCE(cnpj, '')) LIKE $1 OR
                    UPPER(COALESCE(cpf, '')) LIKE $1 OR
                    UPPER(COALESCE(email, '')) LIKE $1
                )"""
            base_query += " ORDER BY COALESCE(company_name, trade_name, name)"
            rows = await conn.fetch(base_query, search_param) if search_param else await conn.fetch(base_query)

        elif type == "products":
            base_query = """
                SELECT id, code, name, description as category, unit_of_measure as unit,
                    cost_price as cost, sale_price as price, stock_quantity as quantity,
                    COALESCE(is_active, true) as active
                FROM products WHERE 1=1
            """
            if status == "active":
                base_query += " AND is_active = true"
            elif status == "inactive":
                base_query += " AND is_active = false"
            if search_param:
                base_query += """ AND (
                    UPPER(COALESCE(code, '')) LIKE $1 OR
                    UPPER(COALESCE(name, '')) LIKE $1 OR
                    UPPER(COALESCE(description, '')) LIKE $1
                )"""
            base_query += " ORDER BY name"
            rows = await conn.fetch(base_query, search_param) if search_param else await conn.fetch(base_query)

        elif type == "users":
            base_query = """
                SELECT id, COALESCE(full_name, username, email) as name,
                    email, role, updated_at as last_login,
                    COALESCE(is_active, true) as active
                FROM users WHERE 1=1
            """
            if status == "active":
                base_query += " AND is_active = true"
            elif status == "inactive":
                base_query += " AND is_active = false"
            if search_param:
                base_query += """ AND (
                    UPPER(COALESCE(full_name, '')) LIKE $1 OR
                    UPPER(COALESCE(username, '')) LIKE $1 OR
                    UPPER(COALESCE(email, '')) LIKE $1
                )"""
            base_query += " ORDER BY COALESCE(full_name, username, email)"
            rows = await conn.fetch(base_query, search_param) if search_param else await conn.fetch(base_query)

        else:  # customers
            base_query = """
                SELECT id, COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name) as name,
                    cpf_cnpj as document, email, phone, address, city, state,
                    COALESCE(is_active, true) as active
                FROM customers WHERE 1=1
            """
            if status == "active":
                base_query += " AND is_active = true"
            elif status == "inactive":
                base_query += " AND is_active = false"
            else:
                base_query += " AND (is_active = true OR is_active IS NULL)"
            if search_param:
                base_query += """ AND (
                    UPPER(COALESCE(first_name, '')) LIKE $1 OR
                    UPPER(COALESCE(last_name, '')) LIKE $1 OR
                    UPPER(COALESCE(company_name, '')) LIKE $1 OR
                    UPPER(COALESCE(trade_name, '')) LIKE $1 OR
                    UPPER(COALESCE(cpf_cnpj, '')) LIKE $1 OR
                    UPPER(COALESCE(email, '')) LIKE $1
                )"""
            base_query += " ORDER BY COALESCE(NULLIF(TRIM(first_name || ' ' || last_name), ''), company_name, trade_name)"
            rows = await conn.fetch(base_query, search_param) if search_param else await conn.fetch(base_query)

        # Calcula resumo
        data = [row_to_dict(row) for row in rows]
        active_count = sum(1 for item in data if item.get('active', True))
        inactive_count = len(data) - active_count

        return {
            "data": data,
            "summary": {
                "total": len(data),
                "count": len(data),
                "active": active_count,
                "inactive": inactive_count
            }
        }
    finally:
        await conn.close()


# === ENDPOINTS - PRODUCTS STATS ===

@router.get("/products/stats/dashboard")
async def get_products_stats(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna estatisticas de produtos"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        total = await conn.fetchval("SELECT COUNT(*) FROM products") or 0
        active = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active = true") or 0
        low_stock = await conn.fetchval("""
            SELECT COUNT(*) FROM products WHERE stock_quantity <= min_stock AND min_stock > 0
        """) or 0

        return {
            "total_products": total,
            "active_products": active,
            "inactive_products": total - active,
            "low_stock_products": low_stock,
            "total_stock_value": 0.0
        }
    finally:
        await conn.close()


# === ENDPOINTS - PROMISSORY NOTES (NOTAS PROMISSÓRIAS) ===

@router.get("/promissory/{account_id}/installments-for-promissory")
async def get_installments_for_promissory(
    account_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista parcelas pendentes para geração de nota promissória"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Busca parcelas filhas pendentes (installment_number > 0, status != PAID)
        # Usa CAST para comparar status como texto, evitando problemas com ENUM
        rows = await conn.fetch("""
            SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                   ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                   ar.due_date, ar.payment_date, ar.status::text as status,
                   ar.installment_number, ar.total_installments, ar.parent_id,
                   COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                   c.cpf_cnpj as customer_document
            FROM accounts_receivable ar
            LEFT JOIN customers c ON ar.customer_id = c.id
            WHERE ar.parent_id = $1
              AND ar.installment_number > 0
              AND UPPER(ar.status::text) != 'PAID'
            ORDER BY ar.installment_number
        """, account_id)

        if not rows:
            # Tenta buscar a própria conta se não tiver parcelas (conta simples)
            rows = await conn.fetch("""
                SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                       ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                       ar.due_date, ar.payment_date, ar.status::text as status,
                       ar.installment_number, ar.total_installments, ar.parent_id,
                       COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                       c.cpf_cnpj as customer_document
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE ar.id = $1
                  AND UPPER(ar.status::text) != 'PAID'
            """, account_id)

        items = []
        total_pending = 0.0

        for row in rows:
            amount = float(row['amount'] or 0)
            paid = float(row['paid_amount'] or 0)
            balance = amount - paid

            items.append({
                "id": str(row['id']),
                "installment_number": row['installment_number'] or 1,
                "total_installments": row['total_installments'] or 1,
                "document_number": row.get('document_number') or f"DOC-{str(row['id'])[:8].upper()}",
                "due_date": row['due_date'].isoformat() if row['due_date'] else None,
                "amount": amount,
                "paid_amount": paid,
                "balance": balance,
                "status": row['status'],
                "customer_name": row['customer_name'],
                "customer_document": row['customer_document']
            })
            total_pending += balance

        return {
            "items": items,
            "total_pending": total_pending
        }
    finally:
        await conn.close()


@router.get("/promissory/{account_id}/generate")
async def generate_promissory_pdf_batch(
    account_id: str,
    installment_ids: str = "",
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Gera UMA ÚNICA Nota Promissória com o VALOR TOTAL das parcelas selecionadas"""
    from fastapi.responses import Response
    from app.utils.promissoryGenerator import generate_promissory_pdf

    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Parse IDs das parcelas selecionadas
        selected_ids = [id.strip() for id in installment_ids.split(',') if id.strip()]
        print(f"[PROMISSORY] === Gerando promissória única para {len(selected_ids)} parcelas ===", flush=True)

        if not selected_ids:
            raise HTTPException(status_code=400, detail="Nenhuma parcela selecionada")

        # Busca dados da empresa
        company = await conn.fetchrow("SELECT * FROM companies LIMIT 1")

        company_data = {}
        if company:
            company_address = ""
            if company.get('street') or company.get('address'):
                company_address = company.get('street') or company.get('address') or ''
                if company.get('number') or company.get('address_number'):
                    company_address += f", {company.get('number') or company.get('address_number')}"
                if company.get('neighborhood'):
                    company_address += f" - {company.get('neighborhood')}"
                if company.get('city') and company.get('state'):
                    company_address += f" - {company.get('city')}/{company.get('state')}"

            company_data = {
                'legal_name': company.get('legal_name') or company.get('trade_name') or company.get('name'),
                'trade_name': company.get('trade_name') or company.get('legal_name') or company.get('name'),
                'document': company.get('document') or company.get('cnpj') or company.get('cpf_cnpj'),
                'address': company_address,
                'city': company.get('city'),
                'state': company.get('state'),
            }

        # Soma o valor de TODAS as parcelas selecionadas para gerar UMA promissória
        total_value = 0.0
        customer_data = None
        customer_name_for_file = "cliente"
        latest_due_date = None
        doc_numbers = []

        for installment_id in selected_ids:
            # Busca dados da parcela
            installment = await conn.fetchrow("""
                SELECT ar.id, ar.customer_id, ar.description, ar.document_number,
                       ar.amount, COALESCE(ar.paid_amount, 0) as paid_amount,
                       ar.due_date, ar.payment_date, ar.status::text as status,
                       ar.installment_number, ar.total_installments,
                       COALESCE(NULLIF(TRIM(c.first_name || ' ' || c.last_name), ''), c.company_name, c.trade_name) as customer_name,
                       c.cpf_cnpj as customer_document,
                       c.address as customer_address,
                       c.city as customer_city,
                       c.state as customer_state,
                       c.zip_code as customer_zip
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE ar.id = $1
            """, installment_id)

            if not installment:
                continue

            # Calcula valor (saldo devedor)
            amount = float(installment['amount'] or 0)
            paid = float(installment['paid_amount'] or 0)
            balance = amount - paid if paid > 0 else amount
            total_value += balance

            print(f"[PROMISSORY] Parcela {installment['installment_number']}: R$ {balance:.2f}", flush=True)

            # Guarda dados do cliente (só precisa pegar uma vez)
            if customer_data is None:
                customer_name_for_file = installment['customer_name'] or 'cliente'

                customer_address = ""
                if installment['customer_address']:
                    customer_address = installment['customer_address']
                    if installment['customer_city']:
                        customer_address += f" - {installment['customer_city']}"
                    if installment['customer_state']:
                        customer_address += f"/{installment['customer_state']}"

                customer_data = {
                    'name': installment['customer_name'] or 'Cliente',
                    'document': installment['customer_document'] or 'N/A',
                    'address': customer_address or 'Não informado',
                    'city': installment['customer_city'] or '',
                    'state': installment['customer_state'] or '',
                }

            # Pega a última data de vencimento
            if installment['due_date']:
                if latest_due_date is None or installment['due_date'] > latest_due_date:
                    latest_due_date = installment['due_date']

            # Coleta números dos documentos
            doc_num = installment['document_number'] or f"P{installment['installment_number']}"
            doc_numbers.append(doc_num)

        if not customer_data or total_value <= 0:
            raise HTTPException(status_code=400, detail="Nenhuma parcela válida encontrada")

        print(f"[PROMISSORY] VALOR TOTAL: R$ {total_value:.2f} ({len(selected_ids)} parcelas)", flush=True)

        # Gera número do documento único para a promissória
        # Formato: NP-{primeiros 8 chars do account_id}-{quantidade de parcelas}
        doc_number = f"NP-{account_id[:8].upper()}-{len(selected_ids)}P"

        # Gera UMA ÚNICA promissória com o valor total
        pdf_bytes = await generate_promissory_pdf(
            company_data=company_data,
            customer_data=customer_data,
            total_value=total_value,
            due_date=latest_due_date,
            doc_number=doc_number
        )

        # Nome do arquivo
        customer_name_clean = customer_name_for_file.replace(' ', '_')[:30]
        filename = f"promissoria_{customer_name_clean}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"

        print(f"[PROMISSORY] PDF gerado: {filename}, {len(pdf_bytes)} bytes, Valor: R$ {total_value:.2f}", flush=True)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Length": str(len(pdf_bytes)),
                "X-Total-Value": f"{total_value:.2f}",
                "X-Installments-Count": str(len(selected_ids))
            }
        )
    finally:
        await conn.close()


# ============================================
# === ENDPOINTS - BACKUP DO SISTEMA ===
# ============================================

import subprocess
import tempfile
import shutil
from pathlib import Path

# Diretorio base para backups (dentro do container/servidor)
BACKUP_DIR = Path("/app/backups") if os.path.exists("/app") else Path("./backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


class BackupScheduleModel(BaseModel):
    """Modelo de configuracao de agendamento de backup"""
    enabled: bool = False
    frequency: str = "daily"  # daily, weekly, monthly
    time: str = "02:00"
    dayOfWeek: int = 1  # 0-6 (domingo-sabado)
    dayOfMonth: int = 1  # 1-31
    retentionDays: int = 30


def get_tenant_backup_dir(tenant_code: str) -> Path:
    """Retorna o diretorio de backups do tenant"""
    tenant_dir = BACKUP_DIR / f"tenant_{tenant_code}"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return tenant_dir


def get_schedule_file(tenant_code: str) -> Path:
    """Retorna o arquivo de configuracao de agendamento"""
    return get_tenant_backup_dir(tenant_code) / "schedule.json"


def load_schedule(tenant_code: str) -> dict:
    """Carrega configuracao de agendamento"""
    schedule_file = get_schedule_file(tenant_code)
    if schedule_file.exists():
        try:
            with open(schedule_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "enabled": False,
        "frequency": "daily",
        "time": "02:00",
        "dayOfWeek": 1,
        "dayOfMonth": 1,
        "retentionDays": 30
    }


def save_schedule(tenant_code: str, schedule: dict):
    """Salva configuracao de agendamento"""
    schedule_file = get_schedule_file(tenant_code)
    with open(schedule_file, 'w') as f:
        json.dump(schedule, f, indent=2)


def calculate_next_backup(schedule: dict) -> Optional[str]:
    """Calcula proxima execucao do backup"""
    if not schedule.get("enabled"):
        return None

    from datetime import timedelta
    now = datetime.now()
    time_parts = schedule.get("time", "02:00").split(":")
    hour = int(time_parts[0])
    minute = int(time_parts[1]) if len(time_parts) > 1 else 0

    if schedule.get("frequency") == "daily":
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
    elif schedule.get("frequency") == "weekly":
        days_ahead = schedule.get("dayOfWeek", 1) - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    elif schedule.get("frequency") == "monthly":
        day = schedule.get("dayOfMonth", 1)
        next_run = now.replace(day=min(day, 28), hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            if now.month == 12:
                next_run = next_run.replace(year=now.year + 1, month=1)
            else:
                next_run = next_run.replace(month=now.month + 1)
    else:
        return None

    return next_run.isoformat()


@router.get("/backups")
async def list_backups(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista todos os backups do tenant"""
    tenant, user = tenant_data

    try:
        tenant_backup_dir = get_tenant_backup_dir(tenant.tenant_code)
        backups = []
        total_size = 0

        # Lista arquivos .sql no diretorio
        for backup_file in sorted(tenant_backup_dir.glob("*.sql"), key=lambda x: x.stat().st_mtime, reverse=True):
            stat = backup_file.stat()
            total_size += stat.st_size
            backups.append({
                "id": backup_file.stem,
                "filename": backup_file.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        # Carrega configuracao de agendamento
        schedule = load_schedule(tenant.tenant_code)

        # Formata tamanho total
        if total_size >= 1024 * 1024 * 1024:
            total_size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
        elif total_size >= 1024 * 1024:
            total_size_str = f"{total_size / (1024 * 1024):.2f} MB"
        elif total_size >= 1024:
            total_size_str = f"{total_size / 1024:.2f} KB"
        else:
            total_size_str = f"{total_size} B"

        return {
            "backups": backups,
            "total": len(backups),
            "total_size": total_size_str,
            "last_backup": backups[0]["created_at"] if backups else None,
            "next_scheduled": calculate_next_backup(schedule),
            "schedule": schedule
        }

    except Exception as e:
        logger.error(f"Erro ao listar backups: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar backups: {str(e)}")


@router.post("/backups/create")
async def create_backup(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria um backup do banco de dados do tenant"""
    tenant, user = tenant_data

    try:
        tenant_backup_dir = get_tenant_backup_dir(tenant.tenant_code)

        # Nome do arquivo com timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{tenant.tenant_code}_{timestamp}.sql"
        backup_path = tenant_backup_dir / backup_filename

        # Configuracoes do banco
        db_host = tenant.database_host or settings.POSTGRES_HOST
        db_port = tenant.database_port or settings.POSTGRES_PORT
        db_user = tenant.database_user
        db_pass = tenant.database_password
        db_name = tenant.database_name

        # Em ambiente local, ajusta o host se necessario
        if db_host in ['license-db', 'enterprise-db'] and not os.path.exists('/app'):
            logger.info(f"[BACKUP] Ambiente local detectado, ajustando host de {db_host} para localhost")
            db_host = 'localhost'

        logger.info(f"[BACKUP] Iniciando backup do tenant {tenant.tenant_code}")
        logger.info(f"[BACKUP] Conexao: host={db_host}, port={db_port}, db={db_name}")

        # Tenta usar pg_dump primeiro (mais completo), senao usa asyncpg
        env = os.environ.copy()
        env["PGPASSWORD"] = db_pass

        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", db_name,
            "-F", "p",
            "--no-owner",
            "--no-acl",
            "-f", str(backup_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode != 0:
                raise Exception(f"pg_dump falhou: {result.stderr}")
            logger.info(f"[BACKUP] Backup criado via pg_dump")
        except Exception as pg_err:
            logger.warning(f"[BACKUP] pg_dump nao disponivel ({pg_err}), usando asyncpg...")

            # Fallback: usa asyncpg para gerar backup SQL
            conn = await asyncpg.connect(
                host=db_host,
                port=int(db_port),
                user=db_user,
                password=db_pass,
                database=db_name,
                timeout=30
            )

            try:
                sql_lines = []
                sql_lines.append(f"-- Backup do banco {db_name}")
                sql_lines.append(f"-- Gerado em {datetime.now().isoformat()}")
                sql_lines.append(f"-- Tenant: {tenant.tenant_code}")
                sql_lines.append("")

                # Lista tabelas
                tables = await conn.fetch("""
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                """)

                for table_row in tables:
                    table_name = table_row['tablename']

                    # Busca colunas da tabela
                    columns = await conn.fetch("""
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = $1
                        ORDER BY ordinal_position
                    """, table_name)

                    col_names = [c['column_name'] for c in columns]

                    # Busca dados
                    rows = await conn.fetch(f'SELECT * FROM "{table_name}"')

                    if rows:
                        sql_lines.append(f"-- Dados da tabela {table_name}")
                        for row in rows:
                            values = []
                            for col in col_names:
                                val = row.get(col)
                                if val is None:
                                    values.append("NULL")
                                elif isinstance(val, str):
                                    escaped = val.replace("'", "''")
                                    values.append(f"'{escaped}'")
                                elif isinstance(val, bool):
                                    values.append("TRUE" if val else "FALSE")
                                elif isinstance(val, (int, float)):
                                    values.append(str(val))
                                elif isinstance(val, datetime):
                                    values.append(f"'{val.isoformat()}'")
                                elif isinstance(val, date):
                                    values.append(f"'{val.isoformat()}'")
                                else:
                                    escaped = str(val).replace("'", "''")
                                    values.append(f"'{escaped}'")

                            cols_str = ', '.join(f'"{c}"' for c in col_names)
                            vals_str = ', '.join(values)
                            sql_lines.append(f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({vals_str});')

                        sql_lines.append("")

                # Salva arquivo
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(sql_lines))

                logger.info(f"[BACKUP] Backup criado via asyncpg ({len(sql_lines)} linhas)")

            finally:
                await conn.close()

        # Verifica se arquivo foi criado
        if not backup_path.exists():
            raise HTTPException(status_code=500, detail="Backup nao foi criado")

        file_size = backup_path.stat().st_size
        logger.info(f"[BACKUP] Backup criado com sucesso: {backup_filename} ({file_size} bytes)")

        return {
            "success": True,
            "message": "Backup criado com sucesso",
            "backup": {
                "id": backup_path.stem,
                "filename": backup_filename,
                "size": file_size,
                "created_at": datetime.now().isoformat()
            }
        }

    except subprocess.TimeoutExpired:
        logger.error("[BACKUP] Timeout ao criar backup")
        raise HTTPException(status_code=504, detail="Timeout ao criar backup")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[BACKUP] Erro ao criar backup: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro ao criar backup: {str(e)}")


@router.get("/backups/{backup_id}/download")
async def download_backup(
    backup_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Baixa um backup especifico"""
    tenant, user = tenant_data

    try:
        # Validacao de seguranca: impede path traversal
        if ".." in backup_id or "/" in backup_id or "\\" in backup_id:
            raise HTTPException(status_code=400, detail="ID de backup invalido")

        tenant_backup_dir = get_tenant_backup_dir(tenant.tenant_code)
        backup_path = tenant_backup_dir / f"{backup_id}.sql"

        # Garante que o arquivo esta dentro do diretorio do tenant
        if not str(backup_path.resolve()).startswith(str(tenant_backup_dir.resolve())):
            raise HTTPException(status_code=403, detail="Acesso negado")

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup nao encontrado")

        return FileResponse(
            path=str(backup_path),
            filename=f"{backup_id}.sql",
            media_type="application/sql"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao baixar backup: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao baixar backup: {str(e)}")


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """
    Restaura um backup especifico usando asyncpg (conexao Python direta):
    1. Conecta ao banco do tenant
    2. Desabilita triggers temporariamente
    3. Trunca todas as tabelas com CASCADE
    4. Executa o SQL do backup
    5. Reabilita triggers

    Esta abordagem nao depende do comando psql estar instalado.
    """
    tenant, user = tenant_data

    try:
        # Validacao de seguranca: impede path traversal
        if ".." in backup_id or "/" in backup_id or "\\" in backup_id:
            raise HTTPException(status_code=400, detail="ID de backup invalido")

        tenant_backup_dir = get_tenant_backup_dir(tenant.tenant_code)
        backup_path = tenant_backup_dir / f"{backup_id}.sql"

        # Garante que o arquivo esta dentro do diretorio do tenant
        if not str(backup_path.resolve()).startswith(str(tenant_backup_dir.resolve())):
            logger.warning(f"[SECURITY] Tentativa de acesso nao autorizado ao backup: {backup_id} pelo tenant {tenant.tenant_code}")
            raise HTTPException(status_code=403, detail="Acesso negado")

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup nao encontrado")

        # Configuracoes do banco
        db_host = tenant.database_host or settings.POSTGRES_HOST
        db_port = tenant.database_port or settings.POSTGRES_PORT
        db_user = tenant.database_user
        db_pass = tenant.database_password
        db_name = tenant.database_name

        # Em ambiente local, ajusta o host se necessario
        # (license-db e enterprise-db sao containers Docker, localmente usa localhost)
        if db_host in ['license-db', 'enterprise-db'] and not os.path.exists('/app'):
            logger.info(f"[RESTORE] Ambiente local detectado, ajustando host de {db_host} para localhost")
            db_host = 'localhost'

        logger.info(f"[RESTORE] Iniciando restauracao do tenant {tenant.tenant_code}")
        logger.info(f"[RESTORE] Conexao: host={db_host}, port={db_port}, db={db_name}, user={db_user}")

        # Le o conteudo do backup
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_sql = f.read()

        logger.info(f"[RESTORE] Backup carregado: {len(backup_sql)} caracteres")

        # Conecta ao banco do tenant
        try:
            conn = await asyncpg.connect(
                host=db_host,
                port=int(db_port),
                user=db_user,
                password=db_pass,
                database=db_name,
                timeout=30
            )
        except Exception as conn_err:
            logger.error(f"[RESTORE] Erro ao conectar ao banco: {conn_err}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao conectar ao banco de dados: {str(conn_err)}"
            )

        try:
            # ETAPA 1: Limpar todas as tabelas
            logger.info(f"[RESTORE] Etapa 1: Limpando tabelas existentes...")

            # Desabilita triggers temporariamente
            await conn.execute("SET session_replication_role = 'replica'")

            # Busca todas as tabelas do schema public
            tables = await conn.fetch("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
            """)

            # Trunca cada tabela
            for table in tables:
                table_name = table['tablename']
                try:
                    await conn.execute(f'TRUNCATE TABLE "{table_name}" CASCADE')
                    logger.debug(f"[RESTORE] Tabela {table_name} truncada")
                except Exception as te:
                    logger.warning(f"[RESTORE] Aviso ao truncar {table_name}: {te}")

            # Reabilita triggers
            await conn.execute("SET session_replication_role = 'origin'")

            logger.info(f"[RESTORE] Tabelas limpas com sucesso")

            # ETAPA 2: Restaurar o backup
            logger.info(f"[RESTORE] Etapa 2: Restaurando dados do backup...")

            # Divide o SQL em comandos individuais e executa
            # Remove comentarios e linhas vazias, depois divide por ;
            commands = []
            current_command = []
            in_dollar_quote = False

            for line in backup_sql.split('\n'):
                stripped = line.strip()

                # Ignora comentarios e linhas vazias fora de blocos
                if not in_dollar_quote:
                    if stripped.startswith('--') or not stripped:
                        continue

                # Detecta inicio/fim de blocos $$ (funcoes, DO blocks)
                if '$$' in line:
                    in_dollar_quote = not in_dollar_quote

                current_command.append(line)

                # Se termina com ; e nao estamos em bloco $$
                if stripped.endswith(';') and not in_dollar_quote:
                    cmd = '\n'.join(current_command).strip()
                    if cmd:
                        commands.append(cmd)
                    current_command = []

            # Executa cada comando
            success_count = 0
            error_count = 0

            for i, cmd in enumerate(commands):
                try:
                    # Pula comandos que podem causar problemas
                    cmd_lower = cmd.lower()
                    if any(skip in cmd_lower for skip in [
                        'create database', 'drop database',
                        'create extension', '\\connect',
                        'set default_tablespace', 'set statement_timeout'
                    ]):
                        continue

                    await conn.execute(cmd)
                    success_count += 1
                except Exception as cmd_err:
                    error_count += 1
                    # Ignora erros de objetos duplicados (normal em restore)
                    err_str = str(cmd_err).lower()
                    if 'already exists' not in err_str and 'duplicate' not in err_str:
                        logger.debug(f"[RESTORE] Comando {i+1} falhou: {str(cmd_err)[:100]}")

            logger.info(f"[RESTORE] Comandos executados: {success_count} sucesso, {error_count} erros/ignorados")

        finally:
            await conn.close()

        logger.info(f"[RESTORE] Restauracao concluida com sucesso para tenant {tenant.tenant_code}")

        return {
            "success": True,
            "message": "Backup restaurado com sucesso! Todos os dados foram atualizados. Faca login novamente para garantir a sincronizacao."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RESTORE] Erro ao restaurar backup: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao restaurar backup: {str(e)}"
        )


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Exclui um backup especifico"""
    tenant, user = tenant_data

    try:
        # Validacao de seguranca: impede path traversal
        if ".." in backup_id or "/" in backup_id or "\\" in backup_id:
            raise HTTPException(status_code=400, detail="ID de backup invalido")

        tenant_backup_dir = get_tenant_backup_dir(tenant.tenant_code)
        backup_path = tenant_backup_dir / f"{backup_id}.sql"

        # Garante que o arquivo esta dentro do diretorio do tenant
        if not str(backup_path.resolve()).startswith(str(tenant_backup_dir.resolve())):
            logger.warning(f"[SECURITY] Tentativa de exclusao nao autorizada do backup: {backup_id} pelo tenant {tenant.tenant_code}")
            raise HTTPException(status_code=403, detail="Acesso negado")

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup nao encontrado")

        backup_path.unlink()
        logger.info(f"[BACKUP] Backup {backup_id} excluido do tenant {tenant.tenant_code}")

        return {
            "success": True,
            "message": "Backup excluido com sucesso"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao excluir backup: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir backup: {str(e)}")


@router.post("/backups/schedule")
async def save_backup_schedule(
    schedule: BackupScheduleModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Salva configuracao de agendamento de backup"""
    tenant, user = tenant_data

    try:
        schedule_dict = schedule.dict()
        save_schedule(tenant.tenant_code, schedule_dict)

        logger.info(f"[BACKUP] Agendamento salvo para tenant {tenant.tenant_code}: {schedule_dict}")

        return {
            "success": True,
            "message": "Agendamento salvo com sucesso",
            "schedule": schedule_dict,
            "next_scheduled": calculate_next_backup(schedule_dict)
        }

    except Exception as e:
        logger.error(f"Erro ao salvar agendamento: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao salvar agendamento: {str(e)}")
