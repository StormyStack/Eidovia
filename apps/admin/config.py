import os
from functools import lru_cache
from urllib.parse import quote_plus
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

def get_env(key: str, default: str = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and (val is None or val == ""):
        raise ValueError(f"Required environment variable '{key}' is missing")
    return val

class AdminSettings(BaseModel):
    # PostgreSQL
    db_host: str = get_env("DATABASE_HOST", "eidovia_postgres")
    db_port: int = int(get_env("DATABASE_PORT", "5432"))
    db_user: str = get_env("POSTGRES_USER", "appuser")
    db_password: str = get_env("DB_PASSWORD", "secretpassword")
    db_name: str = get_env("POSTGRES_DB", "eidovia")

    # Redis
    redis_host: str = get_env("REDIS_HOST", "eidovia_redis")
    redis_port: int = int(get_env("REDIS_PORT", "6379"))
    redis_password: str = get_env("REDIS_PASSWORD", "redissecret")

    # Security
    jwt_secret: str = get_env("JWT_SECRET", "super-secret-jwt-key-for-development-32bytes")
    jwt_algorithm: str = "HS256"
    bcrypt_rounds: int = int(get_env("BCRYPT_ROUNDS", "12"))

    # Service
    admin_port: int = int(get_env("ADMIN_PORT", "8090"))
    admin_host: str = get_env("ADMIN_HOST", "0.0.0.0")

    @property
    def database_url(self) -> str:
        escaped_user = quote_plus(self.db_user)
        escaped_pw = quote_plus(self.db_password)
        return f"postgresql+asyncpg://{escaped_user}:{escaped_pw}@{self.db_host}:{self.db_port}/{self.db_name}"

@lru_cache(maxsize=1)
def get_settings() -> AdminSettings:
    return AdminSettings()
