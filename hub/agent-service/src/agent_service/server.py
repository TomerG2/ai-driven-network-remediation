from fastapi import FastAPI

app = FastAPI(title="agent-service")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"ready": True}


def start():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
