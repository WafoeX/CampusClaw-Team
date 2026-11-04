from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    qdrant_url: str
    qdrant_api_key: str
    version: str

    @classmethod
    def load(cls, env, version_file: Path):
        def required(key):
            value = env.get(key, "")
            if not value.strip():
                raise ConfigError(key)
            return value

        try:
            version = version_file.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            raise ConfigError("BUILD_VERSION") from None
        if not version or any(not (char.isalnum() or char in ".-") for char in version):
            raise ConfigError("BUILD_VERSION")
        try:
            port = int(required("MYSQL_PORT"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise ConfigError("MYSQL_PORT") from None

        url = required("QDRANT_URL")
        try:
            address = urlsplit(url)
            if (
                address.scheme not in ("http", "https")
                or not address.hostname
                or address.username is not None
                or address.query
                or address.fragment
                or address.port == 0
                or any(char.isspace() or ord(char) < 32 for char in url)
            ):
                raise ValueError
        except ValueError:
            raise ConfigError("QDRANT_URL") from None
        api_key = required("QDRANT_API_KEY")
        if any(not 32 < ord(char) < 127 for char in api_key):
            raise ConfigError("QDRANT_API_KEY")
        return cls(
            mysql_host=required("MYSQL_HOST"),
            mysql_port=port,
            mysql_database=required("MYSQL_DATABASE"),
            mysql_user=required("MYSQL_USER"),
            mysql_password=required("MYSQL_PASSWORD"),
            qdrant_url=url.rstrip("/"),
            qdrant_api_key=api_key,
            version=version,
        )
