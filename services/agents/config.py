from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    agent_service_port: int = 8001
    environment: str = "development"
    # Max chars sent to LLM per field (prevents runaway costs on huge inputs)
    max_resume_chars: int = 8000
    max_jd_chars: int = 6000

    # LangSmith tracing — set LANGCHAIN_TRACING_V2=true to enable
    langchain_tracing_v2: str = "false"
    langchain_api_key: str = ""
    langchain_project: str = "hireiq"

    class Config:
        env_file = ".env"


settings = Settings()