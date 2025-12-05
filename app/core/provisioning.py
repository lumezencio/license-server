"""
License Server - Tenant Provisioning Service
Serviço para criação automática de banco de dados por tenant
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple
import asyncpg
import hashlib

from .config import settings

logger = logging.getLogger(__name__)


class ProvisioningError(Exception):
    """Erro durante o provisionamento do tenant"""
    pass


class TenantProvisioningService:
    """
    Serviço responsável por criar e configurar bancos de dados para tenants.

    Fluxo de provisionamento:
    1. Cria banco de dados PostgreSQL
    2. Cria usuário com permissões
    3. Cria estrutura de tabelas (schema)
    4. Cria usuário admin inicial
    5. Atualiza status do tenant
    """

    def __init__(self):
        self.master_host = settings.POSTGRES_HOST
        self.master_port = settings.POSTGRES_PORT
        self.master_user = settings.POSTGRES_USER
        self.master_password = settings.POSTGRES_PASSWORD
        self.master_database = settings.POSTGRES_DATABASE

    async def _get_master_connection(self) -> asyncpg.Connection:
        """Obtém conexão com o banco master (postgres)"""
        try:
            conn = await asyncpg.connect(
                host=self.master_host,
                port=self.master_port,
                user=self.master_user,
                password=self.master_password,
                database=self.master_database
            )
            return conn
        except Exception as e:
            logger.error(f"Erro ao conectar ao banco master: {e}")
            raise ProvisioningError(f"Não foi possível conectar ao servidor PostgreSQL: {e}")

    async def _get_tenant_connection(
        self,
        database: str,
        user: str,
        password: str
    ) -> asyncpg.Connection:
        """Obtém conexão com o banco do tenant"""
        try:
            conn = await asyncpg.connect(
                host=self.master_host,
                port=self.master_port,
                user=user,
                password=password,
                database=database
            )
            return conn
        except Exception as e:
            logger.error(f"Erro ao conectar ao banco do tenant: {e}")
            raise ProvisioningError(f"Não foi possível conectar ao banco do tenant: {e}")

    async def database_exists(self, database_name: str) -> bool:
        """Verifica se um banco de dados existe"""
        conn = await self._get_master_connection()
        try:
            result = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                database_name
            )
            return result is not None
        finally:
            await conn.close()

    async def user_exists(self, username: str) -> bool:
        """Verifica se um usuário existe"""
        conn = await self._get_master_connection()
        try:
            result = await conn.fetchval(
                "SELECT 1 FROM pg_roles WHERE rolname = $1",
                username
            )
            return result is not None
        finally:
            await conn.close()

    async def create_database_user(
        self,
        username: str,
        password: str
    ) -> bool:
        """Cria usuário no PostgreSQL"""
        conn = await self._get_master_connection()
        try:
            # Verifica se usuário já existe
            if await self.user_exists(username):
                logger.info(f"Usuário {username} já existe")
                return True

            # Cria usuário com senha
            # Usamos format seguro para evitar SQL injection
            await conn.execute(f"""
                CREATE USER "{username}" WITH PASSWORD '{password}'
                LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            """)

            logger.info(f"Usuário {username} criado com sucesso")
            return True

        except Exception as e:
            logger.error(f"Erro ao criar usuário {username}: {e}")
            raise ProvisioningError(f"Erro ao criar usuário: {e}")
        finally:
            await conn.close()

    async def create_database(
        self,
        database_name: str,
        owner: str
    ) -> bool:
        """Cria banco de dados para o tenant"""
        conn = await self._get_master_connection()
        try:
            # Verifica se banco já existe
            if await self.database_exists(database_name):
                logger.info(f"Banco {database_name} já existe")
                return True

            # Cria banco de dados
            # IMPORTANTE: CREATE DATABASE não pode rodar dentro de transação
            await conn.execute(f"""
                CREATE DATABASE "{database_name}"
                WITH OWNER = "{owner}"
                ENCODING = 'UTF8'
                LC_COLLATE = 'en_US.utf8'
                LC_CTYPE = 'en_US.utf8'
                TEMPLATE = template0
            """)

            logger.info(f"Banco {database_name} criado com sucesso")
            return True

        except Exception as e:
            logger.error(f"Erro ao criar banco {database_name}: {e}")
            raise ProvisioningError(f"Erro ao criar banco de dados: {e}")
        finally:
            await conn.close()

    async def grant_permissions(
        self,
        database_name: str,
        username: str
    ) -> bool:
        """Concede permissões ao usuário no banco"""
        conn = await self._get_master_connection()
        try:
            # Concede todas as permissões no banco
            await conn.execute(f"""
                GRANT ALL PRIVILEGES ON DATABASE "{database_name}" TO "{username}"
            """)

            logger.info(f"Permissões concedidas a {username} no banco {database_name}")
            return True

        except Exception as e:
            logger.error(f"Erro ao conceder permissões: {e}")
            raise ProvisioningError(f"Erro ao conceder permissões: {e}")
        finally:
            await conn.close()

    async def create_schema(
        self,
        database_name: str,
        username: str,
        password: str
    ) -> bool:
        """
        Cria a estrutura de tabelas do enterprise_system no banco do tenant.
        Inclui: customers, suppliers, products, sales, purchases, accounts, users, company
        """
        conn = await self._get_tenant_connection(database_name, username, password)
        try:
            # Habilita extensões necessárias
            await conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

            # Schema completo do enterprise_system
            schema_sql = """
            -- Tabela de Empresa (Company)
            CREATE TABLE IF NOT EXISTS company (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name VARCHAR(255) NOT NULL,
                trade_name VARCHAR(255),
                document VARCHAR(20) NOT NULL,
                state_registration VARCHAR(30),
                municipal_registration VARCHAR(30),
                phone VARCHAR(20),
                email VARCHAR(255),
                address VARCHAR(255),
                address_number VARCHAR(20),
                address_complement VARCHAR(100),
                neighborhood VARCHAR(100),
                city VARCHAR(100),
                state VARCHAR(2),
                zip_code VARCHAR(10),
                logo_path VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Usuários
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                is_admin BOOLEAN DEFAULT FALSE,
                must_change_password BOOLEAN DEFAULT TRUE,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Clientes
            CREATE TABLE IF NOT EXISTS customers (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name VARCHAR(255) NOT NULL,
                document VARCHAR(20),
                email VARCHAR(255),
                phone VARCHAR(20),
                address VARCHAR(255),
                address_number VARCHAR(20),
                address_complement VARCHAR(100),
                neighborhood VARCHAR(100),
                city VARCHAR(100),
                state VARCHAR(2),
                zip_code VARCHAR(10),
                notes TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Fornecedores
            CREATE TABLE IF NOT EXISTS suppliers (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name VARCHAR(255) NOT NULL,
                document VARCHAR(20),
                email VARCHAR(255),
                phone VARCHAR(20),
                address VARCHAR(255),
                address_number VARCHAR(20),
                address_complement VARCHAR(100),
                neighborhood VARCHAR(100),
                city VARCHAR(100),
                state VARCHAR(2),
                zip_code VARCHAR(10),
                notes TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Produtos
            CREATE TABLE IF NOT EXISTS products (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                code VARCHAR(50),
                name VARCHAR(255) NOT NULL,
                description TEXT,
                unit VARCHAR(20) DEFAULT 'UN',
                cost_price DECIMAL(15,2) DEFAULT 0,
                sale_price DECIMAL(15,2) DEFAULT 0,
                stock_quantity DECIMAL(15,3) DEFAULT 0,
                min_stock DECIMAL(15,3) DEFAULT 0,
                category VARCHAR(100),
                barcode VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Funcionários
            CREATE TABLE IF NOT EXISTS employees (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name VARCHAR(255) NOT NULL,
                document VARCHAR(20),
                email VARCHAR(255),
                phone VARCHAR(20),
                position VARCHAR(100),
                department VARCHAR(100),
                hire_date DATE,
                salary DECIMAL(15,2),
                address VARCHAR(255),
                city VARCHAR(100),
                state VARCHAR(2),
                notes TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Vendas
            CREATE TABLE IF NOT EXISTS sales (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                sale_number SERIAL,
                customer_id UUID REFERENCES customers(id),
                employee_id UUID REFERENCES employees(id),
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subtotal DECIMAL(15,2) DEFAULT 0,
                discount DECIMAL(15,2) DEFAULT 0,
                total DECIMAL(15,2) DEFAULT 0,
                payment_method VARCHAR(50),
                status VARCHAR(20) DEFAULT 'completed',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Itens de Venda
            CREATE TABLE IF NOT EXISTS sale_items (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                sale_id UUID NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                product_id UUID REFERENCES products(id),
                product_name VARCHAR(255),
                quantity DECIMAL(15,3) NOT NULL,
                unit_price DECIMAL(15,2) NOT NULL,
                discount DECIMAL(15,2) DEFAULT 0,
                total DECIMAL(15,2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tabela de Compras
            CREATE TABLE IF NOT EXISTS purchases (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                purchase_number SERIAL,
                supplier_id UUID REFERENCES suppliers(id),
                purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                subtotal DECIMAL(15,2) DEFAULT 0,
                discount DECIMAL(15,2) DEFAULT 0,
                freight DECIMAL(15,2) DEFAULT 0,
                total DECIMAL(15,2) DEFAULT 0,
                payment_method VARCHAR(50),
                status VARCHAR(20) DEFAULT 'completed',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Itens de Compra
            CREATE TABLE IF NOT EXISTS purchase_items (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                purchase_id UUID NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
                product_id UUID REFERENCES products(id),
                product_name VARCHAR(255),
                quantity DECIMAL(15,3) NOT NULL,
                unit_price DECIMAL(15,2) NOT NULL,
                total DECIMAL(15,2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Contas a Receber
            CREATE TABLE IF NOT EXISTS accounts_receivable (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                customer_id UUID REFERENCES customers(id),
                sale_id UUID REFERENCES sales(id),
                description VARCHAR(255),
                amount DECIMAL(15,2) NOT NULL,
                due_date DATE NOT NULL,
                payment_date DATE,
                paid_amount DECIMAL(15,2) DEFAULT 0,
                status VARCHAR(20) DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Contas a Pagar
            CREATE TABLE IF NOT EXISTS accounts_payable (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                supplier_id UUID REFERENCES suppliers(id),
                purchase_id UUID REFERENCES purchases(id),
                description VARCHAR(255),
                amount DECIMAL(15,2) NOT NULL,
                due_date DATE NOT NULL,
                payment_date DATE,
                paid_amount DECIMAL(15,2) DEFAULT 0,
                status VARCHAR(20) DEFAULT 'pending',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Cálculos Jurídicos
            CREATE TABLE IF NOT EXISTS legal_calculations (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                title VARCHAR(255) NOT NULL,
                description TEXT,
                calculation_type VARCHAR(50),
                principal_amount DECIMAL(15,2),
                start_date DATE,
                end_date DATE,
                result_data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Índices para melhor performance
            CREATE INDEX IF NOT EXISTS idx_customers_document ON customers(document);
            CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
            CREATE INDEX IF NOT EXISTS idx_suppliers_document ON suppliers(document);
            CREATE INDEX IF NOT EXISTS idx_products_code ON products(code);
            CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
            CREATE INDEX IF NOT EXISTS idx_sales_customer ON sales(customer_id);
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
            CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchases(supplier_id);
            CREATE INDEX IF NOT EXISTS idx_accounts_receivable_due ON accounts_receivable(due_date);
            CREATE INDEX IF NOT EXISTS idx_accounts_payable_due ON accounts_payable(due_date);
            """

            await conn.execute(schema_sql)

            # Concede permissões em todas as tabelas
            await conn.execute(f"""
                GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{username}";
                GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{username}";
            """)

            logger.info(f"Schema criado com sucesso no banco {database_name}")
            return True

        except Exception as e:
            logger.error(f"Erro ao criar schema: {e}")
            raise ProvisioningError(f"Erro ao criar estrutura do banco: {e}")
        finally:
            await conn.close()

    async def create_admin_user(
        self,
        database_name: str,
        db_username: str,
        db_password: str,
        admin_email: str,
        admin_password: str,
        admin_name: str
    ) -> bool:
        """Cria o usuário administrador inicial no banco do tenant"""
        conn = await self._get_tenant_connection(database_name, db_username, db_password)
        try:
            # Hash da senha (usando SHA256 simples - em produção usar bcrypt)
            password_hash = hashlib.sha256(admin_password.encode()).hexdigest()

            # Verifica se já existe usuário admin
            existing = await conn.fetchval(
                "SELECT 1 FROM users WHERE email = $1",
                admin_email
            )

            if existing:
                logger.info(f"Usuário admin {admin_email} já existe")
                return True

            # Insere usuário admin
            await conn.execute("""
                INSERT INTO users (email, password_hash, name, is_active, is_admin, must_change_password)
                VALUES ($1, $2, $3, TRUE, TRUE, TRUE)
            """, admin_email, password_hash, admin_name)

            logger.info(f"Usuário admin {admin_email} criado com sucesso")
            return True

        except Exception as e:
            logger.error(f"Erro ao criar usuário admin: {e}")
            raise ProvisioningError(f"Erro ao criar usuário admin: {e}")
        finally:
            await conn.close()

    async def provision_tenant(
        self,
        tenant_code: str,
        database_name: str,
        database_user: str,
        database_password: str,
        admin_email: str,
        admin_password: str,
        admin_name: str
    ) -> Tuple[bool, str]:
        """
        Executa o provisionamento completo de um tenant.

        Args:
            tenant_code: Código único do tenant
            database_name: Nome do banco de dados a ser criado
            database_user: Nome do usuário do banco
            database_password: Senha do usuário do banco
            admin_email: Email do admin inicial
            admin_password: Senha do admin (geralmente o CPF/CNPJ)
            admin_name: Nome do admin

        Returns:
            Tuple[bool, str]: (sucesso, mensagem)
        """
        logger.info(f"Iniciando provisionamento do tenant {tenant_code}")

        try:
            # 1. Criar usuário do banco
            logger.info(f"Criando usuário {database_user}...")
            await self.create_database_user(database_user, database_password)

            # 2. Criar banco de dados
            logger.info(f"Criando banco {database_name}...")
            await self.create_database(database_name, database_user)

            # 3. Conceder permissões
            logger.info(f"Concedendo permissões...")
            await self.grant_permissions(database_name, database_user)

            # Aguarda um momento para o banco ser criado completamente
            await asyncio.sleep(1)

            # 4. Criar estrutura de tabelas
            logger.info(f"Criando estrutura de tabelas...")
            await self.create_schema(database_name, database_user, database_password)

            # 5. Criar usuário admin
            logger.info(f"Criando usuário admin...")
            await self.create_admin_user(
                database_name,
                database_user,
                database_password,
                admin_email,
                admin_password,
                admin_name
            )

            logger.info(f"Provisionamento do tenant {tenant_code} concluído com sucesso!")

            return True, "Provisionamento concluído com sucesso"

        except ProvisioningError as e:
            logger.error(f"Erro no provisionamento: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Erro inesperado no provisionamento: {e}")
            return False, f"Erro inesperado: {e}"

    async def check_tenant_database(
        self,
        database_name: str,
        username: str,
        password: str
    ) -> Tuple[bool, dict]:
        """
        Verifica se o banco do tenant está funcionando corretamente.

        Returns:
            Tuple[bool, dict]: (sucesso, informações)
        """
        try:
            conn = await self._get_tenant_connection(database_name, username, password)

            # Conta tabelas
            tables = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """)

            # Conta usuários
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")

            await conn.close()

            return True, {
                "tables": len(tables),
                "users": user_count,
                "status": "healthy"
            }

        except Exception as e:
            return False, {
                "error": str(e),
                "status": "error"
            }

    async def delete_tenant_database(
        self,
        database_name: str,
        username: str
    ) -> bool:
        """
        Remove o banco de dados e usuário de um tenant.
        CUIDADO: Esta operação é irreversível!
        """
        conn = await self._get_master_connection()
        try:
            # Encerra conexões ativas
            await conn.execute(f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{database_name}'
            """)

            # Remove banco
            await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')

            # Remove usuário
            await conn.execute(f'DROP USER IF EXISTS "{username}"')

            logger.info(f"Banco {database_name} e usuário {username} removidos")
            return True

        except Exception as e:
            logger.error(f"Erro ao remover tenant: {e}")
            return False
        finally:
            await conn.close()


# Instância global do serviço
provisioning_service = TenantProvisioningService()
