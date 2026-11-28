import io
import logging
import multiprocessing
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from time import perf_counter_ns
from uuid import uuid4

from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert

from app.core.database import utcnow
from app.core.exceptions import ApiError
from app.models.diary import MediaAsset
from app.models.stickers import MediaDerivative, StickerJob, StickerRuntime
from app.services.sticker_image import (
    FakeBackgroundRemovalProvider, OnnxBackgroundRemovalProvider, PROCESSING_VERSION, StickerImageError, encode, make_sticker,
)
from app.services.stickers import MAX_ATTEMPTS, configuration, derivative, model_directory
from app.services.storage import LocalStorageProvider, lock_owner, release_media_bytes, reserve_media_bytes, storage_usage

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderedSticker:
    dimensions: tuple[int, int]
    files: tuple[bytes, bytes, bytes]
    image_ms: int
    inference_ms: int
    encode_ms: int


def render(source, provider, edge, thumbnail_edge, crop):
    started = perf_counter_ns()
    with Image.open(io.BytesIO(source), formats=["WEBP"]) as original:
        pieces = make_sticker(original, edge, provider, crop)
        encoding = perf_counter_ns()
        files = encode(pieces.sticker), encode(pieces.cutout), encode(pieces.thumbnail(thumbnail_edge))
    return RenderedSticker(pieces.sticker.size, files, (encoding - started) // 1_000_000 - pieces.inference_ms,
                           pieces.inference_ms, (perf_counter_ns() - encoding) // 1_000_000)


def inference_child(pipe, directory, threads, edge, thumbnail_edge):
    provider = None
    with pipe:
        while True:
            try:
                source, crop = pipe.recv()
            except EOFError:
                return
            try:
                if provider is None and (source is None or not crop):
                    try:
                        provider = OnnxBackgroundRemovalProvider(directory, threads)
                    except Exception:
                        raise StickerImageError("model_unavailable") from None
                if source is None:
                    pipe.send((True, None))
                    continue
                pipe.send((True, render(source, None if crop else provider, edge, thumbnail_edge, crop)))
            except StickerImageError as error:
                pipe.send((False, str(error)))
            except Exception:
                pipe.send((False, "inference_failed"))


class ProcessInference:
    def __init__(self, settings):
        self.settings = settings
        self.context = multiprocessing.get_context("spawn")
        self.process = self.pipe = None

    def close(self):
        if self.pipe is not None:
            self.pipe.close()
            self.pipe = None
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=3)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()
            self.process.close()
            self.process = None

    def ensure_started(self):
        if self.process is None or not self.process.is_alive():
            self.close()
            self.pipe, child = self.context.Pipe()
            settings = self.settings
            self.process = self.context.Process(target=inference_child, daemon=True, args=(
                child, model_directory(settings), settings.sticker_threads, settings.sticker_edge, settings.image_thumbnail_edge,
            ))
            self.process.start()
            child.close()

    def warm(self):
        self.ensure_started()
        try:
            self.pipe.send((None, None))
            if not self.pipe.poll(self.settings.sticker_timeout_seconds):
                raise StickerImageError("inference_timeout")
            ok, code = self.pipe.recv()
            if not ok:
                raise StickerImageError(code)
        except (EOFError, OSError):
            raise StickerImageError("model_unavailable") from None

    def __call__(self, source, crop, tick):
        self.ensure_started()
        try:
            self.pipe.send((source, crop))
            for remaining in range(self.settings.sticker_timeout_seconds, 0, -1):
                if self.pipe.poll(1):
                    ok, result = self.pipe.recv()
                    if not ok:
                        raise StickerImageError(result)
                    return result
                if remaining % 3 == 0:
                    tick()
        except (OSError, EOFError):
            self.close()
            raise StickerImageError("inference_failed") from None
        self.close()
        raise StickerImageError("inference_timeout")


@dataclass
class Claim:
    id: str
    user_id: str
    media_id: str
    token: str
    recipe: str
    digest: str
    crop: list[float] | None
    queue_ms: int


class StickerWorker:
    def __init__(self, settings, sessions, processor=None):
        self.settings = settings
        self.sessions = sessions
        self.storage = LocalStorageProvider(settings)
        self.processor = processor
        if processor is None and settings.sticker_provider == "fake":
            self.processor = lambda source, crop, _: render(source, None if crop else FakeBackgroundRemovalProvider(),
                                                           settings.sticker_edge, settings.image_thumbnail_edge, crop)
        elif processor is None:
            self.processor = ProcessInference(settings)

    def close(self):
        if isinstance(self.processor, ProcessInference):
            self.processor.close()

    def warm(self):
        if isinstance(self.processor, ProcessInference):
            self.processor.warm()

    @staticmethod
    def mark(db, now):
        db.execute(insert(StickerRuntime).values(id=1, heartbeat=now).on_conflict_do_update(
            index_elements=[StickerRuntime.id], set_={"heartbeat": now},
        ))

    def heartbeat(self):
        with self.sessions.begin() as db:
            self.mark(db, utcnow())

    def claim(self):
        now = utcnow()
        with self.sessions.begin() as db:
            self.mark(db, now)
            db.execute(update(StickerJob).where(
                StickerJob.status == "pending", StickerJob.updated_at < now - timedelta(days=1),
            ).values(status="failed", error_code="expired"))
            stale = db.scalars(select(StickerJob).where(StickerJob.lease_until <= now)).all()
            for job in stale:
                job.claim, job.lease_until = None, None
                if job.status == "running":
                    job.status = "pending" if job.attempts < MAX_ATTEMPTS else "failed"
                    job.error_code = "inference_timeout"
            db.flush()
            if db.scalar(select(StickerJob.id).where(StickerJob.claim.is_not(None)).limit(1)):
                return None
            job = db.scalar(select(StickerJob).where(StickerJob.status == "pending")
                            .order_by(StickerJob.updated_at, StickerJob.id).limit(1))
            if job is None:
                return None
            job.status, job.claim, job.error_code = "running", str(uuid4()), None
            job.attempts += 1
            job.lease_until = now + timedelta(seconds=self.settings.sticker_timeout_seconds + 15)
            queue_ms = max(0, int((now - job.updated_at).total_seconds() * 1000))
            return Claim(job.id, job.user_id, job.source_media_id, job.claim, job.recipe, job.source_digest, job.crop, queue_ms)

    def source(self, claim):
        with self.sessions() as db:
            asset = db.get(MediaAsset, claim.media_id)
            if asset is None or (asset.user_id, asset.sha256) != (claim.user_id, claim.digest):
                raise StickerImageError("source_invalid")
            key = asset.original_key
        try:
            data = self.storage.path(key).read_bytes()
        except (OSError, ValueError):
            raise StickerImageError("source_invalid") from None
        if sha256(data).hexdigest() != claim.digest:
            raise StickerImageError("source_invalid")
        return data

    def finish(self, claim, output=None, *, error=None, processing_ms=0):
        stem = uuid4().hex
        kinds = ("sticker", "cutout", "sticker-thumb")
        temp = tuple(f"staging/{stem}-{kind}.webp" for kind in kinds)
        keys = tuple(f"stickers/{stem}-{kind}.webp" for kind in kinds)
        old_keys = ()
        reservation = None
        try:
            if output:
                dimensions, files = output.dimensions, output.files
                size = sum(map(len, files))
                root = self.storage.root
                try:
                    reservation = reserve_media_bytes(self.sessions, self.settings, size)
                except ApiError:
                    raise StickerImageError("disk_low") from None
                (root / "staging").mkdir(parents=True, exist_ok=True)
                for key, content in zip(temp, files, strict=True):
                    self.storage.path(key).write_bytes(content)
            with self.sessions.begin() as db:
                lock_owner(db, claim.user_id)
                job = db.get(StickerJob, claim.id)
                if job is None or job.claim != claim.token:
                    return
                if job.status != "running" or job.lease_until <= utcnow():
                    if job.status != "running":
                        job.claim, job.lease_until = None, None
                    return
                job.claim, job.lease_until = None, None
                if error:
                    job.status, job.error_code = "failed", error
                    return
                prior = derivative(db, claim.user_id, claim.media_id)
                count, used = storage_usage(db, claim.user_id)
                if prior:
                    used -= prior.size_bytes
                    count -= 3
                    old_keys = prior.storage_key, prior.cutout_key, prior.thumbnail_key
                if used + size > self.settings.media_user_bytes or count + 3 > self.settings.media_user_files:
                    raise StickerImageError("media_quota")
                if prior:
                    db.delete(prior)
                    db.flush()
                model, version, recipe = configuration(self.settings, claim.crop)
                db.add(MediaDerivative(id=str(uuid4()), user_id=claim.user_id, source_media_id=claim.media_id,
                                       source_digest=claim.digest, recipe=recipe, storage_key=keys[0], cutout_key=keys[1],
                                       thumbnail_key=keys[2], width=dimensions[0], height=dimensions[1], size_bytes=size,
                                       model_name=model, model_version=version, processing_version=PROCESSING_VERSION))
                db.flush()
                for source, destination in zip(temp, keys, strict=True):
                    self.storage.publish(source, destination)
                job.status, job.error_code = "succeeded", None
                job.updated_at = utcnow()
                job.timings = {"queue_ms": claim.queue_ms, "image_ms": output.image_ms, "inference_ms": output.inference_ms,
                               "encode_ms": output.encode_ms, "processing_ms": processing_ms}
            self.storage.discard(*old_keys)
        except Exception:
            if output:
                with self.sessions() as db:
                    published = db.scalar(select(MediaDerivative.id).where(MediaDerivative.storage_key == keys[0]))
                if not published:
                    self.storage.discard(*keys)
            raise
        finally:
            self.storage.discard(*temp)
            release_media_bytes(self.sessions, reservation)

    def run_once(self):
        claim = self.claim()
        if claim is None:
            return False
        try:
            if configuration(self.settings, claim.crop)[2] != claim.recipe:
                raise StickerImageError("configuration_changed")
            started = perf_counter_ns()
            output = self.processor(self.source(claim), claim.crop, self.heartbeat)
            self.finish(claim, output, processing_ms=(perf_counter_ns() - started) // 1_000_000)
        except StickerImageError as error:
            self.finish(claim, error=str(error))
        except Exception:
            LOGGER.error("Sticker job failed during local processing")
            self.finish(claim, error="inference_failed")
        return True
