from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Logger ---
    ENV: str = Field(default="production", description="environment")
    LOG_LEVEL: str = Field(default="INFO")
    SERVICE_NAME: str = Field(default="bot-svc")

    # --- DB (Bot Service) ---
    POSTGRES_BOT_HOST: str | None = Field(default=None)
    POSTGRES_BOT_PORT: int | None = Field(default=None)
    POSTGRES_BOT_DB: str | None = Field(default=None)
    POSTGRES_BOT_USER: str | None = Field(default=None)
    POSTGRES_BOT_PASSWORD: str | None = Field(default=None)
    POSTGRES_BOT_SSL: str | None = Field(default=None)

    # --- Security / JWT ---
    SECRET_KEY: str = Field(default="YOUR_SUPER_SECRET_KEY_CHANGE_ME_IN_PROD")
    ALGORITHM: str = Field(default="HS256")

    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60 * 24 * 7)  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)
    REFRESH_TOKEN_EXPIRE_DAYS_NOT_REMEMBERED: int = Field(default=1)

    REFRESH_TOKEN_PEPPER: str = Field(default="5f5b2b7d9a8e4e6a1c9b0b4e6f2d7a8c9e1f3a5b7c9d0e2f4a6b8c0d1e3f5a7b9c1d3e5f708192a3b4c5d6e7f8091a2b3c4d5e6f")

    # --- RAG and External LLM Services ---
    RAG_API_URL: str = Field(default="http://172.20.13.39:8506/api/ask")
    LEGACY_BACKEND_URL: str = Field(default="http://172.20.13.39:8506")
    RAG_API_KEY: str = Field(default="")
    RAG_TIMEOUT_SECONDS: int = Field(default=30)

    # --- Refresh Cookie ---
    REFRESH_TOKEN_COOKIE_NAME: str = Field(default="refresh_token")
    REFRESH_TOKEN_COOKIE_PATH: str = Field(default="/auth")
    COOKIE_SECURE: bool = Field(default=False)  # production => True
    COOKIE_SAMESITE: str = Field(default="lax")

    # --- Request / Device Detection ---
    TRUST_PROXY_HEADERS: bool = Field(default=False)

    # --- GeoIP ---
    GEOIP_ENABLED: bool = Field(default=False)
    GEOIP_DB_PATH: str | None = Field(default=None)

    # --- CORS ---
    CORS_ALLOW_ORIGINS: str = Field(default="*")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True)
    CORS_ALLOW_METHODS: str = Field(default="*")
    CORS_ALLOW_HEADERS: str = Field(default="*")

    # --- Redis ---
    REDIS_URL: str = Field(default="redis://edu-redis:6379/0")

    model_config = SettingsConfigDict(
        case_sensitive=False,
    )

    @property
    def cors_allow_origins_list(self) -> list[str]:
        if not self.CORS_ALLOW_ORIGINS:
            return ["*"]
        return [s.strip() for s in self.CORS_ALLOW_ORIGINS.split(",") if s.strip()]

    @property
    def pg_dsn(self) -> str:
        if not all(
            [
                self.POSTGRES_BOT_USER,
                self.POSTGRES_BOT_PASSWORD,
                self.POSTGRES_BOT_HOST,
                self.POSTGRES_BOT_PORT,
                self.POSTGRES_BOT_DB,
            ]
        ):
            raise ValueError("Database configuration is incomplete.")

        pw = quote_plus(self.POSTGRES_BOT_PASSWORD)

        ssl_part = (
            f"?ssl={self.POSTGRES_BOT_SSL}"
            if self.POSTGRES_BOT_SSL and self.POSTGRES_BOT_SSL.lower() != "false"
            else ""
        )

        return (
            f"postgresql+asyncpg://{self.POSTGRES_BOT_USER}:{pw}"
            f"@{self.POSTGRES_BOT_HOST}:{self.POSTGRES_BOT_PORT}/{self.POSTGRES_BOT_DB}"
            f"{ssl_part}"
        )


settings = Settings()
