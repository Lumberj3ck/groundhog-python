from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(
        default=None, validation_alias="OPENAI_BASE_URL"
    )
    openai_model: str = Field(
        default="openai/gpt-oss-20b", validation_alias="OPENAI_MODEL"
    )

    # Local data
    notes_dir: str = Field(..., validation_alias="NOTES_DIR")

    # Calendar auth
    google_credentials_file: Optional[str] = Field(
        default=None, validation_alias="GOOGLE_CREDENTIALS_FILE"
    )
    google_client_id: Optional[str] = Field(
        default=None, validation_alias="GOOGLE_CLIENT_ID"
    )
    google_client_secret: Optional[str] = Field(
        default=None, validation_alias="GOOGLE_SECRET"
    )
    google_redirect_url: Optional[str] = Field(
        default=None, validation_alias="GOOGLE_REDIRECT_URL"
    )

    # Auth
    jwt_secret: str = Field(default="change-me", validation_alias="JWT_SECRET")
    master_password: Optional[str] = Field(
        default=None, validation_alias="MASTER_PASSWORD"
    )

    model_config = SettingsConfigDict(populate_by_name=True)


@lru_cache()
def get_settings() -> Settings:
    # BaseModel can read from environment directly
    return Settings()  # type: ignore[arg-type]


