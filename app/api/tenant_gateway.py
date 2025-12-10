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
    code: Optional[str] = None
    name: str
    description: Optional[str] = None
    unit: str = "UN"
    cost_price: float = 0
    sale_price: float = 0
    stock_quantity: float = 0
    min_stock: float = 0
    category: Optional[str] = None
    barcode: Optional[str] = None
    is_active: bool = True


class SupplierModel(BaseModel):
    id: Optional[str] = None
    name: str
    document: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    address_number: Optional[str] = None
    address_complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None
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
                    COALESCE(first_name || ' ' || last_name, company_name, trade_name) as name,
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
                    COALESCE(first_name || ' ' || last_name, company_name, trade_name) as name,
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
                COALESCE(first_name || ' ' || last_name, company_name, trade_name) as name,
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
        # Schema legado usa sku em vez de code, barcode_ean em vez de barcode
        if search:
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
            rows = await conn.fetch("""
                SELECT *,
                    COALESCE(code, sku) as code,
                    COALESCE(barcode_ean, barcode_ean128) as barcode,
                    unit_of_measure as unit
                FROM products
                ORDER BY name
                LIMIT $1 OFFSET $2
            """, limit, skip)

        return [row_to_dict(row) for row in rows]
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


@router.post("/products")
async def create_product(
    product: ProductModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria novo produto"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            INSERT INTO products (code, name, description, unit, cost_price, sale_price,
                                  stock_quantity, min_stock, category, barcode, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """, product.code, product.name, product.description, product.unit,
           product.cost_price, product.sale_price, product.stock_quantity,
           product.min_stock, product.category, product.barcode, product.is_active)

        return row_to_dict(row)
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
        row = await conn.fetchrow("""
            UPDATE products SET
                code = $2, name = $3, description = $4, unit = $5, cost_price = $6,
                sale_price = $7, stock_quantity = $8, min_stock = $9, category = $10,
                barcode = $11, is_active = $12, updated_at = $13
            WHERE id = $1
            RETURNING *
        """, product_id, product.code, product.name, product.description, product.unit,
           product.cost_price, product.sale_price, product.stock_quantity,
           product.min_stock, product.category, product.barcode, product.is_active,
           datetime.utcnow())

        if not row:
            raise HTTPException(status_code=404, detail="Produto nao encontrado")
        return row_to_dict(row)
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

        return [row_to_dict(row) for row in rows]
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
        row = await conn.fetchrow("""
            INSERT INTO suppliers (name, document, email, phone, address, address_number,
                                   address_complement, neighborhood, city, state, zip_code,
                                   notes, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
        """, supplier.name, supplier.document, supplier.email, supplier.phone,
           supplier.address, supplier.address_number, supplier.address_complement,
           supplier.neighborhood, supplier.city, supplier.state, supplier.zip_code,
           supplier.notes, supplier.is_active)

        return row_to_dict(row)
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
        row = await conn.fetchrow("""
            UPDATE suppliers SET
                name = $2, document = $3, email = $4, phone = $5, address = $6,
                address_number = $7, address_complement = $8, neighborhood = $9,
                city = $10, state = $11, zip_code = $12, notes = $13, is_active = $14,
                updated_at = $15
            WHERE id = $1
            RETURNING *
        """, supplier_id, supplier.name, supplier.document, supplier.email,
           supplier.phone, supplier.address, supplier.address_number,
           supplier.address_complement, supplier.neighborhood, supplier.city,
           supplier.state, supplier.zip_code, supplier.notes, supplier.is_active,
           datetime.utcnow())

        if not row:
            raise HTTPException(status_code=404, detail="Fornecedor nao encontrado")
        return row_to_dict(row)
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
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, paid_amount, 0)), 0) FROM accounts_payable
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
                COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
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
        # Schema legado: suppliers usa company_name/trade_name/name
        rows = await conn.fetch("""
            SELECT p.*,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM purchases p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            ORDER BY p.purchase_date DESC
            LIMIT $1 OFFSET $2
        """, limit, skip)

        return [row_to_dict(row) for row in rows]
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
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista contas a receber do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Conta total para paginacao
        total = await conn.fetchval("SELECT COUNT(*) FROM accounts_receivable") or 0

        # Schema legado: customers usa first_name/last_name em vez de name
        # IMPORTANTE: Retorna apenas contas PAI (installment_number = 0)
        # Inclui next_due_date = próxima parcela a vencer (não paga)
        if search:
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                        COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                        COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                        COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                    COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
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
                COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
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

            # Calcula balance (saldo devedor)
            amount = float(row_dict.get("amount") or 0)
            paid_amount = float(row_dict.get("paid_amount") or 0)
            row_dict["balance"] = amount - paid_amount

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
    """Atualiza conta a receber"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            UPDATE accounts_receivable SET
                customer_id = $2, description = $3, amount = $4, paid_amount = $5,
                due_date = $6, status = $7, updated_at = $8
            WHERE id = $1
            RETURNING *
        """,
            account_id,
            account.get("customer_id"),
            account.get("description", ""),
            float(account.get("amount", 0)),
            float(account.get("paid_amount", 0)),
            account.get("due_date"),
            account.get("status", "pending"),
            datetime.utcnow()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conta nao encontrada")
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
                   COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                       COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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

        # Gera o PDF Faraônico
        pdf_bytes = await generate_receipt_pdf(installment_data, customer_data, company_data)

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
                   COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                       COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                COALESCE(first_name || ' ' || last_name, company_name, trade_name) as name,
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
            last_installment_amount = total_amount - (installment_amount * (num_installments - 1))

            for i in range(1, num_installments + 1):
                installment_id = str(uuid.uuid4())
                # Calcula data de vencimento (incrementa mês a cada parcela)
                installment_due_date = due_date + relativedelta(months=i-1)

                # Valor da parcela (última pode ser diferente por arredondamento)
                amount = last_installment_amount if i == num_installments else installment_amount

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
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista contas a pagar do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Conta total para paginacao
        total = await conn.fetchval("SELECT COUNT(*) FROM accounts_payable") or 0

        # Schema legado: suppliers usa company_name/trade_name/name
        if search:
            rows = await conn.fetch("""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE s.company_name ILIKE $1 OR s.trade_name ILIKE $1
                    OR s.name ILIKE $1 OR ap.description ILIKE $1
                ORDER BY ap.due_date
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        elif status:
            # Converte status para UPPERCASE para comparar com ENUM
            status_upper = status.upper()
            rows = await conn.fetch("""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE UPPER(ap.status::text) = $3
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip, status_upper)
        else:
            rows = await conn.fetch("""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip)

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
            account.get("status", "pending")
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
            account.get("status", "pending"),
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

        # Determina novo status
        new_status = "paid" if new_paid >= total_amount else "partial"

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
        return row_to_dict(row)
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
        
        # Salva no container (diretório /app/uploads/logos)
        upload_dir = "/app/uploads/logos"
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
            filepath = f"/app/uploads/{row['logo_path']}"
            if os.path.exists(filepath):
                os.remove(filepath)

        await conn.execute("UPDATE companies SET logo_path = NULL, updated_at = NOW()")
        return {"success": True, "message": "Logo removido com sucesso"}
    finally:
        await conn.close()


# === ENDPOINTS - LEGAL CALCULATIONS ===

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

        # Contas a receber - pendentes (exclui contas PAI de parcelamentos para evitar duplicacao)
        # Inclui: parcelas filhas (parent_id IS NOT NULL) + contas simples (sem parcelas)
        receivables_pending = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL')
            AND is_active = true
            AND (
                parent_id IS NOT NULL  -- Parcelas filhas
                OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1))  -- Contas simples
            )
        """) or 0

        # Contas a receber - recebidas (mesma logica: filhas + simples)
        receivables_received = await conn.fetchval("""
            SELECT COALESCE(SUM(COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('paid', 'PAID', 'partial', 'PARTIAL')
            AND is_active = true
            AND (
                parent_id IS NOT NULL
                OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1))
            )
        """) or 0

        # Contas a receber - vencidas (mesma logica: filhas + simples)
        receivables_overdue = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL')
            AND due_date < CURRENT_DATE
            AND is_active = true
            AND (
                parent_id IS NOT NULL
                OR (parent_id IS NULL AND (total_installments IS NULL OR total_installments <= 1))
            )
        """) or 0

        # Contas a pagar pendentes - schema legado usa amount_paid ou balance
        payables_pending = await conn.fetchval("""
            SELECT COALESCE(SUM(COALESCE(balance, amount - COALESCE(amount_paid, 0))), 0) FROM accounts_payable
            WHERE status::text IN ('pending', 'PENDING')
        """) or 0

        return {
            "customers_count": customers_count,
            "products_count": products_count,
            "suppliers_count": suppliers_count,
            "employees_count": employees_count,
            "sales_month": float(sales_month),
            "accounts_receivable": float(receivables_pending),
            "accounts_payable": float(payables_pending),
            # Campos adicionais para o frontend
            "receivable_pending": float(receivables_pending),
            "receivable_received": float(receivables_received),
            "receivable_overdue": float(receivables_overdue),
            "payable_pending": float(payables_pending),
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
    """Retorna estatisticas detalhadas de contas a pagar"""
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

        return {
            "total_value": float(total),
            "paid_value": float(paid),
            "pending_value": float(pending),
            "overdue_value": 0.0,
            "average_ticket": 0.0
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
            return row_to_dict(row)
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
                COALESCE(first_name || ' ' || last_name, company_name, trade_name) as name,
                cpf_cnpj as document, email, phone
            FROM customers
            ORDER BY COALESCE(first_name || ' ' || last_name, company_name, trade_name)
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
                COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
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
        # IMPORTANTE: usar ap.is_active para evitar ambiguidade com suppliers.is_active
        where_parts = ["1=1", "ap.is_active = true"]
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

        # Lista de contas - schema legado usa amount_paid em vez de paid_amount
        rows = await conn.fetch(f"""
            SELECT ap.id, ap.supplier_id, ap.description, ap.document_number, ap.amount,
                COALESCE(ap.amount_paid, ap.paid_amount, 0) as paid_amount,
                ap.due_date, ap.payment_date, ap.status, ap.payment_method,
                ap.notes, ap.is_active, ap.created_at, ap.updated_at,
                COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
            FROM accounts_payable ap
            LEFT JOIN suppliers s ON ap.supplier_id = s.id
            WHERE {where_clause}
            ORDER BY ap.due_date
        """, *params)

        # Totais - tenta ambos os nomes de coluna
        total_value = sum(float(r.get('amount', 0) or 0) for r in rows)
        total_paid = sum(float(r.get('amount_paid', 0) or r.get('paid_amount', 0) or 0) for r in rows)
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
                COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
            SELECT COALESCE(SUM(COALESCE(amount_paid, paid_amount, 0)), 0) FROM accounts_payable
            WHERE status::text IN ('paid', 'PAID', 'partial', 'PARTIAL') {date_filter_ap}
        """, *params_ap) or 0

        # Previsao de entradas
        previsao_entradas = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(paid_amount, 0)), 0) FROM accounts_receivable
            WHERE status::text IN ('pending', 'PENDING', 'partial', 'PARTIAL') {date_filter_ar}
        """, *params_ar) or 0

        # Previsao de saidas
        previsao_saidas = await conn.fetchval(f"""
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, paid_amount, 0)), 0) FROM accounts_payable
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
                COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, paid_amount, 0)), 0) FROM accounts_payable
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
            SELECT COALESCE(SUM(amount - COALESCE(amount_paid, paid_amount, 0)), 0) FROM accounts_payable
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
    type: Optional[str] = "customers",
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Relatorio de cadastros"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        if type == "suppliers":
            rows = await conn.fetch("""
                SELECT id, COALESCE(company_name, trade_name, name) as name,
                    cpf_cnpj as document, email, phone, address, city, state
                FROM suppliers WHERE deleted_at IS NULL
                ORDER BY COALESCE(company_name, trade_name, name)
            """)
        elif type == "products":
            rows = await conn.fetch("""
                SELECT id, code, name, description, unit, cost_price, sale_price, stock_quantity
                FROM products
                ORDER BY name
            """)
        else:  # customers
            rows = await conn.fetch("""
                SELECT id, COALESCE(first_name || ' ' || last_name, company_name, trade_name) as name,
                    cpf_cnpj as document, email, phone, address, city, state
                FROM customers WHERE deleted_at IS NULL
                ORDER BY COALESCE(first_name || ' ' || last_name, company_name, trade_name)
            """)

        return {
            "data": [row_to_dict(row) for row in rows],
            "summary": {
                "count": len(rows)
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
                   COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                       COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
                       COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name,
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
