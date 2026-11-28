import json
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, inspect

from app.diary_schemas import MealInput
from app.main import create_app
from tests.support import legacy_account, legacy_photo, migrate
from tests.test_diary import create, sample
from tests.test_identity import API


def test_upgrade_from_diary_preserves_rows_media_session_and_old_request_key(settings):
    migrate(settings, "0002_meal_diary")
    meal_id, food_id, key = (str(uuid4()) for _ in range(3))
    with TestClient(create_app(settings)) as old:
        with old.app.state.session_factory.begin() as db:
            owner, auth, _ = legacy_account(db, settings)
            media, image = legacy_photo(db, settings, owner)
        payload = sample(media_ids=[media], items=[{"food_name": "饭团", "calories_kcal": 80.25}])
        data = MealInput.model_validate(payload)
        fields = data.model_dump()
        for item in fields["items"]:
            del item["id"], item["ai_reference"]
        fingerprint = sha256(json.dumps(fields, sort_keys=True, separators=(",", ":"), default=lambda value: (
            str(value.normalize()) if isinstance(value, Decimal) else str(value)
        )).encode()).hexdigest()
        with old.app.state.session_factory.begin() as db:
            metadata = MetaData()
            before = lambda name: Table(name, metadata, autoload_with=db.connection())
            timestamp = data.eaten_at.replace(tzinfo=None)
            db.execute(before("meals").insert().values(
                id=meal_id, user_id=owner, meal_type=data.meal_type, local_date=data.local_date,
                eaten_at=timestamp, timezone=data.timezone, note=data.note, version=1, created_at=timestamp, updated_at=timestamp,
            ))
            db.execute(before("meal_items").insert().values(
                **fields["items"][0], id=food_id, meal_id=meal_id, sort_order=0, source="manual",
                created_at=timestamp, updated_at=timestamp,
            ))
            db.execute(before("meal_media").insert().values(user_id=owner, meal_id=meal_id, media_id=media, sort_order=0))
            db.execute(before("meal_requests").insert().values(user_id=owner, key=key, fingerprint=fingerprint, meal_id=meal_id))
    migrate(settings)
    migrate(settings)
    with TestClient(create_app(settings)) as new:
        assert {"ai_jobs", "ai_job_media", "ai_usage_logs", "ai_retry_requests"} <= set(
            inspect(new.app.state.engine).get_table_names())
        assert new.get(API + "/ready").status_code == 200
        assert new.get(API + "/users/me/settings", headers=auth).json()["timezone"] == "Asia/Tokyo"
        same = create(new, auth, payload, key)
        assert same.status_code == 200 and same.json()["id"] == meal_id
        item = same.json()["items"][0]
        assert (item["id"], item["calories_kcal"], item["source"], item["ai_job_id"]) == (food_id, 80.25, "manual", None)
        assert same.json()["media"][0]["id"] == media
        assert new.get(API + "/media/" + media, headers=auth).content == image
        catalog = new.get(API + "/catalog", headers=auth).json()
        assert catalog["collected"] == 1 and catalog["items"][0]["display_name"] == "饭团"
