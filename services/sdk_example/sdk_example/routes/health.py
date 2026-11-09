from fastapi import FastAPI

from ..settings import Settings


def register(app: FastAPI) -> None:
    settings: Settings = app.state.settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.mode}
