import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
from time import monotonic
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import OperationalError

from app.ai_schemas import Candidate, RecognitionView
from app.core.config import REAL_AI_PROVIDERS, Settings
from app.core.database import utcnow
from app.models.ai import AiJob, AiJobMedia, AiUsageLog
from app.models.diary import MediaAsset
from app.services.ai_control import HEARTBEAT_INTERVAL, mark_heartbeat, refund_real_call, reserve_real_call
from app.services.ai_jobs import configuration_matches, end_job, matching_photos, retry_later, usage
from app.services.ai_provider import Analysis, FoodRecognitionProvider, ProviderError, prepare_photo
from app.services.storage import LocalStorageProvider

LOGGER = logging.getLogger(__name__)
HELD = ("reserved", "dispatching")


@dataclass(frozen=True)
class Claim:
    job_id: str
    owner: str
    token: str


@dataclass(frozen=True)
class JobPhoto:
    id: str
    sort_order: int
    key: str
    size: int
    digest: str


@dataclass(frozen=True)
class PreparedPhotos:
    photos: list[JobPhoto]
    stamps: list[tuple[int, int, int, int]]
    images: list[bytes]


def file_stamp(stat: os.stat_result) -> tuple[int, int, int, int]:
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


class AiWorker:
    def __init__(self, settings: Settings, sessions, provider: FoodRecognitionProvider):
        self.settings = settings
        self.sessions = sessions
        self.provider = provider
        self.storage = LocalStorageProvider(settings)

    @staticmethod
    def begin(db):
        # A short, database-wide SQLite write lock protects global slots and quota across processes.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")

    def recover(self, db, now):
        expired = db.scalars(select(AiJob).where(AiJob.status == "running", AiJob.lease_until <= now)).all()
        for job in expired:
            attempt = db.get(AiUsageLog, job.claim_token)
            sent = attempt is None or attempt.status != "reserved"
            if sent:
                end_job(job, "failed", now, "ai_result_unknown")
            elif job.attempt_count < job.max_attempts and job.expires_at > now:
                retry_later(job, now, 0, "ai_before_send")
            else:
                end_job(job, "failed", now, "ai_expired" if job.expires_at <= now else "ai_before_send")
        # Includes attempts whose job was cancelled during dispatch.
        for before, after, error in (("reserved", "not_sent", "ai_before_send"),
                                     ("dispatching", "unknown", "ai_result_unknown")):
            db.execute(update(AiUsageLog).where(AiUsageLog.status == before, AiUsageLog.hold_until <= now)
                       .values(status=after, error_code=error))
        db.execute(update(AiJob).where(AiJob.status == "pending", AiJob.expires_at <= now)
                   .values(status="failed", error_code="ai_expired", completed_at=now, updated_at=now))

    def purge(self):
        now = utcnow()
        with self.sessions() as db:
            self.begin(db)
            self.recover(db, now)
            jobs = db.execute(delete(AiJob).where(
                AiJob.completed_at <= now - timedelta(seconds=self.settings.ai_job_retention_seconds),
            )).rowcount
            attempts = db.execute(delete(AiUsageLog).where(
                AiUsageLog.created_at < now - timedelta(seconds=self.settings.ai_usage_retention_seconds),
                ~AiUsageLog.status.in_(HELD),
            )).rowcount
            db.commit()
            return jobs, attempts

    def claim(self) -> Claim | None:
        with self.sessions() as db:
            self.begin(db)
            now = utcnow()
            self.recover(db, now)
            active = db.scalar(select(func.count()).select_from(AiUsageLog).where(AiUsageLog.status.in_(HELD)))
            if active >= self.settings.ai_max_concurrent_jobs:
                db.commit()
                return None
            job = db.scalar(select(AiJob).where(AiJob.status == "pending", AiJob.available_at <= now)
                            .order_by(AiJob.available_at, AiJob.created_at, AiJob.id).limit(1))
            if not job:
                db.commit()
                return None
            quota = usage(db, self.settings, job.user_id, now)
            if not configuration_matches(self.settings, job):
                end_job(job, "failed", now, "ai_configuration_changed")
            elif not quota.available:
                end_job(job, "failed", now, quota.exhausted_reason or "ai_unavailable")
            else:
                token = str(uuid4())
                lease = now + timedelta(seconds=self.settings.ai_timeout_seconds + 30)
                claimed = db.execute(update(AiJob).where(AiJob.id == job.id, AiJob.status == "pending").values(
                    status="running", claim_token=token, lease_until=lease, started_at=now,
                    attempt_count=AiJob.attempt_count + 1, updated_at=now, error_code=None,
                )).rowcount
                if claimed == 1:
                    db.add(AiUsageLog(id=token, job_id=job.id, user_id=job.user_id, provider=job.provider,
                                      model=job.model, status="reserved", created_at=now, hold_until=lease))
                    result = Claim(job.id, job.user_id, token)
                    db.commit()
                    return result
            db.commit()
            return None

    @staticmethod
    def current(db, claim, now):
        return db.scalar(select(AiJob).where(
            AiJob.id == claim.job_id, AiJob.user_id == claim.owner, AiJob.status == "running",
            AiJob.claim_token == claim.token, AiJob.lease_until > now,
        ))

    def photo_records(self, db, job: AiJob) -> list[JobPhoto]:
        rows = db.execute(select(
            MediaAsset.id, AiJobMedia.sort_order, MediaAsset.original_key, MediaAsset.size_bytes, MediaAsset.sha256,
        ).join(AiJobMedia, (AiJobMedia.media_id == MediaAsset.id) & (AiJobMedia.user_id == MediaAsset.user_id))
          .where(AiJobMedia.job_id == job.id, AiJobMedia.user_id == job.user_id)
          .order_by(AiJobMedia.sort_order)).all()
        if (len(rows) > self.settings.ai_max_images or not matching_photos(job, [row.id for row in rows])
                or [row.sort_order for row in rows] != list(range(len(rows)))):
            raise ProviderError("ai_images_expired", sent=False)
        return [JobPhoto(*row) for row in rows]

    def photos(self, claim: Claim) -> PreparedPhotos:
        with self.sessions() as db:
            job = self.current(db, claim, utcnow())
            if job is None:
                raise ProviderError("ai_images_expired", sent=False)
            records = self.photo_records(db, job)
        images, stamps = [], []
        try:
            for photo in records:
                with self.storage.path(photo.key).open("rb") as source:
                    stamp = file_stamp(os.fstat(source.fileno()))
                    content = source.read(photo.size + 1)
                    if (len(content) != photo.size or sha256(content).hexdigest() != photo.digest
                            or stamp != file_stamp(os.fstat(source.fileno()))):
                        raise ProviderError("ai_image_invalid", sent=False)
                images.append(prepare_photo(BytesIO(content), self.settings.ai_image_edge))
                stamps.append(stamp)
        except (OSError, ValueError):
            raise ProviderError("ai_images_expired", sent=False) from None
        return PreparedPhotos(records, stamps, images)

    def dispatch(self, claim: Claim, prepared: PreparedPhotos | None = None) -> bool:
        prepared = prepared if prepared is not None else self.photos(claim)
        with self.sessions() as db:
            self.begin(db)
            now = utcnow()
            job = self.current(db, claim, now)
            attempt = db.get(AiUsageLog, claim.token)
            if not job or not attempt or attempt.status != "reserved":
                return False
            try:
                stamps = []
                if self.photo_records(db, job) == prepared.photos:
                    for photo in prepared.photos:
                        with self.storage.path(photo.key).open("rb") as source:
                            stamps.append(file_stamp(os.fstat(source.fileno())))
                verified = prepared.stamps == stamps
            except (OSError, ValueError, ProviderError):
                verified = False
            quota = usage(db, self.settings, claim.owner, now, exclude=claim.token)
            code = None
            if not configuration_matches(self.settings, job):
                code = "ai_configuration_changed"
            elif not verified:
                code = "ai_images_expired"
            elif job.expires_at <= now:
                code = "ai_expired"
            elif not quota.available:
                code = quota.exhausted_reason or "ai_unavailable"
            elif job.provider in REAL_AI_PROVIDERS and not reserve_real_call(db, self.settings):
                code = "ai_cumulative_limit"
            if code:
                attempt.status, attempt.error_code = "not_sent", code
                end_job(job, "failed", now, code)
                db.commit()
                return False
            attempt.status, attempt.created_at = "dispatching", now
            job.lease_until = attempt.hold_until = now + timedelta(seconds=self.settings.ai_timeout_seconds + 15)
            db.commit()
            return True

    def finish(self, claim: Claim, outcome: Analysis | ProviderError, elapsed_ms: int | None = None):
        with self.sessions() as db:
            self.begin(db)
            now = utcnow()
            job = self.current(db, claim, now)
            attempt = db.get(AiUsageLog, claim.token)
            if not attempt or attempt.status not in HELD or attempt.hold_until <= now:
                return
            counts = outcome.usage
            attempt.input_tokens, attempt.output_tokens = counts.input_tokens, counts.output_tokens
            attempt.upstream_request_id = counts.request_id
            attempt.usage_known = counts.input_tokens is not None and counts.output_tokens is not None
            attempt.elapsed_ms = elapsed_ms
            if isinstance(outcome, Analysis):
                attempt.status = "succeeded"
                if job:
                    values = outcome.result.model_dump(exclude={"foods"})
                    foods = [Candidate(id=uuid4(), **food.model_dump()) for food in outcome.result.foods]
                    job.result_json = RecognitionView(**values, foods=foods).model_dump(mode="json")
                    end_job(job, "succeeded", now)
            else:
                attempt.error_code = outcome.code
                if not outcome.sent and attempt.status == "dispatching" and attempt.provider in REAL_AI_PROVIDERS:
                    refund_real_call(db, attempt.provider)
                attempt.status = (
                    "not_sent" if not outcome.sent else "unknown" if outcome.code == "ai_result_unknown" else "failed"
                )
                if job:
                    delay = max(outcome.retry_after, 2 ** job.attempt_count)
                    retry_at = now + timedelta(seconds=delay)
                    if outcome.retryable and job.attempt_count < job.max_attempts and retry_at < job.expires_at:
                        retry_later(job, now, delay, outcome.code)
                    else:
                        end_job(job, "failed", now, outcome.code)
            db.commit()

    async def process_once(self) -> bool:
        claim = await asyncio.to_thread(self.claim)
        if not claim:
            return False
        dispatched = False
        sent_at = None
        try:
            prepared = await asyncio.to_thread(self.photos, claim)
            dispatched = await asyncio.to_thread(self.dispatch, claim, prepared)
            if not dispatched:
                return True
            sent_at = monotonic()
            async with asyncio.timeout(self.settings.ai_timeout_seconds + 1):
                result = await self.provider.analyze(prepared.images)
        except ProviderError as error:
            result = error
        except TimeoutError:
            result = ProviderError("ai_result_unknown" if dispatched else "ai_before_send", sent=dispatched)
        except OperationalError:
            # The next lease recovery will reconcile the attempt without guessing if it was sent.
            raise
        except Exception:
            LOGGER.error("AI worker attempt failed internally")
            result = ProviderError("ai_result_unknown" if dispatched else "ai_internal", sent=dispatched)
        elapsed_ms = round((monotonic() - sent_at) * 1000) if sent_at is not None else None
        await asyncio.to_thread(self.finish, claim, result, elapsed_ms)
        return True

    def heartbeat(self):
        with self.sessions.begin() as db:
            mark_heartbeat(db, self.settings, utcnow())

    async def run(self):
        async def heartbeat_loop():
            while True:
                try:
                    await asyncio.to_thread(self.heartbeat)
                except OperationalError:
                    LOGGER.warning("AI worker heartbeat temporarily unavailable")
                await asyncio.sleep(HEARTBEAT_INTERVAL)

        async def loop(cleanup: bool):
            loop = asyncio.get_running_loop()
            next_cleanup = 0.0
            while True:
                try:
                    if cleanup and loop.time() >= next_cleanup:
                        await asyncio.to_thread(self.purge)
                        next_cleanup = loop.time() + 60
                    worked = await self.process_once()
                except OperationalError:
                    LOGGER.warning("AI worker database temporarily unavailable")
                    worked = False
                if not worked:
                    await asyncio.sleep(1)

        await asyncio.gather(heartbeat_loop(), *(loop(index == 0) for index in range(self.settings.ai_max_concurrent_jobs)))
