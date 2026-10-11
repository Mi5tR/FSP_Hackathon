import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./fsp_talent.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    jwt_ttl_minutes: int = int(os.getenv("JWT_TTL_MINUTES", "720"))
    # In dev mode the email verification token is returned in the API response
    # so the demo works without a mail server.
    dev_mode: bool = os.getenv("DEV_MODE", "1") == "1"
    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    cors_origins: tuple[str, ...] = tuple(
        os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(",")
    )
    grade_change_cooldown_days: int = int(os.getenv("GRADE_CHANGE_COOLDOWN_DAYS", "90"))
    same_level_retry_days: int = int(os.getenv("SAME_LEVEL_RETRY_DAYS", "30"))
    skill_retest_days: int = int(os.getenv("SKILL_RETEST_DAYS", "14"))
    employer_weekly_invite_quota: int = int(os.getenv("EMPLOYER_WEEKLY_INVITE_QUOTA", "30"))
    invitation_ttl_days: int = int(os.getenv("INVITATION_TTL_DAYS", "14"))


settings = Settings()
