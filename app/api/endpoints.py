from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Dict
import uuid
from app.schemas.dtos import (
    AnalysisRequestRequest, TaskResponse, TaskStatusResponse, PersonaResponse
)
from app.services.crawler_service import CrawlerService
from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMService
from app.services.mongo_service import MongoService
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# =========================================================
# 🗄️ In-Memory 작업 저장소 + MongoDB 영구 저장
# =========================================================
# 구조: { task_id: { "status": str, "message": str, "progress": int, "result": dict } }
tasks: Dict[str, Dict] = {}

# 서비스 인스턴스 생성 (싱글톤처럼 활용)
crawler_service = CrawlerService()
analysis_service = AnalysisService()
llm_service = LLMService()
mongo_service = MongoService()

# =========================================================
# ⚙️ 백그라운드 작업 함수 (비즈니스 로직 오케스트레이션)
# =========================================================
async def _process_analysis_task(task_id: str, store_name: str, address: str):
    """
    실제 분석 로직을 순차적으로 수행하는 비동기 함수입니다.
    """
    logger.info(f"🔄 Task {task_id} started processing...")
    
    try:
        # 1. 크롤링 단계
        tasks[task_id].update({"status": "processing", "message": "리뷰 데이터 수집 중 (네이버/카카오)", "progress": 10})
        
        reviews = await crawler_service.collect_all_reviews(store_name, address)
        
        if not reviews:
            tasks[task_id].update({"status": "failed", "message": "리뷰를 찾을 수 없습니다.", "progress": 0})
            return

        logger.info(f"📦 Collected {len(reviews)} reviews. Saving raw reviews to MongoDB...")
        
        # 1.5 원본 리뷰 MongoDB 저장
        try:
            mongo_service.initialize()
            raw_reviews_collection = mongo_service.db["raw_reviews"]
            raw_reviews_collection.insert_one({
                "task_id": task_id,
                "store_name": store_name,
                "address": address,
                "reviews_count": len(reviews),
                "reviews": reviews
            })
            logger.info(f"💾 Raw reviews saved to MongoDB for task {task_id}")
        except Exception as mongo_err:
            logger.warning(f"⚠️ Failed to save raw reviews to MongoDB: {mongo_err}")

        # 2. 분석 단계 (BERTopic)
        tasks[task_id].update({"status": "processing", "message": "리뷰 토픽 분석 중 (AI)", "progress": 40})
        
        analysis_result = analysis_service.run_analysis(reviews)
        
        if "error" in analysis_result:
            tasks[task_id].update({"status": "failed", "message": f"분석 실패: {analysis_result['error']}", "progress": 0})
            return

        # 3. 페르소나 생성 단계 (LLM)
        tasks[task_id].update({"status": "processing", "message": "고객 페르소나 및 리포트 생성 중", "progress": 70})
        
        final_report = llm_service.generate_full_report(store_name, analysis_result)
        
        # 4. MongoDB에 최종 결과 저장
        try:
            mongo_service.save_result(task_id, final_report)
            logger.info(f"💾 Final report saved to MongoDB for task {task_id}")
        except Exception as mongo_err:
            logger.warning(f"⚠️ Failed to save final report to MongoDB: {mongo_err}")
        
        # 5. 완료
        tasks[task_id].update({
            "status": "completed",
            "message": "분석 완료!",
            "progress": 100,
            "result": final_report
        })
        logger.info(f"✅ Task {task_id} completed successfully.")

    except Exception as e:
        import traceback
        logger.error(f"❌ Task {task_id} failed: {e}\n{traceback.format_exc()}")
        tasks[task_id].update({"status": "failed", "message": f"서버 내부 오류: {str(e)}", "progress": 0})

# =========================================================
# 🌐 API 엔드포인트 정의
# =========================================================

@router.post("/analysis/request", response_model=TaskResponse)
async def request_analysis(req: AnalysisRequestRequest, background_tasks: BackgroundTasks):
    """
    분석 요청 API
    - 즉시 Task ID를 반환하고, 분석 작업은 백그라운드에서 실행합니다.
    """
    task_id = str(uuid.uuid4())
    
    # 작업 초기화
    tasks[task_id] = {
        "status": "pending",
        "message": "작업 대기 중...",
        "progress": 0,
        "result": None
    }
    
    # 백그라운드 작업 등록
    background_tasks.add_task(_process_analysis_task, task_id, req.shopInfo_name, req.shopInfo_address)
    
    return TaskResponse(task_id=task_id, status="pending", message="분석 요청이 접수되었습니다.")

@router.get("/analysis/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    작업 상태 조회 API (Polling)
    - FE에서 로딩 바를 그리기 위해 주기적으로 호출합니다.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"], # 0~100
        message=task["message"],
        result=None # 상태 조회 시에는 무거운 결과 데이터 생략 (최적화)
    )

@router.get("/analysis/result/{task_id}", response_model=PersonaResponse)
async def get_task_result(task_id: str):
    """
    작업 결과 조회 API
    - status가 'completed'일 때 호출하여 최종 데이터를 받아갑니다.
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task is not completed yet")
        
    return task["result"]

@router.get("/analysis/latest")
async def get_latest_result():
    """
    MongoDB에서 가장 최근 분석 결과를 조회합니다.
    FE의 인사이트(손님분석) 탭에서 호출합니다.
    """
    try:
        mongo_service.initialize()
        collection = mongo_service.db["analysis_results"]
        
        # 가장 최근 결과 가져오기 (_id 기준 역순 정렬)
        doc = collection.find_one(
            sort=[("_id", -1)]  # 최신순
        )
        
        if not doc:
            raise HTTPException(status_code=404, detail="분석 결과가 없습니다. 먼저 회원가입을 통해 분석을 실행해주세요.")
        
        # MongoDB _id는 JSON 직렬화 불가 → 제거
        doc.pop("_id", None)
        doc.pop("task_id", None)
        
        logger.info(f"📊 Latest analysis result returned: {doc.get('store_name', 'N/A')}")
        return doc
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to fetch latest result: {e}")
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

