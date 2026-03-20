from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    azure_openai_scope: str = "https://cognitiveservices.azure.com/.default"
    azure_openai_endpoint: str = Field("https://placeholder.openai.azure.com/", alias="AZURE_OPENAI_ENDPOINT", validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field("2024-02-01", alias="OPENAI_API_VERSION", validation_alias="OPENAI_API_VERSION")
    llm_model: str = "azure_openai:gpt-4.1-mini"
    embedding_model: str = "azure_openai:text-embedding-3-large"
    api_base: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

settings = Settings()