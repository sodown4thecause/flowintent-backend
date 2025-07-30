"""Configuration management for the Natural Language Workflow Platform."""

import os
from typing import List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """Database configuration settings."""
    url: str
    host: str = "localhost"
    port: int = 5432
    name: str = "workflow_platform"
    user: str = "postgres"
    password: str = ""


class RedisConfig(BaseModel):
    """Redis configuration settings."""
    url: str = "redis://localhost:6379/0"
    host: str = "localhost"
    port: int = 6379
    db: int = 0


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""
    api_key: str
    model: str = "gpt-4o"
    model_mini: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    openai_model_mini: str = Field("gpt-4o-mini", env="OPENAI_MODEL_MINI")
    openai_embedding_model: str = Field("text-embedding-3-small", env="OPENAI_EMBEDDING_MODEL")
    
    # Database Configuration
    database_url: str = Field(..., env="DATABASE_URL")
    database_host: str = Field("localhost", env="DATABASE_HOST")
    database_port: int = Field(5432, env="DATABASE_PORT")
    database_name: str = Field("workflow_platform", env="DATABASE_NAME")
    database_user: str = Field("postgres", env="DATABASE_USER")
    database_password: str = Field("", env="DATABASE_PASSWORD")
    
    # Redis Configuration
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    redis_port: int = Field(6379, env="REDIS_PORT")
    redis_db: int = Field(0, env="REDIS_DB")
    
    # Application Configuration
    secret_key: str = Field(..., env="SECRET_KEY")
    algorithm: str = Field("HS256", env="ALGORITHM")
    access_token_expire_minutes: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    debug: bool = Field(True, env="DEBUG")
    
    # CORS Configuration
    allowed_origins: List[str] = Field(
        ["http://localhost:3000", "http://localhost:8000"], 
        env="ALLOWED_ORIGINS"
    )
    
    # Vector Database Configuration
    vector_db_url: Optional[str] = Field(None, env="VECTOR_DB_URL")
    
    # External API Configuration
    webhook_secret: Optional[str] = Field(None, env="WEBHOOK_SECRET")
    
    # Google Services
    google_drive_client_id: Optional[str] = Field(None, env="GOOGLE_DRIVE_CLIENT_ID")
    google_drive_client_secret: Optional[str] = Field(None, env="GOOGLE_DRIVE_CLIENT_SECRET")
    google_sheets_client_id: Optional[str] = Field(None, env="GOOGLE_SHEETS_CLIENT_ID")
    google_sheets_client_secret: Optional[str] = Field(None, env="GOOGLE_SHEETS_CLIENT_SECRET")
    google_calendar_client_id: Optional[str] = Field(None, env="GOOGLE_CALENDAR_CLIENT_ID")
    google_calendar_client_secret: Optional[str] = Field(None, env="GOOGLE_CALENDAR_CLIENT_SECRET")
    
    # Slack Configuration
    slack_client_id: Optional[str] = Field(None, env="SLACK_CLIENT_ID")
    slack_client_secret: Optional[str] = Field(None, env="SLACK_CLIENT_SECRET")
    slack_signing_secret: Optional[str] = Field(None, env="SLACK_SIGNING_SECRET")
    slack_redirect_uri: Optional[str] = Field(None, env="SLACK_REDIRECT_URI")
    
    # Twitter API
    twitter_client_id: Optional[str] = Field(None, env="TWITTER_CLIENT_ID")
    twitter_client_secret: Optional[str] = Field(None, env="TWITTER_CLIENT_SECRET")
    twitter_bearer_token: Optional[str] = Field(None, env="TWITTER_BEARER_TOKEN")
    twitter_api_key: Optional[str] = Field(None, env="TWITTER_API_KEY")
    twitter_api_key_secret: Optional[str] = Field(None, env="TWITTER_API_KEY_SECRET")
    
    # YouTube API
    youtube_api_key: Optional[str] = Field(None, env="YOUTUBE_API_KEY")
    
    # AI Services
    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    cerebras_api_key: Optional[str] = Field(None, env="CEREBRAS_API_KEY")
    
    # Supabase Configuration
    supabase_url: Optional[str] = Field(None, env="SUPABASE_URL")
    supabase_service_key: Optional[str] = Field(None, env="SUPABASE_SERVICE_KEY")
    
    # Temporal Configuration
    temporal_host: str = Field("localhost:7233", env="TEMPORAL_HOST")
    temporal_namespace: str = Field("default", env="TEMPORAL_NAMESPACE")
    temporal_task_queue: str = Field("workflow-task-queue", env="TEMPORAL_TASK_QUEUE")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @property
    def database_config(self) -> DatabaseConfig:
        """Get database configuration."""
        return DatabaseConfig(
            url=self.database_url,
            host=self.database_host,
            port=self.database_port,
            name=self.database_name,
            user=self.database_user,
            password=self.database_password
        )
    
    @property
    def redis_config(self) -> RedisConfig:
        """Get Redis configuration."""
        return RedisConfig(
            url=self.redis_url,
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db
        )
    
    @property
    def openai_config(self) -> OpenAIConfig:
        """Get OpenAI configuration."""
        return OpenAIConfig(
            api_key=self.openai_api_key,
            model=self.openai_model,
            model_mini=self.openai_model_mini,
            embedding_model=self.openai_embedding_model
        )


# Global settings instance
settings = Settings()