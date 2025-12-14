"""
License Server - Tenant API Gateway
API Gateway Multi-Tenant que roteia requisicoes para o banco correto

Este modulo serve como um "proxy" que:
1. Recebe requisicoes autenticadas com JWT
2. Extrai o tenant_code do token
3. Conecta ao banco do tenant correto
4. Executa a operacao e retorna os dados
"""
from datetime import datetime
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
import logging

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
    """Converte string ISO para date object - asyncpg NAO aceita strings para campos DATE"""
    from datetime import date, datetime
    if val is None or val == '' or val == 'null':
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        if 'T' in val:
            return datetime.fromisoformat(val.replace('Z', '+00:00')).date()
        else:
            return datetime.strptime(val, '%Y-%m-%d').date()
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

# Cache de indices para evitar chamadas repetidas
_indices_cache = {}

async def fetch_bcb_index(codigo_serie: int, data_inicio, data_fim):
    """Busca indice do BCB"""
    import httpx
    from datetime import date

    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados"
    params = {
        "formato": "json",
        "dataInicial": data_inicio.strftime("%d/%m/%Y"),
        "dataFinal": data_fim.strftime("%d/%m/%Y"),
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Erro ao buscar indice BCB {codigo_serie}: {e}")
        return []

async def calculate_correction_factor(tipo_indice: str, data_inicial, data_final):
    """
    Calcula fator de correcao monetaria entre duas datas
    METODOLOGIA TJSP/DR Calc (atualizada Lei 14.905/2024):
    - Primeiro mes: mes SEGUINTE ao vencimento (exclui o mes do vencimento)
    - Ultimo mes: mes ANTERIOR ao termo
    - Para IPCA-E: usa IPCA-E ate agosto/2024 e IPCA-15 a partir de setembro/2024
      (conforme nova tabela pratica TJSP publicada em set/2024)
    - NAO projeta indices futuros - usa apenas indices publicados
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

    # METODOLOGIA TJSP: Primeiro mes = MES SEGUINTE ao vencimento
    # Exemplo: vencimento 13/07/2023 -> primeiro indice = agosto/2023
    if data_inicial.month == 12:
        primeiro_mes = date(data_inicial.year + 1, 1, 1)
    else:
        primeiro_mes = date(data_inicial.year, data_inicial.month + 1, 1)

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

    logger.debug(f"Correcao {tipo_indice}: {primeiro_mes} a {ultimo_mes}, fator={fator:.6f}")
    return fator

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

def get_interest_rate_for_date(tipo_juros: str, data_ref, percentual_personalizado=None):
    """
    Retorna taxa de juros mensal conforme a data de referencia
    Considera a Lei 14.905/2024 que altera as taxas a partir de 30/08/2024
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
    elif tipo_juros in ["juros_legais_6_12", "juros_legais_selic_lei_14905", "taxa_legal_selic_ipca"]:
        # Lei 14.905/2024: Taxa Legal = SELIC - IPCA a partir de 30/08/2024
        if data_ref < marco_cc2002:
            return 0.5  # 6% a.a. = 0.5% a.m. (antes do CC 2002)
        elif data_ref < marco_lei_14905:
            return 1.0  # 12% a.a. = 1% a.m. (CC 2002 até Lei 14.905)
        else:
            return 0.65  # ~7.8% a.a. = 0.65% a.m. (SELIC - IPCA aproximado)
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
    Compatível com DR Calc.
    """
    from datetime import date, datetime
    from calendar import monthrange

    if isinstance(data_inicial, str):
        data_inicial = datetime.strptime(data_inicial, "%Y-%m-%d").date()
    if isinstance(data_final, str):
        data_final = datetime.strptime(data_final, "%Y-%m-%d").date()

    if data_final <= data_inicial:
        return {"percentual_total": 0.0, "valor_juros": 0.0}

    percentual_total = 0.0
    valor_juros = 0.0
    valor_acumulado = valor_base

    # Itera mês a mês do período
    data_atual = data_inicial
    while data_atual < data_final:
        # Determina o último dia do mês atual
        _, ultimo_dia = monthrange(data_atual.year, data_atual.month)
        fim_mes = date(data_atual.year, data_atual.month, ultimo_dia)

        # Data final do período deste mês (não pode ultrapassar data_final)
        data_fim_periodo = min(fim_mes, data_final)

        # Calcula dias neste mês
        if data_atual == data_inicial:
            # Primeiro mês: conta a partir do dia do vencimento
            dias_no_mes = (data_fim_periodo - data_atual).days
        else:
            # Meses seguintes: mês completo ou até data_final
            dias_no_mes = (data_fim_periodo - date(data_atual.year, data_atual.month, 1)).days + 1

        if dias_no_mes <= 0:
            break

        # Fração do mês (considerando mês comercial de 30 dias)
        fracao_mes = dias_no_mes / 30.0

        # Determina a taxa aplicável para este mês
        taxa_mes = get_interest_rate_for_date(tipo_juros, data_atual, percentual_personalizado)

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
    """Calcula um debito com correcao, juros e multa - compatível com DR Calc"""
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

    # 1. Correcao Monetaria
    fator = await calculate_correction_factor(tipo_indice, data_vencimento, termo_final)
    valor_corrigido = valor_original * fator

    # 2. Juros de Mora - calcula mês a mês respeitando Lei 14.905/2024
    if tipo_juros_mora == "nao_aplicar":
        percentual_juros_total = 0.0
        valor_juros = 0.0
    elif percentual_juros_mora:
        # Taxa fixa informada pelo usuário
        meses = calculate_interest_months(data_vencimento, termo_final)
        taxa = float(percentual_juros_mora)
        percentual_juros_total = taxa * meses
        if capitalizar:
            valor_juros = valor_corrigido * ((1 + taxa/100) ** meses - 1)
        else:
            valor_juros = valor_corrigido * (taxa / 100) * meses
    else:
        # Taxa legal - calcular mês a mês (Lei 14.905/2024)
        juros_result = await calculate_legal_interest_monthly(
            valor_corrigido, data_vencimento, termo_final, tipo_juros_mora,
            percentual_juros_mora, capitalizar
        )
        percentual_juros_total = juros_result["percentual_total"]
        valor_juros = juros_result["valor_juros"]

    # 3. Multa
    percentual_multa_val = float(percentual_multa) if percentual_multa else 0
    valor_multa = valor_corrigido * (percentual_multa_val / 100)

    # 4. Total
    valor_total = valor_corrigido + valor_juros + valor_multa

    return {
        **debito,
        "fator_correcao": round(fator, 6),
        "valor_corrigido": round(valor_corrigido, 2),
        "percentual_juros_mora": round(percentual_juros_total, 2),
        "valor_juros_mora": round(valor_juros, 2),
        "valor_multa": round(valor_multa, 2),
        "valor_total": round(valor_total, 2),
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
    """Busca calculo juridico por ID - retorna dados do result_data mesclados"""
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

        # Extrai result_data (JSONB) e mescla com o resultado
        # O frontend espera os dados diretamente (nome, debitos, etc)
        if result.get("result_data"):
            result_data = result["result_data"]
            # Se for string, faz parse
            if isinstance(result_data, str):
                result_data = json.loads(result_data)
            # Mescla os dados do result_data no resultado
            result.update(result_data)

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

        # Armazena dados COM CALCULOS no result_data (JSONB)
        result_data = json.dumps(data_calculado)

        await conn.execute("""
            INSERT INTO legal_calculations
            (id, title, description, calculation_type, principal_amount, start_date, end_date, result_data, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, calc_id, title, description, calculation_type, principal_amount, start_date, end_date, result_data)

        return {"id": calc_id, "message": "Calculo criado com sucesso", "data": data_calculado}
    except Exception as e:
        logger.error(f"Erro ao criar calculo juridico: {str(e)}")
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
                title = $1,
                description = $2,
                calculation_type = $3,
                principal_amount = $4,
                start_date = $5,
                end_date = $6,
                result_data = $7::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $8
        """, title, description, calculation_type, principal_amount, start_date, end_date, result_data, calc_id)

        return {"id": calc_id, "message": "Calculo atualizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
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

        # Extrai dados do result_data
        data = {}
        if result.get("result_data"):
            result_data = result["result_data"]
            if isinstance(result_data, str):
                data = json.loads(result_data)
            else:
                data = result_data

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
                title = $1,
                description = $2,
                calculation_type = $3,
                principal_amount = $4,
                start_date = $5,
                end_date = $6,
                result_data = $7::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $8
        """, title, description, calculation_type, principal_amount, start_date, end_date, result_data_json, calc_id)

        return {"id": calc_id, "message": "Calculo recalculado com sucesso", "data": data_calculado}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao recalcular: {str(e)}")
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
            where_parts.append(f"UPPER(ar.status::text) = ${param_idx}")
            params.append(status.upper())
            param_idx += 1

        where_clause = " AND ".join(where_parts) + filter_clause

        # Lista de contas
        rows = await conn.fetch(f"""
            SELECT ar.id, ar.customer_id, ar.description, ar.document_number, ar.amount,
                ar.paid_amount, ar.due_date, ar.payment_date, ar.status, ar.payment_method,
                ar.installment_number, ar.total_installments, ar.parent_id, ar.notes,
                ar.is_active, ar.created_at, ar.updated_at,
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

        return {
            "data": [row_to_dict(row) for row in rows],
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
            where_parts.append(f"UPPER(ap.status::text) = ${param_idx}")
            params.append(status.upper())
            param_idx += 1

        where_clause = " AND ".join(where_parts)

        # Lista de contas - usa apenas amount_paid (schema padrão)
        rows = await conn.fetch(f"""
            SELECT ap.id, ap.supplier_id, ap.description, ap.document_number, ap.amount,
                COALESCE(ap.amount_paid, 0) as paid_amount,
                ap.due_date, ap.payment_date, ap.status, ap.payment_method,
                ap.notes, ap.created_at, ap.updated_at,
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

        return {
            "data": [row_to_dict(row) for row in rows],
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
