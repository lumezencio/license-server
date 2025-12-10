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
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
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
    """Cria novo cliente"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            INSERT INTO customers (name, document, email, phone, address, address_number,
                                   address_complement, neighborhood, city, state, zip_code,
                                   notes, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING *
        """, customer.name, customer.document, customer.email, customer.phone,
           customer.address, customer.address_number, customer.address_complement,
           customer.neighborhood, customer.city, customer.state, customer.zip_code,
           customer.notes, customer.is_active)

        return row_to_dict(row)
    finally:
        await conn.close()


@router.put("/customers/{customer_id}")
async def update_customer(
    customer_id: str,
    customer: CustomerModel,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza cliente"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            UPDATE customers SET
                name = $2, document = $3, email = $4, phone = $5, address = $6,
                address_number = $7, address_complement = $8, neighborhood = $9,
                city = $10, state = $11, zip_code = $12, notes = $13, is_active = $14,
                updated_at = $15
            WHERE id = $1
            RETURNING *
        """, customer_id, customer.name, customer.document, customer.email,
           customer.phone, customer.address, customer.address_number,
           customer.address_complement, customer.neighborhood, customer.city,
           customer.state, customer.zip_code, customer.notes, customer.is_active,
           datetime.utcnow())

        if not row:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        return row_to_dict(row)
    finally:
        await conn.close()


@router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Remove cliente"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        result = await conn.execute(
            "DELETE FROM customers WHERE id = $1",
            customer_id
        )
        if result == "DELETE 0":
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
        if search:
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE c.first_name ILIKE $1 OR c.last_name ILIKE $1
                    OR c.company_name ILIKE $1 OR ar.description ILIKE $1
                ORDER BY ar.due_date
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        elif status:
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE ar.status = $3
                ORDER BY ar.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip, status)
        else:
            rows = await conn.fetch("""
                SELECT ar.*,
                    COALESCE(c.first_name || ' ' || c.last_name, c.company_name, c.trade_name) as customer_name
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
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
        row = await conn.fetchrow("""
            INSERT INTO accounts_receivable (
                customer_id, description, amount, paid_amount, due_date, status,
                installment_number, total_installments, parent_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """,
            account.get("customer_id"),
            account.get("description", ""),
            float(account.get("amount", 0)),
            float(account.get("paid_amount", 0)),
            account.get("due_date"),
            account.get("status", "pending"),
            account.get("installment_number", 0),
            account.get("total_installments", 1),
            account.get("parent_id")
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

        # Determina novo status
        new_status = "paid" if new_paid >= total_amount else "partial"

        # Atualiza conta
        updated = await conn.fetchrow("""
            UPDATE accounts_receivable SET
                paid_amount = $2, status = $3, payment_date = $4, updated_at = $5
            WHERE id = $1
            RETURNING *
        """, account_id, new_paid, new_status, payment.get("payment_date"), datetime.utcnow())

        return row_to_dict(updated)
    finally:
        await conn.close()


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
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria multiplas contas a receber (parcelamento)"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        accounts = data.get("accounts", [])
        created = []
        for acc in accounts:
            row = await conn.fetchrow("""
                INSERT INTO accounts_receivable (
                    customer_id, description, amount, paid_amount, due_date, status,
                    installment_number, total_installments, parent_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
            """,
                acc.get("customer_id"),
                acc.get("description", ""),
                float(acc.get("amount", 0)),
                float(acc.get("paid_amount", 0)),
                acc.get("due_date"),
                acc.get("status", "pending"),
                acc.get("installment_number", 0),
                acc.get("total_installments", 1),
                acc.get("parent_id")
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
            rows = await conn.fetch("""
                SELECT ap.*,
                    COALESCE(s.company_name, s.trade_name, s.name) as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE ap.status = $3
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip, status)
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

    try:
        row = await conn.fetchrow("""
            INSERT INTO accounts_payable (
                supplier_id, description, amount, paid_amount, due_date, status,
                installment_number, total_installments, parent_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
        """,
            account.get("supplier_id"),
            account.get("description", ""),
            float(account.get("amount", 0)),
            float(account.get("paid_amount", 0)),
            account.get("due_date"),
            account.get("status", "pending"),
            account.get("installment_number", 0),
            account.get("total_installments", 1),
            account.get("parent_id")
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
        row = await conn.fetchrow("""
            UPDATE accounts_payable SET
                supplier_id = $2, description = $3, amount = $4, paid_amount = $5,
                due_date = $6, status = $7, updated_at = $8
            WHERE id = $1
            RETURNING *
        """,
            account_id,
            account.get("supplier_id"),
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
        current_paid = float(row["paid_amount"] or 0)
        total_amount = float(row["amount"])
        new_paid = current_paid + payment_amount

        # Determina novo status
        new_status = "paid" if new_paid >= total_amount else "partial"

        # Atualiza conta
        updated = await conn.fetchrow("""
            UPDATE accounts_payable SET
                paid_amount = $2, status = $3, payment_date = $4, updated_at = $5
            WHERE id = $1
            RETURNING *
        """, account_id, new_paid, new_status, payment.get("payment_date"), datetime.utcnow())

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
        row = await conn.fetchrow("SELECT * FROM company LIMIT 1")
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
        row = await conn.fetchrow("SELECT * FROM company LIMIT 1")
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
