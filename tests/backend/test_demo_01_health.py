"""1.1 健康检查:GET /health 在数据库可连通时返回 200 + {status: ok, db: ok}。"""


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
