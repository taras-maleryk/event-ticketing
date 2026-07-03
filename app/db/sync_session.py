from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

sync_engine = create_engine(settings.SYNC_DATABASE_URL, echo=settings.DB_ECHO)

sync_session_maker = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False
)