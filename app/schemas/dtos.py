from pydantic import BaseModel, Field
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

class JourneyStep(BaseModel):
    """
    고객 여정 지도의 각 단계 (탐색, 방문, 식사, 공유)
    """
    label: str         # 단계 이름 (탐색, 방문, 식사, 공유)
    action: str        # 행동
    thought: str       # 속마음
    type: str          # 감정 상태 (good, neutral, pain)
    touchpoint: str    # 접점
    painPoint: Optional[str] = None # 불편 요소 (Optional)
    opportunity: str   # 기회 요소 (PULSE의 제안)

class JourneyMap(BaseModel):
    """
    전체 고객 여정 지도
    """
    explore: JourneyStep
    visit: JourneyStep
    eat: JourneyStep
    share: JourneyStep

class PersonaItem(BaseModel):
    """
    개별 페르소나 데이터 (FE: UnifiedInsightPage.jsx - PERSONAS 구조와 일치)
    """
    id: int
    nickname: str      # 페르소나 별명 (예: 시원 국물파)
    tags: List[str]    # 특징 태그 (예: ["해장러", "혼밥"])
    img: str           # 이미지 URL (DiceBear)
    summary: str       # 한 줄 요약
    journey: JourneyMap # 고객 여정 지도
    overall_comment: Optional[str] = None  # LLM 생성 분석 총평
    action_recommendation: Optional[str] = None  # LLM 생성 액션 제안

class PersonaResponse(BaseModel):
    """
    최종 페르소나 결과 DTO
    """
    store_name: str
    average_rating: float
    total_reviews: int
    store_summary: str
    personas: List[PersonaItem] # 상세 페르소나 리스트


class ReviewSnapshotItem(BaseModel):
    id: str
    source: str
    source_label: str
    author: str
    rating: Optional[float] = None
    date: Optional[str] = None
    has_photo: bool = False
    text: str
    raw_text: str


class ReviewSnapshotResponse(BaseModel):
    store_name: str
    address: str
    total_reviews: int
    source_counts: Dict[str, int]
    last_crawled_at: Optional[str] = None
    reviews: List[ReviewSnapshotItem]


class ReviewReplyInput(BaseModel):
    id: str
    source: str
    author: str = "리뷰어"
    rating: Optional[float] = None
    date: Optional[str] = None
    has_photo: bool = False
    text: str
    raw_text: Optional[str] = None


class ReviewReplySettings(BaseModel):
    tone: str = "친근함"
    length: str = "보통"
    includeThanks: bool = True
    includeGreatDay: bool = True
    useEmojis: bool = False
    photoThanks: bool = True
    brandPreset: str = ""
    optionalInstruction: str = ""
    exceptionCases: List[Dict[str, Any]] = Field(default_factory=list)


class GenerateReviewRepliesRequest(BaseModel):
    shop_name: str
    reviews: List[ReviewReplyInput]
    settings: ReviewReplySettings


class GeneratedReviewReply(BaseModel):
    id: str
    review_id: str
    content: str
    is_recommended: bool = False


class GenerateReviewRepliesResponse(BaseModel):
    replies: List[GeneratedReviewReply]
