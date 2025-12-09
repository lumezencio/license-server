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
        if search:
            rows = await conn.fetch("""
                SELECT * FROM customers
                WHERE name ILIKE $1 OR document ILIKE $1 OR email ILIKE $1
                ORDER BY name
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            rows = await conn.fetch("""
                SELECT * FROM customers ORDER BY name LIMIT $1 OFFSET $2
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
        row = await conn.fetchrow(
            "SELECT * FROM customers WHERE id = $1",
            customer_id
        )
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
        if search:
            rows = await conn.fetch("""
                SELECT * FROM products
                WHERE name ILIKE $1 OR code ILIKE $1 OR barcode ILIKE $1
                ORDER BY name
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            rows = await conn.fetch("""
                SELECT * FROM products ORDER BY name LIMIT $1 OFFSET $2
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
        if search:
            rows = await conn.fetch("""
                SELECT * FROM suppliers
                WHERE name ILIKE $1 OR document ILIKE $1 OR email ILIKE $1
                ORDER BY name
                LIMIT $2 OFFSET $3
            """, f"%{search}%", limit, skip)
        else:
            rows = await conn.fetch("""
                SELECT * FROM suppliers ORDER BY name LIMIT $1 OFFSET $2
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
        employees_count = await conn.fetchval("SELECT COUNT(*) FROM employees")

        # Vendas do mes
        sales_month = await conn.fetchval("""
            SELECT COALESCE(SUM(total), 0) FROM sales
            WHERE DATE_TRUNC('month', sale_date) = DATE_TRUNC('month', CURRENT_DATE)
        """)

        # Contas a receber pendentes
        receivables = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - paid_amount), 0) FROM accounts_receivable
            WHERE status = 'pending'
        """)

        # Contas a pagar pendentes
        payables = await conn.fetchval("""
            SELECT COALESCE(SUM(amount - paid_amount), 0) FROM accounts_payable
            WHERE status = 'pending'
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
        rows = await conn.fetch("""
            SELECT s.*, c.name as customer_name
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
        rows = await conn.fetch("""
            SELECT p.*, s.name as supplier_name
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
async def list_accounts_receivable(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista contas a receber do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        if status:
            rows = await conn.fetch("""
                SELECT ar.*, c.name as customer_name
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                WHERE ar.status = $3
                ORDER BY ar.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip, status)
        else:
            rows = await conn.fetch("""
                SELECT ar.*, c.name as customer_name
                FROM accounts_receivable ar
                LEFT JOIN customers c ON ar.customer_id = c.id
                ORDER BY ar.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip)

        return [row_to_dict(row) for row in rows]
    finally:
        await conn.close()


# === ENDPOINTS - ACCOUNTS PAYABLE ===

@router.get("/accounts-payable")
async def list_accounts_payable(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista contas a pagar do tenant"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        if status:
            rows = await conn.fetch("""
                SELECT ap.*, s.name as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                WHERE ap.status = $3
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip, status)
        else:
            rows = await conn.fetch("""
                SELECT ap.*, s.name as supplier_name
                FROM accounts_payable ap
                LEFT JOIN suppliers s ON ap.supplier_id = s.id
                ORDER BY ap.due_date
                LIMIT $1 OFFSET $2
            """, limit, skip)

        return [row_to_dict(row) for row in rows]
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
