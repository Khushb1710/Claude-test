"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # AI keys
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    anthropic_api_key: str = Field("", env="ANTHROPIC_API_KEY")

    # Google
    google_credentials_file: Path = Field(
        "credentials/google_credentials.json", env="GOOGLE_CREDENTIALS_FILE"
    )
    google_token_file: Path = Field(
        "credentials/google_token.json", env="GOOGLE_TOKEN_FILE"
    )

    # Microsoft
    microsoft_client_id: str = Field("", env="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: str = Field("", env="MICROSOFT_CLIENT_SECRET")
    microsoft_tenant_id: str = Field("", env="MICROSOFT_TENANT_ID")
    microsoft_accounts: list[str] = Field(default_factory=list, env="MICROSOFT_ACCOUNTS")

    # Email / SMTP
    smtp_host: str = Field("smtp.gmail.com", env="SMTP_HOST")
    smtp_port: int = Field(587, env="SMTP_PORT")
    smtp_username: str = Field("", env="SMTP_USERNAME")
    smtp_password: str = Field("", env="SMTP_PASSWORD")
    email_from: str = Field("", env="EMAIL_FROM")
    default_email_recipients: list[str] = Field(default_factory=list, env="DEFAULT_EMAIL_RECIPIENTS")

    # Bot credentials
    bot_google_email: str = Field("", env="BOT_GOOGLE_EMAIL")
    bot_google_password: str = Field("", env="BOT_GOOGLE_PASSWORD")
    bot_zoom_email: str = Field("", env="BOT_ZOOM_EMAIL")
    bot_zoom_password: str = Field("", env="BOT_ZOOM_PASSWORD")
    bot_microsoft_email: str = Field("", env="BOT_MICROSOFT_EMAIL")
    bot_microsoft_password: str = Field("", env="BOT_MICROSOFT_PASSWORD")

    # App behaviour
    join_buffer_minutes: int = Field(2, env="JOIN_BUFFER_MINUTES")
    data_dir: Path = Field(Path("./data"), env="DATA_DIR")
    whisper_model: str = Field("base", env="WHISPER_MODEL")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    model_config = {"env_file": ".env", "extra": "ignore"}

    def model_post_init(self, __context) -> None:
        # Parse comma-separated list fields
        if isinstance(self.microsoft_accounts, str):
            self.microsoft_accounts = [a.strip() for a in self.microsoft_accounts.split(",") if a.strip()]
        if isinstance(self.default_email_recipients, str):
            self.default_email_recipients = [e.strip() for e in self.default_email_recipients.split(",") if e.strip()]
        self.data_dir.mkdir(parents=True, exist_ok=True)
        Path("credentials").mkdir(exist_ok=True)


settings = Settings()
