from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str
    schwab_api_key: str = ""
    schwab_app_secret: str = ""
    schwab_token_path: str = "./schwab_token.json"
    polygon_api_key: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email: str = ""
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    timezone: str = "America/Chicago"
    max_symbols_per_strategy: int = 50
    strategy_run_timeout: int = 300
    data_batch_size: int = 20
    data_batch_delay: float = 0.5
    # Months of daily history for HA month-anchor cold-start.
    ha_lookback_months: int = 24
    # Weeks of daily history for HA week-anchor cold-start (Mon–Fri weeks).
    ha_lookback_weeks: int = 24


settings = Settings()
