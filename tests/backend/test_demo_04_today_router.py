"""1.9 `GET /today`:返回当前归属日,给前端显示"正在记哪一天"。

只测"路由确实把 attribution_date() 的结果原样吐出来、格式是 ISO 日期"。归属日本身的
边界语义(−2h 切换点、时区换算、跨月跨年)由 test_demo_04_attribution.py 覆盖,
这里不重复——否则同一条规则会有两处断言,改规则要改两个地方。
"""

from datetime import date

from app.services.attribution import attribution_date


class TestTodayRouter:
    def test_returns_current_attribution_date(self, client):
        response = client.get("/today")
        assert response.status_code == 200
        assert response.json() == {"date": attribution_date()}

    def test_date_is_iso_format(self, client):
        payload = client.get("/today").json()
        # 不用 fromisoformat 之外的解析:前端按 "YYYY-MM-DD" 手工拆字符串,格式变了会静默错位
        assert date.fromisoformat(payload["date"]).isoformat() == payload["date"]
