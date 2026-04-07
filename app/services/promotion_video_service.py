import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.services.promotion_prompt_service import PromotionPromptService
from app.utils.logger import get_logger

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=False)

logger = get_logger(__name__)


class PromotionVideoService:
    def __init__(self) -> None:
        self.output_root = BASE_DIR / "output" / "promotion"
        self.uploads_dir = self.output_root / "uploads"
        self.videos_dir = self.output_root / "videos"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)

        self.prompt_service = PromotionPromptService()
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.gemini_api_key = (
            os.getenv("VEO_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("VERTEX_VIDEO_API_KEY")
        )

        # Official Gemini API docs currently document Veo 3.1 preview IDs.
        self.standard_model = os.getenv("PROMOTION_VEO_STANDARD_MODEL", "veo-3.1-generate-preview")
        self.pro_model = os.getenv("PROMOTION_VEO_PRO_MODEL", self.standard_model)
        self.fast_model = os.getenv("PROMOTION_VEO_FAST_MODEL", "veo-3.1-fast-generate-preview")
        self.fallback_model = os.getenv("PROMOTION_VEO_FALLBACK_MODEL", "")

        self.standard_resolution = os.getenv("PROMOTION_VEO_STANDARD_RESOLUTION", "1080p")
        self.pro_resolution = os.getenv("PROMOTION_VEO_PRO_RESOLUTION", "4k")
        self.fast_resolution = os.getenv("PROMOTION_VEO_FAST_RESOLUTION", "720p")
        self.fallback_resolution = os.getenv("PROMOTION_VEO_FALLBACK_RESOLUTION", "720p")

    @staticmethod
    def _guess_mime_type(filename: str | None) -> str:
        mime_type, _ = mimetypes.guess_type(filename or "")
        return mime_type or "image/jpeg"

    def save_upload(self, filename: str, content: bytes) -> str:
        suffix = Path(filename or "upload.jpg").suffix or ".jpg"
        upload_path = self.uploads_dir / f"{uuid.uuid4().hex}{suffix}"
        upload_path.write_bytes(content)
        return str(upload_path)

    def _build_prompt_text(self, plan: dict[str, Any]) -> str:
        metadata = plan.get("metadata") or {}
        timeline = plan.get("timeline") or []
        key_elements = plan.get("key_elements") or []
        negative_prompts = plan.get("negative_prompts") or []

        scene_lines = []
        for scene in timeline:
            time_label = scene.get("time", "")
            action = scene.get("action", "")
            if action:
                scene_lines.append(f"{time_label}: {action}".strip(": "))

        negative_text = ", ".join(str(item) for item in negative_prompts if item)
        prompt = (
            "Create a vertical 9:16 Korean restaurant promotional reel. "
            f"Base style: {metadata.get('base_style', '')}. "
            f"Camera setup: {metadata.get('camera_setup', '')}. "
            f"Location: {metadata.get('location', '')}. "
            f"Key elements: {', '.join(str(item) for item in key_elements if item)}. "
            f"Timeline: {' '.join(scene_lines)}."
        )
        if negative_text:
            prompt += f" Avoid: {negative_text}."
        return prompt.strip()

    def _build_reference_images(self, image_path: str | None) -> list[types.VideoGenerationReferenceImage] | None:
        if not image_path:
            return None

        file_path = Path(image_path)
        if not file_path.exists():
            return None

        with file_path.open("rb") as file:
            image_bytes = file.read()

        image = types.Image(
            imageBytes=image_bytes,
            mimeType=self._guess_mime_type(file_path.name),
        )
        return [
            types.VideoGenerationReferenceImage(
                image=image,
                referenceType=types.VideoGenerationReferenceType.ASSET,
            )
        ]

    def _client_builders(self) -> list[tuple[str, Callable[[], genai.Client]]]:
        if self.gemini_api_key:
            return [("gemini-api", lambda: genai.Client(api_key=self.gemini_api_key))]

        builders: list[tuple[str, Callable[[], genai.Client]]] = []
        if self.project_id:
            builders.append(
                (
                    "vertex-adc",
                    lambda: genai.Client(
                        vertexai=True,
                        project=self.project_id,
                        location=self.location,
                        http_options=types.HttpOptions(api_version="v1"),
                    ),
                )
            )
        return builders

    def _mode_profiles(self, mode: str) -> list[dict[str, str]]:
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode == "pro":
            profiles = [
                {"name": "pro", "model": self.pro_model, "resolution": self.pro_resolution},
                {"name": "standard", "model": self.standard_model, "resolution": self.standard_resolution},
            ]
        elif normalized_mode == "standard_fast":
            profiles = [
                {"name": "fast", "model": self.fast_model, "resolution": self.fast_resolution},
                {"name": "standard", "model": self.standard_model, "resolution": self.standard_resolution},
            ]
        else:
            profiles = [
                {"name": "standard", "model": self.standard_model, "resolution": self.standard_resolution},
                {"name": "fast", "model": self.fast_model, "resolution": self.fast_resolution},
            ]

        if self.fallback_model:
            profiles.append(
                {"name": "fallback", "model": self.fallback_model, "resolution": self.fallback_resolution}
            )

        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for profile in profiles:
            key = (profile["model"], profile["resolution"])
            if key in seen or not profile["model"]:
                continue
            seen.add(key)
            deduped.append(profile)
        return deduped

    @staticmethod
    def _duration_for_profile(resolution: str, reference_images: list[types.VideoGenerationReferenceImage] | None) -> int:
        if resolution.lower() in {"1080p", "4k"} or reference_images:
            return 8
        return 6

    def _persist_generated_video(self, client: genai.Client, video: types.Video) -> str:
        local_path = self.videos_dir / f"{uuid.uuid4().hex}.mp4"

        try:
            client.files.download(file=video)
            video.save(str(local_path))
            return f"/static/promotion/videos/{local_path.name}"
        except Exception as exc:
            logger.warning("[PromotionVideoService] Download/save failed: %s", exc)

        uri = getattr(video, "uri", None)
        if uri:
            uri = str(uri)
            if uri.startswith("http://") or uri.startswith("https://"):
                return uri

        raise RuntimeError("Generated video could not be saved locally.")

    def generate_video(
        self,
        *,
        target: str,
        concept: str,
        style: str,
        mode: str,
        image_path: str | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        notify = progress_callback or (lambda *_args: None)
        started_at = time.monotonic()

        notify(15, "홍보영상 콘셉트를 정리하는 중입니다.")
        plan = self.prompt_service.build_prompt_plan(
            target=target,
            concept=concept,
            style=style,
            mode=mode,
            image_path=image_path,
        )
        prompt = self._build_prompt_text(plan)
        reference_images = self._build_reference_images(image_path)
        optimizer_name = (plan.get("metadata") or {}).get("optimizer")

        last_error: Exception | None = None
        for client_name, build_client in self._client_builders():
            client = build_client()
            for profile in self._mode_profiles(mode):
                try:
                    duration_seconds = self._duration_for_profile(
                        profile["resolution"],
                        reference_images,
                    )
                    notify(
                        45,
                        (
                            f"영상 생성 모델({client_name}:{profile['model']}, "
                            f"{profile['resolution']}, optimizer={optimizer_name or 'fallback'})에 요청하는 중입니다."
                        ),
                    )

                    operation = client.models.generate_videos(
                        model=profile["model"],
                        prompt=prompt,
                        config=types.GenerateVideosConfig(
                            aspect_ratio=(plan.get("metadata") or {}).get("aspect_ratio", "9:16"),
                            duration_seconds=duration_seconds,
                            resolution=profile["resolution"],
                            reference_images=reference_images,
                            negative_prompt=", ".join(plan.get("negative_prompts") or []),
                        ),
                    )

                    progress = 55
                    while not operation.done:
                        notify(progress, "Veo가 영상을 생성하는 중입니다.")
                        time.sleep(10)
                        operation = client.operations.get(operation)
                        progress = min(progress + 10, 90)

                    generated_videos = []
                    if getattr(operation, "response", None):
                        generated_videos = getattr(operation.response, "generated_videos", []) or []
                    if not generated_videos and getattr(operation, "result", None):
                        generated_videos = getattr(operation.result, "generated_videos", []) or []

                    if not generated_videos:
                        error = getattr(operation, "error", None)
                        raise RuntimeError(f"Video generation finished without output. {error}")

                    video_url = self._persist_generated_video(client, generated_videos[0].video)
                    elapsed = time.monotonic() - started_at
                    notify(100, "홍보영상 생성이 완료되었습니다.")
                    return {
                        "videoUrl": video_url,
                        "videoTitle": plan.get("title") or f"{concept} 홍보영상",
                        "hashtags": plan.get("hashtags") or ["#홍보영상", "#맛집"],
                        "generationTime": f"{elapsed:.1f}s",
                        "promptPlan": plan,
                        "model": profile["model"],
                        "resolution": profile["resolution"],
                    }
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "[PromotionVideoService] Video generation attempt via %s/%s failed: %s",
                        client_name,
                        profile["model"],
                        exc,
                    )

        raise RuntimeError(
            "Video generation could not be completed. "
            f"{last_error or 'No usable Gemini or Vertex authentication method was found.'}"
        )
