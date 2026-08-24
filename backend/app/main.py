from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, health, meal_entries
from app.services.llm_client import create_dashscope_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """共享一个 httpx.AsyncClient(连接池复用),LLM client 挂 app.state,
    路由通过 app.dependencies.get_llm_client 取。"""
    async with httpx.AsyncClient() as http_client:
        app.state.llm_client = create_dashscope_client(http_client)
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="DietApp API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(meal_entries.router)

    return app


app = create_app()
