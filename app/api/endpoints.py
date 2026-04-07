import asyncio
import json
import threading
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas.dtos import (
    AnalysisRequestRequest,
    GenerateReviewRepliesRequest,
    GenerateReviewRepliesResponse,
    PersonaResponse,
    PromotionPromptPreviewResponse,
    PromotionPromptRecommendationResponse,
    PromotionTaskStatusResponse,
    ReviewSnapshotResponse,
    TaskResponse,
    TaskStatusResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.crawler_service import CrawlerService
from app.services.llm_service import LLMService
from app.services.mongo_service import MongoService
from app.services.promotion_video_service import PromotionVideoService
from app.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

tasks: dict[str, dict[str, Any]] = {}
task_lock = threading.Lock()
promotion_tasks: dict[str, dict[str, Any]] = {}
promotion_task_lock = threading.Lock()

crawler_service = CrawlerService()
analysis_service = AnalysisService()
llm_service = LLMService()
mongo_service = MongoService()
promotion_video_service = PromotionVideoService()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _create_task(task_id: str) -> None:
    with task_lock:
        tasks[task_id] = {
            "status": "pending",
            "message": "분석 대기 중입니다.",
            "progress": 0,
            "result": None,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }


def _update_task(task_id: str, **updates: Any) -> None:
    with task_lock:
        task = tasks.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = _utc_now_iso()


def _get_task(task_id: str) -> dict[str, Any] | None:
    with task_lock:
        task = tasks.get(task_id)
        return dict(task) if task else None


def _create_promotion_task(task_id: str) -> None:
    with promotion_task_lock:
        promotion_tasks[task_id] = {
            "status": "processing",
            "message": "홍보영상 생성을 준비하는 중입니다.",
            "progress": 0,
            "data": None,
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }


def _update_promotion_task(task_id: str, **updates: Any) -> None:
    with promotion_task_lock:
        task = promotion_tasks.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = _utc_now_iso()


def _get_promotion_task(task_id: str) -> dict[str, Any] | None:
    with promotion_task_lock:
        task = promotion_tasks.get(task_id)
        return dict(task) if task else None


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


def _process_analysis_task(task_id: str, store_name: str, address: str) -> None:
    logger.info("Task %s started processing", task_id)

    try:
        _update_task(
            task_id,
            status="processing",
            message="리뷰 데이터를 수집하는 중입니다.",
            progress=10,
        )

        reviews = asyncio.run(crawler_service.collect_all_reviews(store_name, address))
        if not reviews:
            _update_task(
                task_id,
                status="failed",
                message="리뷰를 찾을 수 없습니다.",
                progress=0,
            )
            return

        mongo_service.initialize()
        mongo_service.save_raw_reviews(task_id, store_name, address, reviews)

        _update_task(
            task_id,
            status="processing",
            message="리뷰 토픽을 분석하는 중입니다.",
            progress=40,
        )

        analysis_result = analysis_service.run_analysis(reviews)
        if "error" in analysis_result:
            _update_task(
                task_id,
                status="failed",
                message=f"분석 실패: {analysis_result['error']}",
                progress=0,
            )
            return

        _update_task(
            task_id,
            status="processing",
            message="페르소나와 고객 여정을 생성하는 중입니다.",
            progress=70,
        )

        final_report = llm_service.generate_full_report(store_name, analysis_result)
        mongo_service.save_result(task_id, final_report)

        _update_task(
            task_id,
            status="completed",
            message="분석 완료",
            progress=100,
            result=final_report,
        )
        logger.info("Task %s completed successfully", task_id)
    except Exception as exc:
        logger.error("Task %s failed: %s\n%s", task_id, exc, traceback.format_exc())
        _update_task(
            task_id,
            status="failed",
            message=f"서버 내부 오류: {exc}",
            progress=0,
        )


def _start_analysis_worker(task_id: str, store_name: str, address: str) -> None:
    worker = threading.Thread(
        target=_process_analysis_task,
        args=(task_id, store_name, address),
        name=f"analysis-{task_id[:8]}",
        daemon=True,
    )
    worker.start()


def _process_promotion_task(
    task_id: str,
    target: str,
    concept: str,
    mode: str,
    style: str,
    image_path: str | None,
) -> None:
    try:
        _update_promotion_task(
            task_id,
            status="processing",
            progress=5,
            message="홍보영상 작업을 시작하는 중입니다.",
        )

        result = promotion_video_service.generate_video(
            target=target,
            concept=concept,
            mode=mode,
            style=style,
            image_path=image_path,
            progress_callback=lambda progress, message: _update_promotion_task(
                task_id,
                status="processing",
                progress=progress,
                message=message,
            ),
        )
        _update_promotion_task(
            task_id,
            status="complete",
            progress=100,
            message="홍보영상 생성이 완료되었습니다.",
            data={
                "videoUrl": result["videoUrl"],
                "videoTitle": result["videoTitle"],
                "hashtags": result["hashtags"],
                "generationTime": result.get("generationTime"),
            },
        )
    except Exception as exc:
        logger.error("Promotion task %s failed: %s\n%s", task_id, exc, traceback.format_exc())
        _update_promotion_task(
            task_id,
            status="error",
            progress=0,
            message=f"홍보영상 생성 실패: {exc}",
        )


def _start_promotion_worker(
    task_id: str,
    target: str,
    concept: str,
    mode: str,
    style: str,
    image_path: str | None,
) -> None:
    worker = threading.Thread(
        target=_process_promotion_task,
        args=(task_id, target, concept, mode, style, image_path),
        name=f"promotion-{task_id[:8]}",
        daemon=True,
    )
    worker.start()


@router.post("/analysis/request", response_model=TaskResponse)
async def request_analysis(req: AnalysisRequestRequest):
    task_id = str(uuid.uuid4())
    _create_task(task_id)
    _start_analysis_worker(task_id, req.shopInfo_name, req.shopInfo_address)
    return TaskResponse(
        task_id=task_id,
        status="pending",
        message="분석 요청을 접수했습니다.",
    )


@router.get("/analysis/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = _get_task(task_id)
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
    task = _get_task(task_id)
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
    store_name: str = Query(..., description="Store name"),
    address: str = Query(..., description="Store address"),
    refresh_if_needed: bool = Query(False, description="Refresh crawler result when snapshot is stale"),
    target_total_reviews: int = Query(0, description="Desired minimum review count"),
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


@router.post("/info/generate", response_model=TaskResponse)
async def generate_promotion_video(
    target: str = Form(...),
    concept: str = Form(...),
    mode: str = Form(...),
    style: str = Form(...),
    image: UploadFile | None = File(None),
):
    task_id = str(uuid.uuid4())
    image_path = None

    if image is not None:
        image_bytes = await image.read()
        image_path = promotion_video_service.save_upload(
            image.filename or "promotion.jpg",
            image_bytes,
        )

    _create_promotion_task(task_id)
    _start_promotion_worker(task_id, target, concept, mode, style, image_path)

    return TaskResponse(
        task_id=task_id,
        status="processing",
        message="홍보영상 생성을 시작했습니다.",
    )


@router.post("/info/prompt-preview", response_model=PromotionPromptPreviewResponse)
async def preview_promotion_prompt(
    target: str = Form(...),
    concept: str = Form(...),
    mode: str = Form(...),
    style: str = Form(...),
    image: UploadFile | None = File(None),
):
    image_path = None
    if image is not None:
        image_bytes = await image.read()
        image_path = promotion_video_service.save_upload(
            image.filename or "promotion-preview.jpg",
            image_bytes,
        )

    plan = promotion_video_service.prompt_service.build_prompt_plan(
        target=target,
        concept=concept,
        style=style,
        mode=mode,
        image_path=image_path,
    )
    return PromotionPromptPreviewResponse(**plan)


@router.post("/info/prompt-recommendation", response_model=PromotionPromptRecommendationResponse)
async def recommend_promotion_prompt(
    target: str = Form(...),
    style: str = Form(...),
    mode: str = Form(...),
    store_name: str = Form(""),
    store_summary: str = Form(""),
    persona_label: str = Form(""),
    persona_summary: str = Form(""),
    action_recommendation: str = Form(""),
    persona_tags_json: str = Form("[]"),
    image: UploadFile | None = File(None),
):
    image_path = None
    if image is not None:
        image_bytes = await image.read()
        image_path = promotion_video_service.save_upload(
            image.filename or "promotion-recommendation.jpg",
            image_bytes,
        )

    try:
        persona_tags = json.loads(persona_tags_json or "[]")
    except json.JSONDecodeError:
        persona_tags = []

    recommended_prompt = promotion_video_service.prompt_service.recommend_concept_prompt(
        target=target,
        style=style,
        mode=mode,
        store_name=store_name,
        store_summary=store_summary,
        persona_label=persona_label,
        persona_summary=persona_summary,
        persona_tags=persona_tags if isinstance(persona_tags, list) else [],
        action_recommendation=action_recommendation,
        image_path=image_path,
    )

    return PromotionPromptRecommendationResponse(
        recommendedPrompt=recommended_prompt,
        videoTitle=f"{persona_label or store_name or '맞춤'} 홍보영상",
        hashtags=[],
        metadata={
            "optimizer": "persona-auto-complete",
            "style": style,
            "mode": mode,
        },
    )


@router.get("/info/status/{task_id}", response_model=PromotionTaskStatusResponse)
async def get_promotion_status(task_id: str):
    task = _get_promotion_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return PromotionTaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        message=task["message"],
        data=task.get("data"),
    )
