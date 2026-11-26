import json
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256

from app.ai_schemas import ESTIMATE_FIELDS, RecognitionView
from app.core.config import Settings
from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.diary_schemas import ItemInput
from app.services.ai_jobs import linked_photos, matching_photos, owned_job


def item_values(item: ItemInput):
    return item.model_dump(exclude={"id", "ai_reference"})


def estimate_digest(values: dict) -> str:
    snapshot = {name: values[name] for name in ("food_name", "category", *ESTIMATE_FIELDS)}
    for name in ESTIMATE_FIELDS:
        if snapshot[name] is not None:
            amount = Decimal(snapshot[name])
            snapshot[name] = str(amount.normalize()) if amount else "0"
    return sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def verify_candidate(db, settings: Settings, owner: str, meal_id: str, media_ids: set[str], reference):
    job = owned_job(db, owner, str(reference.job_id))
    if (job.status != "succeeded" or not job.result_json
            or job.completed_at + timedelta(seconds=settings.ai_job_retention_seconds) <= utcnow()
            or (job.provider == "fake" and settings.app_env == "production")):
        raise ApiError(409, "ai_candidate_unavailable", "这项识别结果已不可用，可手动保存。")
    candidate = next((food for food in RecognitionView.model_validate(job.result_json).foods
                      if food.id == reference.candidate_id), None)
    if candidate is None:
        raise ApiError(404, "ai_candidate_not_found", "识别候选不存在或不可访问。")
    if job.adopted_meal_id and job.adopted_meal_id != meal_id:
        raise ApiError(409, "ai_candidate_used", "这次识别结果已用于另一条饮食记录。")
    original = linked_photos(db, job)
    if ((job.form_meal_id and job.form_meal_id != meal_id) or not matching_photos(job, original)
            or not media_ids.issuperset(original)):
        raise ApiError(422, "ai_candidate_context", "这次识别的照片或餐次已变化，可以将候选转为手动明细。")
    job.adopted_meal_id = meal_id
    return dict(ai_job_id=job.id, ai_candidate_id=str(candidate.id), ai_provider=job.provider, ai_model=job.model,
                ai_prompt_version=job.prompt_version, ai_original_digest=estimate_digest(candidate.model_dump()))
