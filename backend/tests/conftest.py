import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.support import isolated_settings, migrate


@pytest.fixture
def settings(tmp_path):
    return isolated_settings(tmp_path / "identity-test.db")


@pytest.fixture
def app(settings):
    migrate(settings)
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
