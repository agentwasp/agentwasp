import base64
import time

import httpx
import structlog

from .base import LLMProvider
from .types import ModelRequest, ModelResponse, TokenUsage
from ..utils.path_safety import validate_media_path

logger = structlog.get_logger()

GOOGLE_MODELS = [
    # Gemini 3.x (preview)
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    # Gemini 2.5
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    # Gemini 2.0
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    # Gemini 1.5 (legacy)
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]
GOOGLE_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GoogleProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self, api_key: str, default_model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._default_model = default_model
        self._healthy = False

    def provider_name(self) -> str:
        return "google"

    async def health_check(self) -> bool:
        if not self._api_key:
            self._healthy = False
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{GOOGLE_API_URL}?key={self._api_key}")
                self._healthy = resp.status_code == 200
                return self._healthy
        except Exception as e:
            logger.debug("google.health_check.failed", error=str(e))
            self._healthy = False
            return False

    def available_models(self) -> list[str]:
        return GOOGLE_MODELS

    def supports_vision(self, model: str = "") -> bool:
        # All Gemini models support image input
        return True

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self._default_model
        start = time.monotonic()

        system_text = ""
        contents = []
        for i, m in enumerate(request.messages):
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                role = "user" if m.role == "user" else "model"
                if (
                    role == "user"
                    and request.image_path
                    and i == len(request.messages) - 1
                ):
                    parts = [{"text": m.content}]
                    try:
                        safe_path = validate_media_path(request.image_path)
                        with open(safe_path, "rb") as f:
                            img_b64 = base64.b64encode(f.read()).decode()
                        import mimetypes
                        mime, _ = mimetypes.guess_type(safe_path)
                        mime = mime or "image/jpeg"
                        parts.append({"inlineData": {"mimeType": mime, "data": img_b64}})
                    except Exception as e:
                        logger.warning("google.image_inject_failed", error=str(e))
                    contents.append({"role": role, "parts": parts})
                else:
                    contents.append({"role": role, "parts": [{"text": m.content}]})

        # Prepend system prompt to first user message
        if system_text and contents:
            first_text = contents[0]["parts"][0]["text"]
            contents[0]["parts"][0]["text"] = f"{system_text.strip()}\n\n{first_text}"

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        url = f"{GOOGLE_API_URL}/{model}:generateContent?key={self._api_key}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = int((time.monotonic() - start) * 1000)

        candidates = data.get("candidates", [])
        content = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            content = " ".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})

        logger.info(
            "google.generated",
            model=model,
            latency_ms=latency_ms,
            tokens=usage_meta.get("totalTokenCount", 0),
        )

        return ModelResponse(
            content=content,
            model_used=model,
            provider="google",
            usage=TokenUsage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=usage_meta.get("totalTokenCount", 0),
            ),
            latency_ms=latency_ms,
        )
