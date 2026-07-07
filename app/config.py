"""
Application configuration loaded from environment variables.

All Azure Entra ID settings are loaded from a .env file (or system
environment variables). This keeps secrets out of source code.

Usage:
    from app.config import get_settings
    settings = get_settings()
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Copy .env.example to .env and fill in your Azure values before running.
    See docs/azure_setup.md for how to obtain each value.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Azure Entra ID ──────────────────────────────────────────
    # Tenant (directory) ID — identifies your Azure AD instance
    azure_tenant_id: str

    # Application (client) ID — identifies this app registration
    azure_client_id: str

    # Object IDs of security groups used for authorisation
    azure_reader_group_id: str
    azure_writer_group_id: str

    # ── Application ─────────────────────────────────────────────
    # App title shown in Swagger UI
    app_title: str = "OAuth Python API"
    app_description: str = "FastAPI application secured with Azure Entra ID"
    app_version: str = "1.0.0"

    # ── Master Configuration ─────────────────────────────────────
    master_config_dir: str = "data/master_config"
    schemas_dir: str = "data/schemas"
    schema_mapping_file: str = "data/schemas/mapping.json"
    max_upload_size_bytes: int = 1_073_741_824  # 1 GB
    protected_files: list[str] = ["master_configuration.json"]
    allowed_components: list[str] = ["cepe", "wasabi", "gvmerge"]

    @property
    def openapi_scope(self) -> str:
        """The scope string used in OAuth2 flows (Swagger UI / frontend)."""
        return f"api://{self.azure_client_id}/access_as_user"

    @property
    def all_group_ids(self) -> list[str]:
        """Both group IDs — for endpoints requiring any authenticated group member."""
        return [self.azure_reader_group_id, self.azure_writer_group_id]


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Using lru_cache ensures the .env file is only read once and the same
    Settings object is reused across the application lifetime.
    """
    return Settings()
