import asyncio
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from anyio import CancelScope
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException

from app.core.exceptions import ApiError, ProblemResponse
from app.dependencies import CurrentUser, Database
from app.diary_schemas import MediaView
from app.services.storage import MEDIA_MISSING, owned_media, release_media_bytes, reserve_media_bytes
from app.services.stickers import derivative

router = APIRouter(prefix="/media", tags=["私有图片"], responses={
    401: {"model": ProblemResponse}, 404: {"model": ProblemResponse}, 413: {"model": ProblemResponse},
})
LIMIT_EXCEEDED = "fooddiary_upload_limit"
UPLOAD_TIMEOUT = "fooddiary_upload_timeout"
UPLOAD_FORM = {
    "requestBody": {"required": True, "content": {"multipart/form-data": {
        "schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}}}
    }}},
}
IMAGE_CONTENT = {200: {"content": {"image/webp": {"schema": {"type": "string", "format": "binary"}}}}}


def bounded_request(request: Request, limit: int):
    length = request.headers.get("content-length")
    if length and length.isdecimal() and int(length) > limit:
        raise ApiError(413, "image_size", "上传请求超过大小限制。")
    total = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 120

    async def receive():
        nonlocal total
        try:
            async with asyncio.timeout_at(deadline):
                message = await request.receive()
        except TimeoutError:
            raise MultiPartException(UPLOAD_TIMEOUT) from None
        total += len(message.get("body", b""))
        if total > limit:
            # Starlette closes partially spooled uploads on multipart errors.
            raise MultiPartException(LIMIT_EXCEEDED)
        return message

    return Request(request.scope, receive)


@router.post("/upload", status_code=201, openapi_extra=UPLOAD_FORM)
async def upload(request: Request, user: CurrentUser, db: Database) -> MediaView:
    settings = request.app.state.settings
    owner = user.id
    request.app.state.rate_limiter.check("media_upload", owner, settings.media_upload_attempts)
    db.rollback()  # Do not hold a read transaction while the client sends bytes.
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "multipart/form-data":
        raise ApiError(415, "upload_format", "请使用图片上传表单。")
    capped = bounded_request(request, settings.image_upload_bytes + 128 * 1024)
    sessions = request.app.state.session_factory
    # Budget both the multipart spool and worst-case normalized/original and thumbnail staging.
    staging = 4 * (settings.image_max_edge ** 2 + settings.image_thumbnail_edge ** 2) + 4 * 1024 ** 2
    reservation = await run_in_threadpool(reserve_media_bytes, sessions, settings,
                                          settings.image_upload_bytes + 128 * 1024 + staging, Path(gettempdir()))
    try:
        async with capped.form(max_files=1, max_fields=0, max_part_size=64 * 1024) as form:
            image = form.get("file")
            if not isinstance(image, UploadFile):
                raise ApiError(422, "image_required", "请选择一张图片。")
            if image.size is None or image.size > settings.image_upload_bytes:
                raise ApiError(413, "image_size", "图片文件超过大小限制。")
            storage = request.app.state.storage
            asset = await run_in_threadpool(storage.create, db, owner, image.file)
            return MediaView.model_validate(asset)
    except HTTPException as error:
        if error.detail == LIMIT_EXCEEDED:
            raise ApiError(413, "image_size", "上传请求超过大小限制。") from None
        if error.detail == UPLOAD_TIMEOUT:
            raise ApiError(408, "upload_timeout", "上传超时，请重试。") from None
        raise ApiError(400, "invalid_upload", "图片上传表单无效。") from None
    finally:
        with CancelScope(shield=True):
            await run_in_threadpool(release_media_bytes, sessions, reservation)


def image_response(request: Request, db: Database, user: CurrentUser, media_id: UUID, thumb: bool):
    asset = owned_media(db, user.id, str(media_id))
    key = asset.thumbnail_key if thumb else asset.original_key
    try:
        path = request.app.state.storage.path(key)
    except ValueError:
        raise ApiError(404, "media_not_found", MEDIA_MISSING) from None
    if not path.is_file():
        raise ApiError(404, "media_not_found", MEDIA_MISSING)
    return FileResponse(path, media_type=asset.content_type,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{media_id}", response_class=FileResponse, responses=IMAGE_CONTENT)
def original(request: Request, db: Database, user: CurrentUser, media_id: UUID):
    return image_response(request, db, user, media_id, False)


@router.get("/{media_id}/thumbnail", response_class=FileResponse, responses=IMAGE_CONTENT)
def thumbnail(request: Request, db: Database, user: CurrentUser, media_id: UUID):
    return image_response(request, db, user, media_id, True)


def sticker_response(request, db, user, media_id, variant):
    asset = derivative(db, user.id, str(media_id))
    if not asset:
        raise ApiError(404, "sticker_not_found", "美食贴纸不存在或不可访问。")
    try:
        path = request.app.state.storage.path(getattr(asset, variant))
    except ValueError:
        raise ApiError(404, "sticker_not_found", "美食贴纸不存在或不可访问。") from None
    if not path.is_file():
        raise ApiError(404, "sticker_not_found", "美食贴纸不存在或不可访问。")
    return FileResponse(path, media_type=asset.content_type,
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{media_id}/sticker", response_class=FileResponse, responses=IMAGE_CONTENT)
def sticker(request: Request, db: Database, user: CurrentUser, media_id: UUID):
    return sticker_response(request, db, user, media_id, "storage_key")


@router.get("/{media_id}/sticker/thumbnail", response_class=FileResponse, responses=IMAGE_CONTENT)
def sticker_thumbnail(request: Request, db: Database, user: CurrentUser, media_id: UUID):
    return sticker_response(request, db, user, media_id, "thumbnail_key")


@router.get("/{media_id}/sticker/cutout", response_class=FileResponse, responses=IMAGE_CONTENT)
def sticker_cutout(request: Request, db: Database, user: CurrentUser, media_id: UUID):
    return sticker_response(request, db, user, media_id, "cutout_key")


@router.delete("/{media_id}", status_code=204, responses={409: {"model": ProblemResponse}})
def remove(request: Request, db: Database, user: CurrentUser, media_id: UUID) -> Response:
    request.app.state.storage.remove(db, user.id, str(media_id))
    return Response(status_code=204)
