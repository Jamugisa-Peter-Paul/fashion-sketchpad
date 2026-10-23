"""In-process stand-in for llama-swap's /v1/chat/completions, for tests and local development.

    uvicorn gateway.tools.fake_llm:app --port 8086   # then LLM_URL=http://127.0.0.1:8086/v1

It answers every request with `state.answer` (default: a few shirt details as JSON) and keeps the requests
it got in `state.requests`. Set `state.status` to make it fail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DEFAULT_ANSWER = json.dumps(
    {
        "garment": ["pointed shirt collar", "long sleeves with buttoned cuffs"],
        "front": ["six-button front placket", "two chest flap pockets"],
        "back": ["back yoke", "centre box pleat"],
    }
)


@dataclass
class FakeLlmState:
    answer: str = DEFAULT_ANSWER
    status: int = 200
    requests: list[dict[str, Any]] = field(default_factory=list)


def create_fake_llm(answer: str = DEFAULT_ANSWER) -> FastAPI:
    app = FastAPI(title="Fake LLM")
    app.state.fake = FakeLlmState(answer=answer)

    @app.post("/chat/completions")
    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> JSONResponse:
        fake: FakeLlmState = app.state.fake
        body = await request.json()
        fake.requests.append({"body": body, "authorization": request.headers.get("authorization")})
        if fake.status != 200:
            return JSONResponse({"error": "fake failure"}, status_code=fake.status)
        return JSONResponse(
            {
                "id": "fake",
                "object": "chat.completion",
                "model": body.get("model"),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": fake.answer}, "finish_reason": "stop"}],
            }
        )

    return app


app = create_fake_llm()
