import mimetypes
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from google.auth.exceptions import DefaultCredentialsError
from google import genai
from google.genai import types

from app.services.promotion_prompt_service import PromotionPromptService
from app.utils.logger import get_logger

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=False)

logger = get_logger(__name__)


FALSEY_ENV_VALUES = {"0", "false", "off", "no"}


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
        self.veo_api_key = os.getenv("VEO_API_KEY")
        self.gemini_api_key = self.veo_api_key or os.getenv("GEMINI_API_KEY")
        self.vertex_api_key = os.getenv("VERTEX_VIDEO_API_KEY")
        self.vertex_output_gcs_uri = os.getenv("PROMOTION_VEO_OUTPUT_GCS_URI", "").strip()
        self.provider = (os.getenv("PROMOTION_VEO_PROVIDER") or "").strip().lower()
        if not self.provider:
            self.provider = "vertex" if self.project_id else "gemini"
        self.enable_secondary_backend_fallback = (
            os.getenv("PROMOTION_VEO_ENABLE_SECONDARY_BACKEND_FALLBACK", "false").strip().lower()
            not in FALSEY_ENV_VALUES
        )

        # Gemini API defaults.
        self.standard_model = os.getenv("PROMOTION_VEO_STANDARD_MODEL", "veo-3.1-generate-preview")
        self.pro_model = os.getenv("PROMOTION_VEO_PRO_MODEL", self.standard_model)
        self.fast_model = os.getenv("PROMOTION_VEO_FAST_MODEL", "veo-3.1-fast-generate-preview")
        self.fallback_model = os.getenv("PROMOTION_VEO_FALLBACK_MODEL", "")

        # Vertex defaults favor the more stable Veo 2 line.
        self.vertex_standard_model = os.getenv("PROMOTION_VEO_VERTEX_STANDARD_MODEL", "veo-2.0-generate-001")
        self.vertex_pro_model = os.getenv("PROMOTION_VEO_VERTEX_PRO_MODEL", self.vertex_standard_model)
        self.vertex_fast_model = os.getenv("PROMOTION_VEO_VERTEX_FAST_MODEL", self.vertex_standard_model)
        self.vertex_fallback_model = os.getenv("PROMOTION_VEO_VERTEX_FALLBACK_MODEL", "")

        self.standard_resolution = os.getenv("PROMOTION_VEO_STANDARD_RESOLUTION", "1080p")
        self.pro_resolution = os.getenv("PROMOTION_VEO_PRO_RESOLUTION", "4k")
        self.fast_resolution = os.getenv("PROMOTION_VEO_FAST_RESOLUTION", "720p")
        self.fallback_resolution = os.getenv("PROMOTION_VEO_FALLBACK_RESOLUTION", "720p")
        self.vertex_standard_resolution = os.getenv("PROMOTION_VEO_VERTEX_STANDARD_RESOLUTION", "720p")
        self.vertex_pro_resolution = os.getenv("PROMOTION_VEO_VERTEX_PRO_RESOLUTION", self.vertex_standard_resolution)
        self.vertex_fast_resolution = os.getenv("PROMOTION_VEO_VERTEX_FAST_RESOLUTION", self.vertex_standard_resolution)
        self.vertex_fallback_resolution = os.getenv(
            "PROMOTION_VEO_VERTEX_FALLBACK_RESOLUTION",
            self.vertex_standard_resolution,
        )

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
        available_builders: dict[str, Callable[[], genai.Client]] = {}
        if self.gemini_api_key:
            available_builders["gemini-api"] = lambda: genai.Client(api_key=self.gemini_api_key)
        if self.project_id:
            available_builders["vertex-adc"] = lambda: genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location,
                http_options=types.HttpOptions(api_version="v1"),
            )

        if not available_builders:
            return []

        if self.provider == "gemini":
            priority = ["gemini-api", "vertex-adc"]
        else:
            priority = ["vertex-adc", "gemini-api"]

        ordered_names = [name for name in priority if name in available_builders]
        if self.enable_secondary_backend_fallback:
            return [(name, available_builders[name]) for name in ordered_names]

        return [(ordered_names[0], available_builders[ordered_names[0]])]

    def _mode_profiles(self, mode: str, *, client_name: str) -> list[dict[str, str]]:
        normalized_mode = (mode or "").strip().lower()
        if client_name.startswith("vertex"):
            standard_model = self.vertex_standard_model
            pro_model = self.vertex_pro_model
            fast_model = self.vertex_fast_model
            fallback_model = self.vertex_fallback_model
            standard_resolution = self.vertex_standard_resolution
            pro_resolution = self.vertex_pro_resolution
            fast_resolution = self.vertex_fast_resolution
            fallback_resolution = self.vertex_fallback_resolution
        else:
            standard_model = self.standard_model
            pro_model = self.pro_model
            fast_model = self.fast_model
            fallback_model = self.fallback_model
            standard_resolution = self.standard_resolution
            pro_resolution = self.pro_resolution
            fast_resolution = self.fast_resolution
            fallback_resolution = self.fallback_resolution

        if normalized_mode == "pro":
            profiles = [
                {"name": "pro", "model": pro_model, "resolution": pro_resolution},
                {"name": "standard", "model": standard_model, "resolution": standard_resolution},
            ]
        elif normalized_mode == "standard_fast":
            profiles = [
                {"name": "fast", "model": fast_model, "resolution": fast_resolution},
                {"name": "standard", "model": standard_model, "resolution": standard_resolution},
            ]
        else:
            profiles = [
                {"name": "standard", "model": standard_model, "resolution": standard_resolution},
                {"name": "fast", "model": fast_model, "resolution": fast_resolution},
            ]

        if fallback_model:
            profiles.append(
                {"name": "fallback", "model": fallback_model, "resolution": fallback_resolution}
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

    def _build_video_config(
        self,
        *,
        client_name: str,
        profile: dict[str, str],
        plan: dict[str, Any],
        reference_images: list[types.VideoGenerationReferenceImage] | None,
        duration_seconds: int,
    ) -> types.GenerateVideosConfig:
        config_kwargs: dict[str, Any] = {
            "aspect_ratio": (plan.get("metadata") or {}).get("aspect_ratio", "9:16"),
            "duration_seconds": duration_seconds,
            "resolution": profile["resolution"],
            "negative_prompt": ", ".join(plan.get("negative_prompts") or []),
        }

        if reference_images:
            config_kwargs["reference_images"] = reference_images

        if client_name.startswith("vertex") and self.vertex_output_gcs_uri:
            config_kwargs["output_gcs_uri"] = self.vertex_output_gcs_uri

        return types.GenerateVideosConfig(**config_kwargs)

    def _normalize_generation_error(self, errors: list[Exception]) -> RuntimeError:
        if not errors:
            return RuntimeError(
                "Video generation could not be completed. "
                "No usable Gemini or Vertex authentication method was found."
            )

        error = errors[-1]
        message = str(error)
        combined_message = " | ".join(str(item) for item in errors)

        if (
            any("RESOURCE_EXHAUSTED" in str(item) or "Quota exceeded" in str(item) for item in errors)
            and any(isinstance(item, DefaultCredentialsError) or "DefaultCredentialsError" in str(item) for item in errors)
        ):
            return RuntimeError(
                "The configured Gemini API key is out of quota, and the fallback Vertex AI path is not authenticated "
                "on this machine. Enable billing for the Gemini key or set up Vertex AI ADC credentials."
            )

        if isinstance(error, DefaultCredentialsError) or "DefaultCredentialsError" in message:
            return RuntimeError(
                "Vertex AI authentication is not configured on this machine. "
                "Set up Application Default Credentials (ADC) for the configured Google Cloud project "
                "before using Veo through Vertex AI. "
                "This backend does not rely on VERTEX_VIDEO_API_KEY alone."
            )

        if "RESOURCE_PROJECT_INVALID" in message:
            return RuntimeError(
                "The provided Vertex video key could not be mapped to a usable Google Cloud project for Veo. "
                "Use standard Vertex AI project authentication (ADC/service account) with "
                "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION for video generation."
            )

        if "RESOURCE_EXHAUSTED" in message or "Quota exceeded" in message:
            if "free_tier" in message or "FreeTier" in message:
                return RuntimeError(
                    "The configured Gemini API key has exhausted its free-tier quota. "
                    "Enable paid billing for that key or switch to Vertex AI with project credentials."
                )
            return RuntimeError(
                "Google rejected the Veo request because the configured account or project is out of quota "
                "or billing capacity."
            )

        return RuntimeError(f"Video generation could not be completed. {combined_message}")

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

        client_builders = self._client_builders()
        if not client_builders:
            raise RuntimeError(
                "No Veo authentication is configured. "
                "Set VEO_API_KEY or GEMINI_API_KEY for the Gemini API, or configure "
                "GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION with Vertex AI ADC credentials."
            )

        attempt_errors: list[Exception] = []
        for client_name, build_client in client_builders:
            try:
                client = build_client()
            except Exception as exc:
                attempt_errors.append(exc)
                logger.warning(
                    "[PromotionVideoService] Failed to initialize %s client: %s",
                    client_name,
                    exc,
                )
                continue

            for profile in self._mode_profiles(mode, client_name=client_name):
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
                        config=self._build_video_config(
                            client_name=client_name,
                            profile=profile,
                            plan=plan,
                            reference_images=reference_images,
                            duration_seconds=duration_seconds,
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
                    attempt_errors.append(exc)
                    logger.warning(
                        "[PromotionVideoService] Video generation attempt via %s/%s failed: %s",
                        client_name,
                        profile["model"],
                        exc,
                    )

        raise self._normalize_generation_error(attempt_errors)
