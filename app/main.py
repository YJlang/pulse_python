from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import router
from app.services.analysis_service import AnalysisService
from app.utils.logger import get_logger

logger = get_logger(__name__)
STATIC_ROOT = Path(__file__).resolve().parents[1] / "output"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[System] Starting PULSE AI Server...")

    service = AnalysisService()
    service.initialize()

    logger.info("[System] All models loaded. Server is ready!")

    yield

    logger.info("[System] Shutting down...")


app = FastAPI(
    title="PULSE AI Server",
    description="AI and data analysis service for PULSE.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")


@app.get("/")
def root():
    return {"message": "PULSE AI Server is running properly."}
