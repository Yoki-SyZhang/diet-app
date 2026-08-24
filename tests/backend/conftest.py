from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db
from app.dependencies import get_llm_client
from app.main import app
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture
def db_session(tmp_path) -> Iterator[Session]:
    """service 层测试直连的 Session,建表走 Base.metadata(ORM 模型与迁移后的 head
    schema 对齐,由 test_demo_04_schema_migration 保证),不碰真实库。"""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'service_test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestSessionLocal()
    yield session
    session.close()
    engine.dispose()


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


@dataclass
class MigratedClient:
    """路由集成测试用:真实 alembic 迁移到 head 的临时 SQLite + TestClient。
    `use_llm(stub)` 把 LLM 依赖换成 stub;`session_factory` 可开 Session 直接
    预置/断言数据库状态。"""

    client: TestClient
    session_factory: sessionmaker

    def use_llm(self, stub) -> None:
        app.dependency_overrides[get_llm_client] = lambda: stub


@pytest.fixture
def migrated_client(tmp_path, monkeypatch) -> Iterator[MigratedClient]:
    db_url = f"sqlite:///{(tmp_path / 'router_test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

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
        yield MigratedClient(client=test_client, session_factory=TestSessionLocal)
    app.dependency_overrides.clear()
    engine.dispose()
