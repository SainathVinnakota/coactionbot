from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AWS Credentials
    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # AWS Bedrock
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_kb_id: str

    # S3
    s3_bucket_name: str  # Bucket for KB documents (required)

    # OpenAI
    openai_api_key: str
    openai_chat_model: str = "gpt-4o"

    # Crawler
    max_crawl_depth: int = 2
    max_pages_per_crawl: int = 50
    crawl_concurrency: int = 5

    # App
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
