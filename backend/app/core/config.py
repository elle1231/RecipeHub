"""应用配置：从 .env 集中读取所有连接信息与密钥。

所有密钥（模型 API Key、微信 AppSecret）只存在 .env，绝不写进代码或提交到 Git。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    app_name: str = "RecipeHub"
    debug: bool = False

    # 数据库
    database_url: str = "sqlite:///./recipehub.db"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # LLM / Embedding
    openai_api_key: str = ""
    openai_base_url: str = ""
    llm_model: str = ""
    # LLM 温度，默认 1.0（OpenAI 默认值，兼容推理模型如 Kimi K3 只允许 1）。
    llm_temperature: float = 1.0
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    # 向量维度由 embedding_model 决定，必须与模型真实输出一致。
    # BAAI/bge-small-zh-v1.5 输出 512 维。换模型后这里也要改，否则向旧
    # Collection 写入不兼容向量（RH-17 建 Collection 时按此维度定死）。
    embedding_dim: int = 512

    # 微信小程序
    wechat_appid: str = ""
    wechat_appsecret: str = ""


settings = Settings()
