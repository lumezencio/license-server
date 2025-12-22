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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import select

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
    """
    # Verifica se agendamento esta habilitado
    if not schedule.get("enabled"):
        logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Agendamento desabilitado")
        return False

    now = datetime.now()
    time_str = schedule.get("time", "02:00")
    time_parts = time_str.split(":")
    scheduled_hour = int(time_parts[0])
    scheduled_minute = int(time_parts[1]) if len(time_parts) > 1 else 0

    current_hour = now.hour
    current_minute = now.minute

    logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Hora atual={current_hour}:{current_minute:02d}, "
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
        current_weekday = now.weekday()
        logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Dia da semana atual={current_weekday}, "
                    f"Configurado={day_of_week}")
        if current_weekday != day_of_week:
            return False

    elif frequency == "monthly":
        day_of_month = schedule.get("dayOfMonth", 1)
        current_day = now.day
        logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Dia do mes atual={current_day}, "
                    f"Configurado={day_of_month}")
        if current_day != day_of_month:
            return False

    # Verifica se ja executou hoje
    last_run = schedule.get("last_run")
    if last_run:
        try:
            last_run_dt = datetime.fromisoformat(last_run)
            last_run_date = last_run_dt.date()
            if last_run_date == now.date():
                logger.debug(f"[BACKUP-SCHEDULER] {tenant_code}: Ja executou hoje ({last_run})")
                return False
        except Exception as e:
            logger.warning(f"[BACKUP-SCHEDULER] {tenant_code}: Erro ao parsear last_run: {e}")

    logger.info(f"[BACKUP-SCHEDULER] {tenant_code}: Condicoes atendidas! Backup sera executado.")
    return True


async def execute_backup(tenant: Tenant) -> bool:
    """Executa backup do tenant usando pg_dump"""
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

        # Executa pg_dump
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

        logger.info(f"[BACKUP-SCHEDULER] Iniciando backup automatico do tenant {tenant.tenant_code}")
        logger.debug(f"[BACKUP-SCHEDULER] Comando: pg_dump -h {db_host} -p {db_port} -U {db_user} -d {db_name}")

        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            logger.error(f"[BACKUP-SCHEDULER] Erro no pg_dump para {tenant.tenant_code}: {result.stderr}")
            return False

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
            logger.info(f"[BACKUP-SCHEDULER] Executando backup agendado de {tenant.tenant_code}")

            success = await execute_backup(tenant)

            if success:
                # Atualiza last_run
                schedule["last_run"] = datetime.now().isoformat()
                save_schedule(tenant.tenant_code, schedule)

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
