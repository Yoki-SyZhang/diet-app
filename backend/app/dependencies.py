"""FastAPI 依赖注入(1.9)。LLM client 挂在 app.state 上:`lifespan` 里创建共享的
`httpx.AsyncClient`,用 `create_dashscope_client` 工厂包一层——路由层依赖 `LlmClient`
Protocol,测试里 override 这个依赖注入 stub。
"""

from __future__ import annotations

from fastapi import Request

from app.services.llm_client import LlmClient


def get_llm_client(request: Request) -> LlmClient:
    return request.app.state.llm_client
