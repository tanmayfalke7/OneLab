"""Validated environment configuration; production never uses a generated secret."""
import os
import secrets
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    demo_user_email: str = "auditor@onelab.finance"
    demo_user_password: str = "Onelab@2026"
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    max_upload_mb: int = 5
    max_csv_rows: int = 50000

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, value: str) -> str:
        if value not in {"development", "production"}: raise ValueError("ENVIRONMENT must be development or production")
        return value

    def model_post_init(self, __context):
        if not self.secret_key:
            if self.environment == "production": raise RuntimeError("SECRET_KEY is required in production")
            self.secret_key = secrets.token_urlsafe(48)
        if self.jwt_algorithm != "HS256": raise RuntimeError("Only JWT_ALGORITHM=HS256 is supported")
        if self.max_upload_mb < 1 or self.max_csv_rows < 1: raise RuntimeError("Upload limits must be positive")

    @property
    def origins(self) -> list[str]: return [v.strip() for v in self.allowed_origins.split(",") if v.strip()]

@lru_cache
def get_settings() -> Settings: return Settings()
