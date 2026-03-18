from datetime import datetime, timedelta, timezone
from typing import Dict
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.schemas.dtos import (
    AnalysisRequestRequest,
    TaskResponse,
    TaskStatusResponse,
    PersonaResponse,
    ReviewSnapshotResponse,
    GenerateReviewRepliesRequest,
    GenerateReviewRepliesResponse,
)
from app.services.crawler_service import CrawlerService
from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMService
from app.services.mongo_service import MongoService
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

tasks: Dict[str, Dict] = {}

crawler_service = CrawlerService()
analysis_service = AnalysisService()
llm_service = LLMService()
mongo_service = MongoService()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


async def _ensure_review_snapshot(
    store_name: str,
    address: str,
    refresh_if_needed: bool,
    target_total_reviews: int,
):
    snapshot = mongo_service.get_latest_reviews(store_name, address)
    if not refresh_if_needed:
        return snapshot

    should_refresh = snapshot is None
    if snapshot:
        snapshot_version = snapshot.get("crawler_version", 0) or 0
        if snapshot_version < mongo_service.SNAPSHOT_VERSION:
            should_refresh = True
        elif target_total_reviews > 0 and snapshot.get("reviews_count", 0) < target_total_reviews:
            crawled_at = _parse_iso_datetime(snapshot.get("last_crawled_at"))
            if crawled_at is None or crawled_at < datetime.now(timezone.utc) - timedelta(hours=12):
                should_refresh = True

    if not should_refresh:
        return snapshot

    logger.info(
        "Refreshing review snapshot for %s (target_total_reviews=%s)",
        store_name,
        target_total_reviews,
    )
    reviews = await crawler_service.collect_all_reviews(store_name, address)
    if reviews:
        mongo_service.save_raw_reviews(
            f"refresh-{uuid.uuid4()}",
            store_name,
            address,
            reviews,
        )
        return mongo_service.get_latest_reviews(store_name, address)

    return snapshot


async def _process_analysis_task(task_id: str, store_name: str, address: str):
    logger.info("Task %s started processing", task_id)

    try:
        tasks[task_id].update(
            {
                "status": "processing",
                "message": "리뷰 데이터를 수집하는 중입니다.",
                "progress": 10,
            }
        )

        reviews = await crawler_service.collect_all_reviews(store_name, address)
        if not reviews:
            tasks[task_id].update(
                {
                    "status": "failed",
                    "message": "리뷰를 찾을 수 없습니다.",
                    "progress": 0,
                }
            )
            return

        mongo_service.initialize()
        mongo_service.save_raw_reviews(task_id, store_name, address, reviews)

        tasks[task_id].update(
            {
                "status": "processing",
                "message": "리뷰 토픽을 분석하는 중입니다.",
                "progress": 40,
            }
        )

        analysis_result = analysis_service.run_analysis(reviews)
        if "error" in analysis_result:
            tasks[task_id].update(
                {
                    "status": "failed",
                    "message": f"분석 실패: {analysis_result['error']}",
                    "progress": 0,
                }
            )
            return

        tasks[task_id].update(
            {
                "status": "processing",
                "message": "페르소나와 고객 여정을 생성하는 중입니다.",
                "progress": 70,
            }
        )

        final_report = llm_service.generate_full_report(store_name, analysis_result)
        mongo_service.save_result(task_id, final_report)

        tasks[task_id].update(
            {
                "status": "completed",
                "message": "분석 완료",
                "progress": 100,
                "result": final_report,
            }
        )
        logger.info("Task %s completed successfully", task_id)
    except Exception as exc:
        import traceback

        logger.error("Task %s failed: %s\n%s", task_id, exc, traceback.format_exc())
        tasks[task_id].update(
            {
                "status": "failed",
                "message": f"서버 내부 오류: {exc}",
                "progress": 0,
            }
        )


@router.post("/analysis/request", response_model=TaskResponse)
async def request_analysis(req: AnalysisRequestRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "message": "작업 대기 중",
        "progress": 0,
        "result": None,
    }
    background_tasks.add_task(_process_analysis_task, task_id, req.shopInfo_name, req.shopInfo_address)
    return TaskResponse(task_id=task_id, status="pending", message="분석 요청이 접수되었습니다.")


@router.get("/analysis/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
        result=None,
    )


@router.get("/analysis/result/{task_id}", response_model=PersonaResponse)
async def get_task_result(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task is not completed yet")
    return task["result"]


@router.get("/analysis/latest")
async def get_latest_result():
    try:
        mongo_service.initialize()
        doc = mongo_service.db["analysis_results"].find_one(sort=[("_id", -1)])
        if not doc:
            raise HTTPException(status_code=404, detail="분석 결과가 없습니다.")

        doc.pop("_id", None)
        doc.pop("task_id", None)
        logger.info("Latest analysis result returned: %s", doc.get("store_name", "N/A"))
        return doc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch latest result: %s", exc)
        raise HTTPException(status_code=500, detail=f"서버 오류: {exc}")


@router.get("/reviews/latest", response_model=ReviewSnapshotResponse)
async def get_latest_reviews(
    store_name: str = Query(..., description="가게 이름"),
    address: str = Query(..., description="가게 주소"),
    refresh_if_needed: bool = Query(False, description="부족하거나 오래된 스냅샷이면 재수집"),
    target_total_reviews: int = Query(0, description="원하는 최소 총 리뷰 수"),
):
    try:
        snapshot = await _ensure_review_snapshot(
            store_name=store_name,
            address=address,
            refresh_if_needed=refresh_if_needed,
            target_total_reviews=target_total_reviews,
        )
        if not snapshot:
            raise HTTPException(status_code=404, detail="저장된 리뷰 스냅샷이 없습니다.")

        normalized_reviews = [
            mongo_service._normalize_review(review)
            for review in (snapshot.get("reviews") or [])
        ]

        return ReviewSnapshotResponse(
            store_name=snapshot["store_name"],
            address=snapshot["address"],
            total_reviews=snapshot.get("reviews_count", len(normalized_reviews)),
            source_counts=snapshot.get("source_counts") or {},
            last_crawled_at=snapshot.get("last_crawled_at"),
            reviews=normalized_reviews,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch latest reviews: %s", exc)
        raise HTTPException(status_code=500, detail=f"서버 오류: {exc}")


@router.post("/reviews/replies/generate", response_model=GenerateReviewRepliesResponse)
async def generate_review_replies(req: GenerateReviewRepliesRequest):
    try:
        replies = llm_service.generate_review_replies(
            shop_name=req.shop_name,
            reviews=[review.model_dump() for review in req.reviews],
            settings=req.settings.model_dump(),
        )
        return GenerateReviewRepliesResponse(replies=replies)
    except Exception as exc:
        logger.error("Failed to generate review replies: %s", exc)
        raise HTTPException(status_code=500, detail=f"답변 생성 실패: {exc}")
