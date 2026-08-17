"""1.1 健康检查:GET /health 在数据库可连通时返回 200 + {status: ok, db: ok},
数据库异常时返回 503 + {status: error, db: error}。"""

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_health_db_failure_returns_503():
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("db unreachable")

    def broken_get_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_get_db
    try:
        with TestClient(app) as broken_client:
            response = broken_client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "error"}
