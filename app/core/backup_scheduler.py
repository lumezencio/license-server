"""
License Server - Backup Scheduler
Servico de agendamento automatico de backups para tenants

Este modulo roda em background e:
1. Verifica periodicamente os agendamentos de backup de cada tenant
2. Executa backups automaticos nos horarios configurados
3. Limpa backups antigos conforme politica de retencao
"""

import asyncio
import json
import subprocess
import os
import logging
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import asyncpg
from sqlalchemy import select

# Fuso horario padrao do Brasil (UTC-3)
BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")

from app.database import AsyncSessionLocal
from app.models import Tenant, TenantStatus
from app.core import settings

logger = logging.getLogger(__name__)

# Diretorio base para backups (mesmo padrao do tenant_gateway.py)
BACKUP_DIR = Path("/app/backups") if os.path.exists("/app") else Path("./backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


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
                data = json.load(f)
                logger.debug(f"[BACKUP-SCHEDULER] Schedule carregado para {tenant_code}: {data}")
                return data
        except Exception as e:
            logger.error(f"[BACKUP-SCHEDULER] Erro ao carregar schedule de {tenant_code}: {e}")
    return {
        "enabled": False,
        "frequency": "daily",
        "time": "02:00",
        "dayOfWeek": 1,
        "dayOfMonth": 1,
        "retentionDays": 30,
        "last_run": None
    }


def save_schedule(tenant_code: str, schedule: dict):
    """Salva configuracao de agendamento"""
    schedule_file = get_schedule_file(tenant_code)
    with open(schedule_file, 'w') as f:
        json.dump(schedule, f, indent=2)
    logger.info(f"[BACKUP-SCHEDULER] Schedule salvo para {tenant_code}")


def should_run_backup(schedule: dict, tenant_code: str = "unknown") -> bool:
    """
    Verifica se o backup deve ser executado agora.
    Retorna True se todas as condicoes forem atendidas.
    USA O FUSO HORARIO DO BRASIL (America/Sao_Paulo) para comparar com o horario agendado.
    """
    # Verifica se agendamento esta habilitado
    if not schedule.get("enabled"):
        logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Agendamento desabilitado")
        return False

    # Usa o fuso horario do Brasil para verificar o horario
    # O tenant agenda no horario local dele (Brasil), entao precisamos comparar com horario BR
    now_brazil = datetime.now(BRAZIL_TZ)
    time_str = schedule.get("time", "02:00")
    time_parts = time_str.split(":")
    scheduled_hour = int(time_parts[0])
    scheduled_minute = int(time_parts[1]) if len(time_parts) > 1 else 0

    current_hour = now_brazil.hour
    current_minute = now_brazil.minute

    logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Hora Brasil={current_hour}:{current_minute:02d}, "
                f"Agendado={scheduled_hour}:{scheduled_minute:02d}")

    # Verifica se estamos no horario certo (com tolerancia de 2 minutos)
    if current_hour != scheduled_hour:
        return False

    minute_diff = abs(current_minute - scheduled_minute)
    if minute_diff > 2:  # Tolerancia de 2 minutos
        return False

    # Verifica frequencia
    frequency = schedule.get("frequency", "daily")
    logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Frequencia={frequency}")

    if frequency == "weekly":
        day_of_week = schedule.get("dayOfWeek", 1)
        current_weekday = now_brazil.weekday()
        logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Dia da semana atual={current_weekday}, "
                    f"Configurado={day_of_week}")
        if current_weekday != day_of_week:
            return False

    elif frequency == "monthly":
        day_of_month = schedule.get("dayOfMonth", 1)
        current_day = now_brazil.day
        logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Dia do mes atual={current_day}, "
                    f"Configurado={day_of_month}")
        if current_day != day_of_month:
            return False

    # Verifica se ja executou hoje (usando data do Brasil)
    last_run = schedule.get("last_run")
    if last_run:
        try:
            last_run_dt = datetime.fromisoformat(last_run)
            # Converte para fuso horario do Brasil para comparar datas
            if last_run_dt.tzinfo is None:
                last_run_dt = last_run_dt.replace(tzinfo=BRAZIL_TZ)
            last_run_date = last_run_dt.date()
            if last_run_date == now_brazil.date():
                logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Ja executou hoje ({last_run})")
                return False
        except Exception as e:
            logger.warning(f"[BACKUP-SCHEDULER] {tenant_code}: Erro ao parsear last_run: {e}")

    logger.info(f"[BACKUP-SCHEDULER] {tenant_code}: Condicoes atendidas! Backup sera executado.")
    return True


async def execute_backup_with_asyncpg(tenant: Tenant, backup_path: Path, db_host: str, db_port: int, db_user: str, db_pass: str, db_name: str) -> bool:
    """Executa backup usando asyncpg (fallback quando pg_dump nao esta disponivel)"""
    conn = None
    try:
        conn = await asyncpg.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_pass,
            database=db_name,
            timeout=30
        )

        sql_lines = []
        now_brazil = datetime.now(BRAZIL_TZ)
        sql_lines.append(f"-- Backup do banco {db_name}")
        sql_lines.append(f"-- Gerado em {now_brazil.strftime('%Y-%m-%d %H:%M:%S')} (Horario de Brasilia)")
        sql_lines.append(f"-- Tenant: {tenant.tenant_code}")
        sql_lines.append(f"-- Metodo: asyncpg (backup agendado)")
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

        logger.info(f"[BACKUP-SCHEDULER] Backup criado via asyncpg ({len(sql_lines)} linhas)")
        return True

    except Exception as e:
        logger.error(f"[BACKUP-SCHEDULER] Erro no backup asyncpg: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            await conn.close()


async def execute_backup(tenant: Tenant) -> bool:
    """Executa backup do tenant usando pg_dump ou asyncpg como fallback"""
    try:
        tenant_backup_dir = get_tenant_backup_dir(tenant.tenant_code)

        # Nome do arquivo com timestamp no fuso horario do Brasil
        # Assim o arquivo reflete o horario local do usuario
        now_brazil = datetime.now(BRAZIL_TZ)
        timestamp = now_brazil.strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{tenant.tenant_code}_{timestamp}.sql"
        backup_path = tenant_backup_dir / backup_filename

        # Configuracoes do banco
        db_host = tenant.database_host or settings.POSTGRES_HOST
        db_port = tenant.database_port or settings.POSTGRES_PORT
        db_user = tenant.database_user
        db_pass = tenant.database_password
        db_name = tenant.database_name

        logger.info(f"[BACKUP-SCHEDULER] Iniciando backup automatico do tenant {tenant.tenant_code}")
        logger.debug(f"[BACKUP-SCHEDULER] Conexao: host={db_host}, port={db_port}, db={db_name}")

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
            logger.info(f"[BACKUP-SCHEDULER] Backup criado via pg_dump")
        except Exception as pg_err:
            logger.warning(f"[BACKUP-SCHEDULER] pg_dump nao disponivel ({pg_err}), usando asyncpg...")

            # Fallback: usa asyncpg para gerar backup SQL
            success = await execute_backup_with_asyncpg(
                tenant, backup_path, db_host, db_port, db_user, db_pass, db_name
            )
            if not success:
                return False

        # Verifica se arquivo foi criado
        if not backup_path.exists():
            logger.error(f"[BACKUP-SCHEDULER] Backup nao foi criado para {tenant.tenant_code}")
            return False

        file_size = backup_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        logger.info(f"[BACKUP-SCHEDULER] Backup automatico criado: {backup_filename} ({size_mb:.2f} MB)")

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"[BACKUP-SCHEDULER] Timeout ao criar backup de {tenant.tenant_code}")
        return False
    except Exception as e:
        logger.error(f"[BACKUP-SCHEDULER] Erro ao criar backup de {tenant.tenant_code}: {e}")
        import traceback
        traceback.print_exc()
        return False


def cleanup_old_backups(tenant_code: str, retention_days: int):
    """Remove backups antigos conforme politica de retencao"""
    try:
        tenant_backup_dir = get_tenant_backup_dir(tenant_code)
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        removed_count = 0
        for backup_file in tenant_backup_dir.glob("*.sql"):
            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if file_mtime < cutoff_date:
                backup_file.unlink()
                removed_count += 1
                logger.info(f"[BACKUP-SCHEDULER] Backup antigo removido: {backup_file.name}")

        if removed_count > 0:
            logger.info(f"[BACKUP-SCHEDULER] {removed_count} backups antigos removidos de {tenant_code}")

    except Exception as e:
        logger.error(f"[BACKUP-SCHEDULER] Erro ao limpar backups antigos de {tenant_code}: {e}")


async def process_tenant_backup(tenant: Tenant):
    """Processa backup de um tenant especifico"""
    try:
        schedule = load_schedule(tenant.tenant_code)

        if should_run_backup(schedule, tenant.tenant_code):
            # Marca imediatamente como executado para evitar duplicatas
            # (quando ha multiplos workers rodando)
            now_brazil = datetime.now(BRAZIL_TZ)
            schedule["last_run"] = now_brazil.isoformat()
            save_schedule(tenant.tenant_code, schedule)

            logger.info(f"[BACKUP-SCHEDULER] Executando backup agendado de {tenant.tenant_code}")

            success = await execute_backup(tenant)

            if success:
                # Limpa backups antigos
                retention_days = schedule.get("retentionDays", 30)
                cleanup_old_backups(tenant.tenant_code, retention_days)

                logger.info(f"[BACKUP-SCHEDULER] Backup agendado concluido para {tenant.tenant_code}")
            else:
                logger.error(f"[BACKUP-SCHEDULER] Falha no backup agendado de {tenant.tenant_code}")

    except Exception as e:
        logger.error(f"[BACKUP-SCHEDULER] Erro ao processar backup de {tenant.tenant_code}: {e}")
        import traceback
        traceback.print_exc()


async def run_scheduler():
    """
    Loop principal do scheduler de backups.
    Executa a cada 60 segundos verificando se algum backup precisa ser executado.
    """
    logger.info("[BACKUP-SCHEDULER] ========================================")
    logger.info("[BACKUP-SCHEDULER] Servico de agendamento de backups INICIADO")
    logger.info(f"[BACKUP-SCHEDULER] Diretorio de backups: {BACKUP_DIR}")
    logger.info("[BACKUP-SCHEDULER] ========================================")

    check_count = 0

    while True:
        try:
            check_count += 1
            now = datetime.now()

            # Log periodico a cada 10 minutos
            if check_count % 10 == 1:
                logger.info(f"[BACKUP-SCHEDULER] Verificacao #{check_count} - {now.strftime('%Y-%m-%d %H:%M:%S')}")

            # Busca todos os tenants ativos
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Tenant).where(
                        Tenant.status.in_([TenantStatus.ACTIVE.value, TenantStatus.TRIAL.value])
                    )
                )
                tenants = result.scalars().all()

                if check_count % 10 == 1:
                    logger.debug(f"[BACKUP-SCHEDULER] {len(tenants)} tenants ativos encontrados")

                for tenant in tenants:
                    await process_tenant_backup(tenant)

        except Exception as e:
            logger.error(f"[BACKUP-SCHEDULER] Erro no loop do scheduler: {e}")
            import traceback
            traceback.print_exc()

        # Aguarda 60 segundos antes de verificar novamente
        await asyncio.sleep(60)


# Para executar standalone (debug)
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("Iniciando backup scheduler em modo standalone...")
    asyncio.run(run_scheduler())
