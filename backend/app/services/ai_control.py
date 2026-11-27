from datetime import timedelta
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert

from app.core.config import REAL_AI_PROVIDERS
from app.models.ai import AiCallBudget, AiWorkerHeartbeat

HEARTBEAT_INTERVAL = 3
HEARTBEAT_TTL = 12


def processing_identity(settings) -> str:
    # Official endpoint names carry the serving region and, for dedicated endpoints, the workspace.
    fields = (settings.ai_provider, settings.ai_model_name, settings.ai_base_url.rstrip("/"))
    return sha256("\n".join(fields).encode()).hexdigest()


def worker_online(db, settings, now) -> bool:
    if not settings.ai_available:
        return False
    return db.scalar(select(AiWorkerHeartbeat.checked_at).where(
        AiWorkerHeartbeat.configuration == processing_identity(settings),
        AiWorkerHeartbeat.checked_at > now - timedelta(seconds=HEARTBEAT_TTL),
    )) is not None


def mark_heartbeat(db, settings, now):
    statement = insert(AiWorkerHeartbeat).values(configuration=processing_identity(settings), checked_at=now)
    db.execute(statement.on_conflict_do_update(index_elements=["configuration"], set_={"checked_at": now}))


def cumulative_exhausted(db, settings) -> bool:
    if settings.ai_provider not in REAL_AI_PROVIDERS:
        return False
    spent = db.scalar(select(AiCallBudget.spent).where(AiCallBudget.provider == settings.ai_provider))
    return spent is None or spent >= settings.ai_cumulative_limit


def reserve_real_call(db, settings) -> bool:
    result = db.execute(update(AiCallBudget).where(
        AiCallBudget.provider == settings.ai_provider, AiCallBudget.spent < settings.ai_cumulative_limit,
    ).values(spent=AiCallBudget.spent + 1))
    return result.rowcount == 1


def refund_real_call(db, provider):
    db.execute(update(AiCallBudget).where(
        AiCallBudget.provider == provider, AiCallBudget.spent > 0,
    ).values(spent=AiCallBudget.spent - 1))
