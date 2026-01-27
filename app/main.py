from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.endpoints import router
from app.services.analysis_service import AnalysisService
from app.utils.logger import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 실행 시 초기화 작업을 수행합니다.
    - 무거운 AI 모델들을 미리 로드하여 첫 요청의 지연 시간을 줄입니다.
    """
    logger.info("🚀 [System] Starting PULSE AI Server...")
    
    # 분석 서비스 초기화 (모델 로드)
    # AnalysisService는 싱글톤이므로 여기서 초기화하면
    # API 엔드포인트에서 사용하는 인스턴스에도 적용됩니다.
    service = AnalysisService()
    service.initialize()
    
    logger.info("✅ [System] All models loaded. Server is ready!")
    
    yield
    
    logger.info("🛑 [System] Shutting down...")

# FastAPI 앱 생성
app = FastAPI(
    title="PULSE AI Server",
    description="외식업 마케팅 자동화를 위한 AI/Data 분석 서버",
    version="2.0.0",
    lifespan=lifespan
)

# CORS 설정 (Spring Boot 및 프론트엔드 연동)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 배포 시에는 구체적인 도메인으로 제한 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(router, prefix="/api")

@app.get("/")
def root():
    return {"message": "PULSE AI Server is running properly."}
