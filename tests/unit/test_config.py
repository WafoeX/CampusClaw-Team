import pytest

from app.config import ConfigError, Settings
from app.services.health import before_deadline


@pytest.mark.parametrize("value", [None, "", "  "])
def test_RT_F01_missing_and_blank_config(config_env, tmp_path, value):
    metadata = tmp_path / "BUILD_VERSION"
    metadata.write_text("test-build")
    for key in config_env:
        env = dict(config_env)
        if value is None:
            env.pop(key)
        else:
            env[key] = value
        with pytest.raises(ConfigError, match=f"^{key}$"):
            Settings.load(env, metadata)
    if value is None:
        metadata.unlink()
    else:
        metadata.write_text(value)
    with pytest.raises(ConfigError, match="^BUILD_VERSION$"):
        Settings.load(config_env, metadata)


@pytest.mark.parametrize(
    ("key", "value"), [("MYSQL_PORT", "65536"), ("QDRANT_URL", "file:///internal")]
)
def test_RT_F02_invalid_config_does_not_show_original_value(
    config_env, tmp_path, key, value
):
    metadata = tmp_path / "BUILD_VERSION"
    metadata.write_text("test-build")
    with pytest.raises(ConfigError, match=f"^{key}$"):
        Settings.load({**config_env, key: value}, metadata)


@pytest.mark.parametrize(
    ("ms", "expected"), [(999, True), (1000, False), (1001, False)]
)
def test_RT_B02_probe_deadline_is_exclusive(ms, expected):
    assert before_deadline(ms / 1000, 1.0) is expected
