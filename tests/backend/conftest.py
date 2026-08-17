from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture
def migrated_engine(tmp_path, monkeypatch):
    """跑真实 alembic 迁移到一个一次性临时 SQLite 文件,绝不触碰
    backend/data/dietapp.db。env.py 会用 DATABASE_URL 环境变量覆盖
    传入的 sqlalchemy.url,所以两处都要设。"""
    db_url = f"sqlite:///{(tmp_path / 'schema_test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    db_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
