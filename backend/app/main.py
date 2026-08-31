from fastapi import FastAPI

from .config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name}
