"""
License Server - Diario Pessoal API Gateway
API Gateway Multi-Tenant para o sistema de Diario Pessoal

Este modulo fornece endpoints especificos para o produto DIARIO:
- CRUD de entradas do diario
- Gestao de tags
- Configuracoes do usuario
- Estatisticas e historico de humor
- Prompts de escrita
"""
from datetime import datetime, date, time
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
import uuid as uuid_lib
import json
from decimal import Decimal

from app.api.tenant_gateway import (
    get_tenant_from_token,
    get_tenant_connection,
    row_to_dict
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway/diario", tags=["Diario Pessoal Gateway"])


# === MODELOS PYDANTIC ===

class DiaryEntryCreate(BaseModel):
    """Modelo para criar entrada do diario"""
    title: Optional[str] = None
    content: str
    content_html: Optional[str] = None
    mood: Optional[str] = "neutral"
    mood_score: Optional[int] = Field(None, ge=1, le=10)
    energy_level: Optional[int] = Field(None, ge=1, le=10)
    weather: Optional[str] = None
    location: Optional[str] = None
    entry_date: Optional[str] = None  # ISO format YYYY-MM-DD
    entry_time: Optional[str] = None  # HH:MM:SS
    is_favorite: bool = False
    is_private: bool = True
    is_pinned: bool = False
    tags: Optional[List[str]] = None  # Lista de IDs de tags
    images: Optional[List[str]] = None
    attachments: Optional[List[dict]] = None
    metadata: Optional[dict] = None


class DiaryEntryUpdate(BaseModel):
    """Modelo para atualizar entrada do diario"""
    title: Optional[str] = None
    content: Optional[str] = None
    content_html: Optional[str] = None
    mood: Optional[str] = None
    mood_score: Optional[int] = Field(None, ge=1, le=10)
    energy_level: Optional[int] = Field(None, ge=1, le=10)
    weather: Optional[str] = None
    location: Optional[str] = None
    entry_date: Optional[str] = None
    entry_time: Optional[str] = None
    is_favorite: Optional[bool] = None
    is_private: Optional[bool] = None
    is_pinned: Optional[bool] = None
    tags: Optional[List[str]] = None
    images: Optional[List[str]] = None
    attachments: Optional[List[dict]] = None
    metadata: Optional[dict] = None


class TagCreate(BaseModel):
    """Modelo para criar tag"""
    name: str
    color: Optional[str] = "#3B82F6"
    icon: Optional[str] = None
    description: Optional[str] = None


class TagUpdate(BaseModel):
    """Modelo para atualizar tag"""
    name: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class UserSettingsUpdate(BaseModel):
    """Modelo para atualizar configuracoes do usuario"""
    theme: Optional[str] = None
    font_family: Optional[str] = None
    font_size: Optional[str] = None
    editor_mode: Optional[str] = None
    auto_save: Optional[bool] = None
    auto_save_interval: Optional[int] = None
    spell_check: Optional[bool] = None
    reminder_enabled: Optional[bool] = None
    reminder_time: Optional[str] = None
    reminder_days: Optional[List[str]] = None
    email_notifications: Optional[bool] = None
    default_privacy: Optional[str] = None
    require_pin: Optional[bool] = None
    show_word_count: Optional[bool] = None
    show_mood_stats: Optional[bool] = None
    show_streak: Optional[bool] = None
    default_export_format: Optional[str] = None
    include_images_export: Optional[bool] = None


class MoodRecordCreate(BaseModel):
    """Modelo para registrar humor"""
    mood: str
    mood_score: Optional[int] = Field(None, ge=1, le=10)
    energy_level: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None
    recorded_date: Optional[str] = None


# === FUNCOES AUXILIARES ===

def slugify(text: str) -> str:
    """Converte texto em slug"""
    import re
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


# === ENDPOINTS - DASHBOARD ===

@router.get("/dashboard")
async def get_dashboard(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna dados do dashboard do diario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Total de entradas
        total_entries = await conn.fetchval(
            "SELECT COUNT(*) FROM diary_entries WHERE user_id = $1 AND deleted_at IS NULL",
            user["id"]
        )

        # Entradas este mes
        entries_this_month = await conn.fetchval("""
            SELECT COUNT(*) FROM diary_entries
            WHERE user_id = $1 AND deleted_at IS NULL
            AND entry_date >= date_trunc('month', CURRENT_DATE)
        """, user["id"])

        # Streak atual
        streak_data = await conn.fetchrow(
            "SELECT current_streak, longest_streak, total_words FROM user_streaks WHERE user_id = $1",
            user["id"]
        )

        # Humor medio dos ultimos 7 dias
        avg_mood = await conn.fetchval("""
            SELECT AVG(mood_score) FROM diary_entries
            WHERE user_id = $1 AND deleted_at IS NULL
            AND mood_score IS NOT NULL
            AND entry_date >= CURRENT_DATE - INTERVAL '7 days'
        """, user["id"])

        # Ultimas 5 entradas
        recent_entries = await conn.fetch("""
            SELECT id, title, entry_date, mood, mood_score, word_count, is_favorite
            FROM diary_entries
            WHERE user_id = $1 AND deleted_at IS NULL
            ORDER BY entry_date DESC, created_at DESC
            LIMIT 5
        """, user["id"])

        # Tags mais usadas
        top_tags = await conn.fetch("""
            SELECT id, name, color, usage_count
            FROM tags
            WHERE user_id = $1 AND is_active = TRUE
            ORDER BY usage_count DESC
            LIMIT 5
        """, user["id"])

        # Prompt aleatorio do dia
        random_prompt = await conn.fetchrow("""
            SELECT id, prompt_text, category
            FROM writing_prompts
            WHERE (user_id = $1 OR is_system = TRUE) AND is_active = TRUE
            ORDER BY RANDOM()
            LIMIT 1
        """, user["id"])

        return {
            "stats": {
                "total_entries": total_entries or 0,
                "entries_this_month": entries_this_month or 0,
                "current_streak": streak_data["current_streak"] if streak_data else 0,
                "longest_streak": streak_data["longest_streak"] if streak_data else 0,
                "total_words": streak_data["total_words"] if streak_data else 0,
                "avg_mood_week": round(float(avg_mood), 1) if avg_mood else None
            },
            "recent_entries": [row_to_dict(r) for r in recent_entries],
            "top_tags": [row_to_dict(t) for t in top_tags],
            "daily_prompt": row_to_dict(random_prompt) if random_prompt else None
        }
    finally:
        await conn.close()


# === ENDPOINTS - ENTRIES (CRUD) ===

@router.get("/entries")
async def list_entries(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    mood: Optional[str] = None,
    tag_id: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista entradas do diario com filtros"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Construir query dinamicamente
        where_clauses = ["user_id = $1", "deleted_at IS NULL"]
        params = [user["id"]]
        param_idx = 2

        if search:
            where_clauses.append(f"(title ILIKE ${param_idx} OR content ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        if mood:
            where_clauses.append(f"mood = ${param_idx}")
            params.append(mood)
            param_idx += 1

        if is_favorite is not None:
            where_clauses.append(f"is_favorite = ${param_idx}")
            params.append(is_favorite)
            param_idx += 1

        if start_date:
            where_clauses.append(f"entry_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            where_clauses.append(f"entry_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)

        # Se filtrar por tag, fazer JOIN
        if tag_id:
            query = f"""
                SELECT DISTINCT e.* FROM diary_entries e
                JOIN entry_tags et ON e.id = et.entry_id
                WHERE {where_sql} AND et.tag_id = ${param_idx}
                ORDER BY e.entry_date DESC, e.created_at DESC
                LIMIT ${param_idx + 1} OFFSET ${param_idx + 2}
            """
            params.extend([tag_id, limit, skip])
        else:
            query = f"""
                SELECT * FROM diary_entries
                WHERE {where_sql}
                ORDER BY entry_date DESC, created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, skip])

        rows = await conn.fetch(query, *params)

        # Buscar tags de cada entrada
        entries = []
        for row in rows:
            entry = row_to_dict(row)
            tags = await conn.fetch("""
                SELECT t.id, t.name, t.color FROM tags t
                JOIN entry_tags et ON t.id = et.tag_id
                WHERE et.entry_id = $1
            """, row["id"])
            entry["tags"] = [row_to_dict(t) for t in tags]
            entries.append(entry)

        return entries
    finally:
        await conn.close()


@router.get("/entries/{entry_id}")
async def get_entry(
    entry_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca entrada por ID"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        row = await conn.fetchrow("""
            SELECT * FROM diary_entries
            WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL
        """, entry_id, user["id"])

        if not row:
            raise HTTPException(status_code=404, detail="Entrada nao encontrada")

        entry = row_to_dict(row)

        # Buscar tags
        tags = await conn.fetch("""
            SELECT t.id, t.name, t.color, t.icon FROM tags t
            JOIN entry_tags et ON t.id = et.tag_id
            WHERE et.entry_id = $1
        """, entry_id)
        entry["tags"] = [row_to_dict(t) for t in tags]

        return entry
    finally:
        await conn.close()


@router.post("/entries")
async def create_entry(
    entry: DiaryEntryCreate,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria nova entrada do diario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        entry_id = str(uuid_lib.uuid4())
        entry_date = entry.entry_date or date.today().isoformat()

        await conn.execute("""
            INSERT INTO diary_entries (
                id, user_id, title, content, content_html, mood, mood_score,
                energy_level, weather, location, entry_date, entry_time,
                is_favorite, is_private, is_pinned, images, attachments, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        """,
            entry_id, user["id"], entry.title, entry.content, entry.content_html,
            entry.mood, entry.mood_score, entry.energy_level, entry.weather,
            entry.location, entry_date, entry.entry_time,
            entry.is_favorite, entry.is_private, entry.is_pinned,
            json.dumps(entry.images) if entry.images else None,
            json.dumps(entry.attachments) if entry.attachments else None,
            json.dumps(entry.metadata) if entry.metadata else None
        )

        # Associar tags
        if entry.tags:
            for tag_id in entry.tags:
                try:
                    await conn.execute(
                        "INSERT INTO entry_tags (entry_id, tag_id) VALUES ($1, $2)",
                        entry_id, tag_id
                    )
                except Exception:
                    pass  # Tag pode nao existir

        # Atualizar streak
        await update_user_streak(conn, user["id"], entry_date)

        # Registrar no historico de humor se tiver mood_score
        if entry.mood_score:
            await conn.execute("""
                INSERT INTO mood_history (id, user_id, entry_id, mood, mood_score, energy_level, recorded_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, str(uuid_lib.uuid4()), user["id"], entry_id, entry.mood,
                entry.mood_score, entry.energy_level, entry_date)

        # Buscar entrada criada
        created = await conn.fetchrow("SELECT * FROM diary_entries WHERE id = $1", entry_id)
        return row_to_dict(created)

    finally:
        await conn.close()


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: str,
    entry: DiaryEntryUpdate,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza entrada do diario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Verificar se existe
        existing = await conn.fetchrow(
            "SELECT id FROM diary_entries WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL",
            entry_id, user["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Entrada nao encontrada")

        # Construir SET dinamicamente
        updates = []
        params = []
        param_idx = 1

        for field, value in entry.model_dump(exclude_unset=True).items():
            if field == "tags":
                continue  # Tratar separadamente
            if value is not None:
                if field in ["images", "attachments", "metadata"]:
                    value = json.dumps(value)
                updates.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1

        if updates:
            params.append(entry_id)
            await conn.execute(
                f"UPDATE diary_entries SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ${param_idx}",
                *params
            )

        # Atualizar tags se fornecidas
        if entry.tags is not None:
            # Remover tags antigas
            await conn.execute("DELETE FROM entry_tags WHERE entry_id = $1", entry_id)
            # Adicionar novas
            for tag_id in entry.tags:
                try:
                    await conn.execute(
                        "INSERT INTO entry_tags (entry_id, tag_id) VALUES ($1, $2)",
                        entry_id, tag_id
                    )
                except Exception:
                    pass

        # Buscar entrada atualizada
        updated = await conn.fetchrow("SELECT * FROM diary_entries WHERE id = $1", entry_id)
        return row_to_dict(updated)

    finally:
        await conn.close()


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: str,
    permanent: bool = False,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Exclui entrada do diario (soft delete por padrao)"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        existing = await conn.fetchrow(
            "SELECT id FROM diary_entries WHERE id = $1 AND user_id = $2",
            entry_id, user["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Entrada nao encontrada")

        if permanent:
            await conn.execute("DELETE FROM diary_entries WHERE id = $1", entry_id)
        else:
            await conn.execute(
                "UPDATE diary_entries SET deleted_at = CURRENT_TIMESTAMP WHERE id = $1",
                entry_id
            )

        return {"message": "Entrada excluida com sucesso"}

    finally:
        await conn.close()


@router.get("/entries/date/{entry_date}")
async def get_entries_by_date(
    entry_date: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca entradas de uma data especifica"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT * FROM diary_entries
            WHERE user_id = $1 AND entry_date = $2 AND deleted_at IS NULL
            ORDER BY entry_time ASC NULLS LAST, created_at ASC
        """, user["id"], entry_date)

        entries = []
        for row in rows:
            entry = row_to_dict(row)
            tags = await conn.fetch("""
                SELECT t.id, t.name, t.color FROM tags t
                JOIN entry_tags et ON t.id = et.tag_id
                WHERE et.entry_id = $1
            """, row["id"])
            entry["tags"] = [row_to_dict(t) for t in tags]
            entries.append(entry)

        return entries
    finally:
        await conn.close()


@router.get("/entries/month/{year}/{month}")
async def get_entries_by_month(
    year: int,
    month: int,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Busca entradas de um mes especifico (para calendario)"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT entry_date, COUNT(*) as count,
                   array_agg(mood) as moods,
                   AVG(mood_score) as avg_mood
            FROM diary_entries
            WHERE user_id = $1
            AND EXTRACT(YEAR FROM entry_date) = $2
            AND EXTRACT(MONTH FROM entry_date) = $3
            AND deleted_at IS NULL
            GROUP BY entry_date
            ORDER BY entry_date
        """, user["id"], year, month)

        return [row_to_dict(r) for r in rows]
    finally:
        await conn.close()


# === ENDPOINTS - TAGS ===

@router.get("/tags")
async def list_tags(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista tags do usuario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT * FROM tags
            WHERE user_id = $1 AND is_active = TRUE
            ORDER BY usage_count DESC, name ASC
        """, user["id"])

        return [row_to_dict(r) for r in rows]
    finally:
        await conn.close()


@router.post("/tags")
async def create_tag(
    tag: TagCreate,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Cria nova tag"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        tag_id = str(uuid_lib.uuid4())
        slug = slugify(tag.name)

        # Verificar se slug ja existe
        existing = await conn.fetchrow(
            "SELECT id FROM tags WHERE user_id = $1 AND slug = $2",
            user["id"], slug
        )
        if existing:
            raise HTTPException(status_code=400, detail="Tag com este nome ja existe")

        await conn.execute("""
            INSERT INTO tags (id, user_id, name, slug, color, icon, description)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, tag_id, user["id"], tag.name, slug, tag.color, tag.icon, tag.description)

        created = await conn.fetchrow("SELECT * FROM tags WHERE id = $1", tag_id)
        return row_to_dict(created)

    finally:
        await conn.close()


@router.put("/tags/{tag_id}")
async def update_tag(
    tag_id: str,
    tag: TagUpdate,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza tag"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        existing = await conn.fetchrow(
            "SELECT id FROM tags WHERE id = $1 AND user_id = $2",
            tag_id, user["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Tag nao encontrada")

        updates = []
        params = []
        param_idx = 1

        for field, value in tag.model_dump(exclude_unset=True).items():
            if value is not None:
                if field == "name":
                    # Atualizar slug tambem
                    updates.append(f"slug = ${param_idx}")
                    params.append(slugify(value))
                    param_idx += 1
                updates.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1

        if updates:
            params.append(tag_id)
            await conn.execute(
                f"UPDATE tags SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ${param_idx}",
                *params
            )

        updated = await conn.fetchrow("SELECT * FROM tags WHERE id = $1", tag_id)
        return row_to_dict(updated)

    finally:
        await conn.close()


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: str,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Exclui tag"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        existing = await conn.fetchrow(
            "SELECT id FROM tags WHERE id = $1 AND user_id = $2",
            tag_id, user["id"]
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Tag nao encontrada")

        await conn.execute("DELETE FROM tags WHERE id = $1", tag_id)
        return {"message": "Tag excluida com sucesso"}

    finally:
        await conn.close()


# === ENDPOINTS - SETTINGS ===

@router.get("/settings")
async def get_settings(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna configuracoes do usuario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        settings = await conn.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1",
            user["id"]
        )

        if not settings:
            # Criar configuracoes padrao
            settings_id = str(uuid_lib.uuid4())
            await conn.execute("""
                INSERT INTO user_settings (id, user_id) VALUES ($1, $2)
            """, settings_id, user["id"])
            settings = await conn.fetchrow(
                "SELECT * FROM user_settings WHERE id = $1", settings_id
            )

        return row_to_dict(settings)
    finally:
        await conn.close()


@router.put("/settings")
async def update_settings(
    settings: UserSettingsUpdate,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Atualiza configuracoes do usuario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Garantir que existe
        existing = await conn.fetchrow(
            "SELECT id FROM user_settings WHERE user_id = $1",
            user["id"]
        )
        if not existing:
            settings_id = str(uuid_lib.uuid4())
            await conn.execute(
                "INSERT INTO user_settings (id, user_id) VALUES ($1, $2)",
                settings_id, user["id"]
            )

        updates = []
        params = []
        param_idx = 1

        for field, value in settings.model_dump(exclude_unset=True).items():
            if value is not None:
                if field == "reminder_days":
                    value = json.dumps(value)
                updates.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1

        if updates:
            params.append(user["id"])
            await conn.execute(
                f"UPDATE user_settings SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ${param_idx}",
                *params
            )

        updated = await conn.fetchrow(
            "SELECT * FROM user_settings WHERE user_id = $1", user["id"]
        )
        return row_to_dict(updated)

    finally:
        await conn.close()


# === ENDPOINTS - STATISTICS ===

@router.get("/stats")
async def get_stats(
    period: str = "month",  # week, month, year, all
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna estatisticas detalhadas do usuario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        # Definir intervalo
        interval_map = {
            "week": "7 days",
            "month": "30 days",
            "year": "365 days",
            "all": "100 years"
        }
        interval = interval_map.get(period, "30 days")

        # Estatisticas gerais
        stats = await conn.fetchrow(f"""
            SELECT
                COUNT(*) as total_entries,
                SUM(word_count) as total_words,
                AVG(word_count) as avg_words,
                AVG(mood_score) as avg_mood,
                COUNT(DISTINCT entry_date) as days_with_entries
            FROM diary_entries
            WHERE user_id = $1 AND deleted_at IS NULL
            AND entry_date >= CURRENT_DATE - INTERVAL '{interval}'
        """, user["id"])

        # Distribuicao de humor
        mood_distribution = await conn.fetch(f"""
            SELECT mood, COUNT(*) as count
            FROM diary_entries
            WHERE user_id = $1 AND deleted_at IS NULL
            AND mood IS NOT NULL
            AND entry_date >= CURRENT_DATE - INTERVAL '{interval}'
            GROUP BY mood
            ORDER BY count DESC
        """, user["id"])

        # Entradas por dia da semana
        entries_by_weekday = await conn.fetch(f"""
            SELECT EXTRACT(DOW FROM entry_date) as weekday, COUNT(*) as count
            FROM diary_entries
            WHERE user_id = $1 AND deleted_at IS NULL
            AND entry_date >= CURRENT_DATE - INTERVAL '{interval}'
            GROUP BY weekday
            ORDER BY weekday
        """, user["id"])

        # Tags mais usadas
        top_tags = await conn.fetch(f"""
            SELECT t.name, t.color, COUNT(*) as count
            FROM tags t
            JOIN entry_tags et ON t.id = et.tag_id
            JOIN diary_entries e ON et.entry_id = e.id
            WHERE e.user_id = $1 AND e.deleted_at IS NULL
            AND e.entry_date >= CURRENT_DATE - INTERVAL '{interval}'
            GROUP BY t.id, t.name, t.color
            ORDER BY count DESC
            LIMIT 10
        """, user["id"])

        return {
            "period": period,
            "general": row_to_dict(stats),
            "mood_distribution": [row_to_dict(r) for r in mood_distribution],
            "entries_by_weekday": [row_to_dict(r) for r in entries_by_weekday],
            "top_tags": [row_to_dict(r) for r in top_tags]
        }
    finally:
        await conn.close()


@router.get("/mood-history")
async def get_mood_history(
    days: int = 30,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna historico de humor"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        rows = await conn.fetch("""
            SELECT recorded_date, mood, mood_score, energy_level, notes
            FROM mood_history
            WHERE user_id = $1
            AND recorded_date >= CURRENT_DATE - $2 * INTERVAL '1 day'
            ORDER BY recorded_date DESC, recorded_time DESC
        """, user["id"], days)

        return [row_to_dict(r) for r in rows]
    finally:
        await conn.close()


@router.post("/mood")
async def record_mood(
    mood_data: MoodRecordCreate,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Registra humor (sem criar entrada)"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        mood_id = str(uuid_lib.uuid4())
        recorded_date = mood_data.recorded_date or date.today().isoformat()

        await conn.execute("""
            INSERT INTO mood_history (id, user_id, mood, mood_score, energy_level, notes, recorded_date)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, mood_id, user["id"], mood_data.mood, mood_data.mood_score,
            mood_data.energy_level, mood_data.notes, recorded_date)

        created = await conn.fetchrow("SELECT * FROM mood_history WHERE id = $1", mood_id)
        return row_to_dict(created)

    finally:
        await conn.close()


# === ENDPOINTS - PROMPTS ===

@router.get("/prompts")
async def get_prompts(
    category: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Lista prompts de escrita"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        if category:
            rows = await conn.fetch("""
                SELECT * FROM writing_prompts
                WHERE (user_id = $1 OR is_system = TRUE) AND is_active = TRUE
                AND category = $2
                ORDER BY is_system DESC, times_used DESC
            """, user["id"], category)
        else:
            rows = await conn.fetch("""
                SELECT * FROM writing_prompts
                WHERE (user_id = $1 OR is_system = TRUE) AND is_active = TRUE
                ORDER BY is_system DESC, times_used DESC
            """, user["id"])

        return [row_to_dict(r) for r in rows]
    finally:
        await conn.close()


@router.get("/prompts/random")
async def get_random_prompt(
    category: Optional[str] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna um prompt aleatorio"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        if category:
            prompt = await conn.fetchrow("""
                SELECT * FROM writing_prompts
                WHERE (user_id = $1 OR is_system = TRUE) AND is_active = TRUE
                AND category = $2
                ORDER BY RANDOM()
                LIMIT 1
            """, user["id"], category)
        else:
            prompt = await conn.fetchrow("""
                SELECT * FROM writing_prompts
                WHERE (user_id = $1 OR is_system = TRUE) AND is_active = TRUE
                ORDER BY RANDOM()
                LIMIT 1
            """, user["id"])

        if not prompt:
            raise HTTPException(status_code=404, detail="Nenhum prompt encontrado")

        return row_to_dict(prompt)
    finally:
        await conn.close()


# === ENDPOINTS - STREAK ===

@router.get("/streak")
async def get_streak(
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Retorna informacoes de streak do usuario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        streak = await conn.fetchrow(
            "SELECT * FROM user_streaks WHERE user_id = $1",
            user["id"]
        )

        if not streak:
            return {
                "current_streak": 0,
                "longest_streak": 0,
                "total_entries": 0,
                "total_words": 0,
                "achievements": []
            }

        return row_to_dict(streak)
    finally:
        await conn.close()


# === FUNCAO AUXILIAR PARA STREAK ===

async def update_user_streak(conn, user_id: str, entry_date: str):
    """Atualiza streak do usuario apos criar entrada"""
    try:
        streak = await conn.fetchrow(
            "SELECT * FROM user_streaks WHERE user_id = $1",
            user_id
        )

        today = date.fromisoformat(entry_date) if isinstance(entry_date, str) else entry_date

        if not streak:
            # Criar streak
            await conn.execute("""
                INSERT INTO user_streaks (
                    id, user_id, current_streak, longest_streak,
                    streak_start_date, last_entry_date, total_entries, total_words
                ) VALUES ($1, $2, 1, 1, $3, $3, 1, 0)
            """, str(uuid_lib.uuid4()), user_id, today)
        else:
            last_date = streak["last_entry_date"]
            current = streak["current_streak"] or 0
            longest = streak["longest_streak"] or 0
            total = streak["total_entries"] or 0

            if last_date:
                diff = (today - last_date).days
                if diff == 1:
                    # Continua streak
                    current += 1
                elif diff > 1:
                    # Quebrou streak
                    current = 1
                # Se diff == 0, mesma data, nao muda streak

            if current > longest:
                longest = current

            await conn.execute("""
                UPDATE user_streaks SET
                    current_streak = $1, longest_streak = $2,
                    last_entry_date = $3, total_entries = $4,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $5
            """, current, longest, today, total + 1, user_id)

    except Exception as e:
        logger.error(f"Erro ao atualizar streak: {e}")


# === ENDPOINTS - EXPORT ===

@router.post("/export")
async def export_entries(
    format: str = "json",  # json, txt, markdown
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tag_ids: Optional[List[str]] = None,
    tenant_data: tuple = Depends(get_tenant_from_token)
):
    """Exporta entradas do diario"""
    tenant, user = tenant_data
    conn = await get_tenant_connection(tenant)

    try:
        where_clauses = ["user_id = $1", "deleted_at IS NULL"]
        params = [user["id"]]
        param_idx = 2

        if start_date:
            where_clauses.append(f"entry_date >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            where_clauses.append(f"entry_date <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        where_sql = " AND ".join(where_clauses)

        rows = await conn.fetch(f"""
            SELECT * FROM diary_entries
            WHERE {where_sql}
            ORDER BY entry_date ASC, created_at ASC
        """, *params)

        entries = []
        for row in rows:
            entry = row_to_dict(row)
            tags = await conn.fetch("""
                SELECT t.name FROM tags t
                JOIN entry_tags et ON t.id = et.tag_id
                WHERE et.entry_id = $1
            """, row["id"])
            entry["tag_names"] = [t["name"] for t in tags]
            entries.append(entry)

        if format == "json":
            return {"entries": entries, "total": len(entries)}

        elif format == "txt":
            lines = []
            for e in entries:
                lines.append(f"=== {e['entry_date']} ===")
                if e.get('title'):
                    lines.append(f"Titulo: {e['title']}")
                if e.get('mood'):
                    lines.append(f"Humor: {e['mood']}")
                lines.append("")
                lines.append(e['content'])
                lines.append("")
                if e.get('tag_names'):
                    lines.append(f"Tags: {', '.join(e['tag_names'])}")
                lines.append("\n" + "-" * 50 + "\n")
            return {"content": "\n".join(lines), "format": "txt"}

        elif format == "markdown":
            lines = []
            for e in entries:
                lines.append(f"# {e.get('title') or e['entry_date']}")
                lines.append(f"*{e['entry_date']}*")
                if e.get('mood'):
                    lines.append(f"\n**Humor:** {e['mood']}")
                lines.append(f"\n{e['content']}")
                if e.get('tag_names'):
                    lines.append(f"\n**Tags:** {', '.join(e['tag_names'])}")
                lines.append("\n---\n")
            return {"content": "\n".join(lines), "format": "markdown"}

        else:
            raise HTTPException(status_code=400, detail="Formato invalido")

    finally:
        await conn.close()
