from pydantic import BaseModel
from typing import List, Dict, Optional, Any

# =========================================================
# 📝 데이터 전송 객체 (DTO) 정의
# =========================================================

class AnalysisRequestRequest(BaseModel):
    """
    분석 요청 DTO
    Spring Boot에서 FastAPI로 분석을 요청할 때 사용합니다.
    """
    shopInfo_name: str    # 가게 상호명 (frontend: shopInfo_name)
    shopInfo_address: str # 가게 주소 (frontend: shopInfo_address)

class TaskResponse(BaseModel):
    """
    작업 생성 응답 DTO
    요청을 접수하면 즉시 발급되는 작업 ID를 반환합니다.
    """
    task_id: str       # 고유 작업 ID (UUID)
    status: str        # 현재 상태 (예: "processing")
    message: str       # 상태 메시지

class TaskStatusResponse(BaseModel):
    """
    작업 상태 조회 응답 DTO (Polling용)
    FE에서 로딩 바를 표시하기 위해 주기적으로 호출합니다.
    """
    task_id: str
    status: str        # "processing", "completed", "failed"
    progress: int      # 진행률 (0 ~ 100)
    message: str       # 현재 진행 중인 작업 설명 (예: "네이버 리뷰 수집 중...")
    result: Optional[Dict[str, Any]] = None # 완료 시 결과 데이터 포함

class PersonaResponse(BaseModel):
    """
    최종 페르소나 결과 DTO
    """
    store_name: str
    average_rating: float
    total_reviews: int
    store_summary: str
    personas: List[Dict[str, Any]] # 상세 페르소나 리스트
