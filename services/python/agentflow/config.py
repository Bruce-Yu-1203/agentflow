"""Application configuration and startup validation."""

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    model_api_key: str = ""
    model_name: str = "claude-3-5-sonnet-20241022"
    model_base_url: str = ""
    embedding_provider: str = "local"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_path: str = "./data/chroma"
    skills_dir: str = "./skills"
    mcp_config: str = "./config/mcp_servers.json"
    api_tokens: str = ""
    seed_demo_docs: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            chroma_port = int(os.getenv("AGENTFLOW_CHROMA_PORT", "8001"))
        except ValueError as exc:
            raise ValueError("AGENTFLOW_CHROMA_PORT must be an integer") from exc
        settings = cls(
            environment=os.getenv("AGENTFLOW_ENV", "development").strip().lower(),
            model_api_key=os.getenv("AGENTFLOW_MODEL_API_KEY", "").strip(),
            model_name=os.getenv("AGENTFLOW_MODEL_NAME", "claude-3-5-sonnet-20241022").strip(),
            model_base_url=os.getenv("AGENTFLOW_MODEL_BASE_URL", "").strip(),
            embedding_provider=os.getenv("AGENTFLOW_EMBEDDING_PROVIDER", "local").strip().lower(),
            embedding_api_key=os.getenv("AGENTFLOW_EMBEDDING_API_KEY", "").strip(),
            embedding_base_url=os.getenv("AGENTFLOW_EMBEDDING_BASE_URL", "").strip(),
            redis_url=os.getenv("AGENTFLOW_REDIS_URL", "redis://localhost:6379/0").strip(),
            chroma_host=os.getenv("AGENTFLOW_CHROMA_HOST", "localhost").strip(),
            chroma_port=chroma_port,
            chroma_path=os.getenv("AGENTFLOW_CHROMA_PATH", "./data/chroma").strip(),
            skills_dir=os.getenv("AGENTFLOW_SKILLS_DIR", "./skills").strip(),
            mcp_config=os.getenv("AGENTFLOW_MCP_CONFIG", "./config/mcp_servers.json").strip(),
            api_tokens=os.getenv("AGENTFLOW_API_TOKENS", "").strip(),
            seed_demo_docs=os.getenv("AGENTFLOW_SEED_DEMO_DOCS", "false").strip().lower() in {"1", "true", "yes"},
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("AGENTFLOW_ENV must be development, test, or production")
        if not self.model_name:
            raise ValueError("AGENTFLOW_MODEL_NAME cannot be empty")
        if self.embedding_provider not in {"local", "online", "auto", "disabled"}:
            raise ValueError("AGENTFLOW_EMBEDDING_PROVIDER must be local, online, auto, or disabled")
        parsed = urlsplit(self.redis_url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("AGENTFLOW_REDIS_URL must be a Redis URL")
        if not 1 <= self.chroma_port <= 65535:
            raise ValueError("AGENTFLOW_CHROMA_PORT must be between 1 and 65535")
        if self.model_base_url:
            provider = urlsplit(self.model_base_url)
            if provider.scheme not in {"http", "https"} or not provider.hostname:
                raise ValueError("AGENTFLOW_MODEL_BASE_URL must be an HTTP(S) URL")
        if self.environment == "production":
            if not self.model_api_key:
                raise ValueError("AGENTFLOW_MODEL_API_KEY is required in production")
            if not self.api_tokens:
                raise ValueError("AGENTFLOW_API_TOKENS is required in production")
            if self.seed_demo_docs:
                raise ValueError("Demo knowledge cannot be seeded in production")
            if not Path(self.skills_dir).is_dir():
                raise ValueError("AGENTFLOW_SKILLS_DIR must exist in production")
