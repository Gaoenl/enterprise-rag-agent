from sqlalchemy import MetaData, Table, URL, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

# 数据库
class MemoryDatabase:
    def __init__(self):
        settings = get_settings()

        url = URL.create(
            "postgresql+psycopg",
            username=settings.postgres_user,
            password=settings.postgres_password,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
        )

        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            pool_size=5,
            max_overflow=5,
            pool_timeout=settings.postgres_pool_timeout_seconds,
            connect_args={
                "connect_timeout":
                    settings.postgres_connect_timeout_seconds,
                "application_name": "enterprise-rag-python-memory",
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
        )

        self.sessions = sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

        metadata = MetaData()
        self.conversations = Table(
            "chat_conversation", metadata,
            autoload_with=self.engine,
        )
        self.messages = Table(
            "chat_message", metadata,
            autoload_with=self.engine,
        )
        self.traces = Table(
            "rag_trace", metadata,
            autoload_with=self.engine,
        )

    def close(self):
        self.engine.dispose()
