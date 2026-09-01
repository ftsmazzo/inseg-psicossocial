from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import get_user_by_email, hash_password
from app.config import export_llm_env, get_settings
from app.db import Base, SessionLocal, engine, ensure_schema_patches
from app.models_db import User
from app.routers import auth, jobs

settings = get_settings()
export_llm_env()
app = FastAPI(title=settings.app_name)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(jobs.router)


@app.on_event("startup")
def on_startup() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_schema_patches()
    db = SessionLocal()
    try:
        admin = get_user_by_email(db, settings.bootstrap_admin_email)
        if not admin:
            db.add(
                User(
                    email=settings.bootstrap_admin_email,
                    name=settings.bootstrap_admin_name,
                    hashed_password=hash_password(settings.bootstrap_admin_password),
                    is_admin=True,
                )
            )
        else:
            admin.name = settings.bootstrap_admin_name
            admin.hashed_password = hash_password(settings.bootstrap_admin_password)
        db.commit()
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.app_name}


STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    img_dir = STATIC_DIR / "img"
    if img_dir.exists():
        app.mount("/img", StaticFiles(directory=img_dir), name="img")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        index = STATIC_DIR / "index.html"
        if index.exists() and not full_path.startswith("api/"):
            return FileResponse(index)
        return {"detail": "Not found"}
