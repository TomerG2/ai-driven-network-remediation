from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from agent_service.graph import build_graph
from agent_service.models import RemediationState

app = FastAPI(title="agent-service")


class RemediateRequest(BaseModel):
    raw_event: str
    confidence_override: Optional[float] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"ready": True}


@app.post("/remediate")
def remediate(request: RemediateRequest):
    graph = build_graph()
    result = graph.invoke(request.model_dump(exclude_none=True))
    return RemediationState(**result).model_dump()


def start():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
