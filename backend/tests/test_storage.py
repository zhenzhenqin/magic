import os
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models.diary import MediaAsset
from tests.test_diary import create, image_bytes, sample, upload
from tests.test_identity import API, bearer, signed_in


@pytest.fixture
def owner(client):
    return bearer(signed_in(client))


@pytest.mark.parametrize("kind", ["JPEG", "PNG", "WEBP"])
def test_follows_detected_format_and_strips_metadata(client, owner, kind):
    data = upload(client, owner, kind, filename="untrusted.txt")
    assert data.status_code == 201
    asset = data.json()
    assert asset["content_type"] == "image/webp" and asset["status"] == "draft"
    original = client.get(API + "/media/" + asset["id"], headers=owner)
    thumb = client.get(API + "/media/" + asset["id"] + "/thumbnail", headers=owner)
    assert original.headers["cache-control"] == thumb.headers["cache-control"] == "no-store"
    assert original.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(thumb.content)) as photo:
        assert max(photo.size) == 400 and "exif" not in photo.info


def test_exif_orientation_and_gps_are_removed(client, owner):
    exif = Image.Exif()
    exif[274] = 6
    exif[34853] = {1: "N", 2: (1.0, 2.0, 3.0)}
    result = upload(client, owner, contents=image_bytes(size=(150, 80), exif=exif)).json()
    assert (result["width"], result["height"]) == (80, 150)
    downloaded = client.get(API + "/media/" + result["id"], headers=owner)
    with Image.open(BytesIO(downloaded.content)) as photo:
        assert photo.size == (80, 150)
        assert not photo.getexif()


def test_rejects_wrong_content_oversize_pixels_and_stream(client, owner, settings):
    assert upload(client, owner, contents=b"<svg>not an image</svg>").status_code == 415
    settings.image_max_pixels = 1000
    assert upload(client, owner).json()["error"]["code"] == "image_pixels"
    settings.image_upload_bytes = 1024
    assert upload(client, owner, contents=b"X" * 2048).status_code == 413
    boundary = "fooddiary-test-boundary"
    header = (
        "--" + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="sample.jpg"'
        + "\r\nContent-Type: image/jpeg\r\n\r\n"
    ).encode()

    def parts():
        yield header
        yield b"X" * (128 * 1024 + 4096)
        yield ("\r\n--" + boundary + "--\r\n").encode()

    response = client.post(API + "/media/upload", content=parts(), headers={
        **owner, "Content-Type": "multipart/form-data; boundary=" + boundary,
    })
    assert response.status_code == 413


def test_quota_and_rate_limit(client, owner, settings):
    settings.media_user_files = 1
    settings.media_upload_attempts = 2
    assert upload(client, owner).status_code == 201
    assert upload(client, owner).json()["error"]["code"] == "media_quota"
    assert upload(client, owner).status_code == 429


def test_partial_disk_failure_leaves_no_files(client, owner, app, monkeypatch):
    storage = app.state.storage
    publish = storage.publish

    def failure(temporary, final):
        if final.startswith("thumbnails/"):
            raise OSError("forced disk failure")
        return publish(temporary, final)

    monkeypatch.setattr(storage, "publish", failure)
    result = upload(TestClient(app, raise_server_exceptions=False), owner)
    assert result.status_code == 500
    assert not list(storage.root.rglob("*.webp"))
    with app.state.session_factory() as db:
        assert db.scalars(select(MediaAsset)).all() == []


def test_database_commit_failure_compensates_published_files(client, owner, app, monkeypatch):
    def fail_commit(_):
        raise RuntimeError("forced local commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    assert upload(TestClient(app, raise_server_exceptions=False), owner).status_code == 500
    assert not list(app.state.storage.root.rglob("*.webp"))
    with app.state.session_factory() as db:
        assert db.scalars(select(MediaAsset)).all() == []


def test_cleanup_dry_run_and_apply_keep_referenced_images(client, owner, app):
    storage = app.state.storage
    draft = upload(client, owner).json()["id"]
    attached = upload(client, owner).json()["id"]
    fresh = upload(client, owner).json()["id"]
    assert create(client, owner, sample(media_ids=[attached])).status_code == 201
    old = utcnow() - timedelta(days=2)
    with app.state.session_factory.begin() as db:
        db.execute(update(MediaAsset).where(MediaAsset.id.in_([draft, attached])).values(updated_at=old))
    leftover = storage.path(f"staging/{uuid4().hex}-original.webp")
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_bytes(b"abandoned")
    os.utime(leftover, (old.timestamp(), old.timestamp()))
    with app.state.session_factory() as db:
        assert storage.sweep(db) == {"unreferenced_assets": 1, "untracked_files": 1}
        assert leftover.exists() and db.get(MediaAsset, draft) is not None
        assert storage.sweep(db, apply=True) == {"unreferenced_assets": 1, "untracked_files": 1}
        assert storage.sweep(db) == {"unreferenced_assets": 0, "untracked_files": 0}
    assert not leftover.exists()
    assert client.get(API + "/media/" + draft, headers=owner).status_code == 404
    assert client.get(API + "/media/" + attached, headers=owner).status_code == 200
    assert client.get(API + "/media/" + fresh, headers=owner).status_code == 200


@pytest.mark.parametrize("key", ["../fooddiary.db", "originals/../file.webp", "C:/Windows/file.webp", "staging/../../secret"])
def test_storage_key_traversal_rejected(app, key):
    with pytest.raises(ValueError):
        app.state.storage.path(key)
