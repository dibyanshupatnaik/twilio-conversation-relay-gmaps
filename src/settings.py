from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env file."""

    port: int = Field(default=8080, env="PORT")
    ngrok_url: Optional[str] = Field(default=None, env="NGROK_URL")

    openai_api_key: str = Field(env="OPENAI_API_KEY")
    google_places_api_key: str = Field(env="GOOGLE_PLACES_API_KEY")

    twilio_account_sid: str = Field(env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(env="TWILIO_AUTH_TOKEN")
    twilio_messaging_sid: str = Field(env="TWILIO_MESSAGING_SID")

    welcome_greeting: str = Field(
        default="Hey there! I can help you find a great restaurant. "
        "Tell me the cuisine, your location, budget, and if you prefer walking or transit."
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
