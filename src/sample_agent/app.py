import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from sample_agent.agent import SupportAgent, open_agent


logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    mode: Literal["demo", "azure"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = os.environ.get("AGENT_MODE", "demo")
    async with open_agent(mode) as agent:
        app.state.agent = agent
        app.state.mode = mode
        yield


app = FastAPI(
    title="Soporte TI — agente didáctico",
    description="Datos ficticios. API local de demostración, sin autenticación de usuarios.",
    lifespan=lifespan,
)


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "mode": request.app.state.mode}


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    agent: SupportAgent = request.app.state.agent
    try:
        answer = await asyncio.wait_for(agent.answer(body.message), timeout=45)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="El agente excedió el tiempo límite.") from None
    except Exception as exc:
        logger.warning("Fallo del agente: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="El agente no está disponible. Reintenta o contacta a soporte.",
        ) from None
    return ChatResponse(answer=answer, mode=request.app.state.mode)
