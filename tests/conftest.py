import pytest

from app import create_app
from app.config import Settings
from app.services.health import HealthService


@pytest.fixture
def config_env():
    return {
        "MYSQL_HOST": "mysql.test",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "campusclaw_test",
        "MYSQL_USER": "test",
        "MYSQL_PASSWORD": "synthetic-db-value",
        "QDRANT_URL": "http://qdrant.test:6333",
        "QDRANT_API_KEY": "synthetic-qdrant-value",
    }


@pytest.fixture
def settings(tmp_path, config_env):
    version_file = tmp_path / "BUILD_VERSION"
    version_file.write_text("test-build")
    return Settings.load(config_env, version_file)


@pytest.fixture
def make_app(settings):
    instances = []

    def build(
        *, mysql=lambda: True, qdrant=lambda: True, draining=lambda: False, **options
    ):
        health = HealthService(mysql, qdrant, draining)
        instances.append(health)
        return create_app(settings, health=health, **options)

    yield build

    for instance in instances:
        instance.executor.shutdown(wait=True, cancel_futures=True)
