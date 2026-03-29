"""
ENN - External Neural Network
Entities = neurons. Relationships = synapses. LLM thinks freely.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .api.routes import router, set_storage
from .graph.storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = Storage(db_path="/app/data/enn.db")
    if db.connect():
        logger.info("SQLite connected")
        set_storage(db)
    else:
        logger.warning("SQLite connection failed")
    yield
    from .llm.client import get_llm_client
    client = get_llm_client()
    await client.close()
    db.close()


app = FastAPI(
    title="ENN",
    description="External Neural Network — entities are neurons, relationships are synapses, LLM thinks freely.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

import pathlib
_static_dir = pathlib.Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    index = _static_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"name": "ENN", "version": "3.0.0", "docs": "/docs"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
