import base64
import time

import httpx
import structlog

from .base import LLMProvider
from .types import ModelRequest, ModelResponse, TokenUsage
from ..utils.path_safety import validate_media_path

logger = structlog.get_logger()

ANTHROPIC_MODELS = [
    # Claude 4.x
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
    # Claude 3.5
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-haiku-20241022",
    # Claude 3
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
]
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-6"):
        self._api_key = api_key
        self._default_model = default_model
        self._healthy = False

    def provider_name(self) -> str:
        return "anthropic"

    async def health_check(self) -> bool:
        if not self._api_key:
            self._healthy = False
            return False
        self._healthy = self._api_key.startswith("sk-ant-")
        return self._healthy

    def available_models(self) -> list[str]:
        return ANTHROPIC_MODELS

    def supports_vision(self, model: str = "") -> bool:
        # All Claude 3+ models support images
        m = model or self._default_model
        return "claude" in m

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self._default_model
        start = time.monotonic()

        system_text = ""
        messages = []
        for i, m in enumerate(request.messages):
            if m.role == "system":
                system_text += m.content + "\n"
            elif (
                m.role == "user"
                and request.image_path
                and i == len(request.messages) - 1
                and self.supports_vision(model)
            ):
                try:
                    safe_path = validate_media_path(request.image_path)
                    with open(safe_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode()
                    import mimetypes
                    mime, _ = mimetypes.guess_type(safe_path)
                    mime = mime or "image/jpeg"
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": img_b64,
                            }},
                            {"type": "text", "text": m.content},
                        ],
                    })
                except Exception as e:
                    logger.warning("anthropic.image_inject_failed", error=str(e))
                    messages.append({"role": m.role, "content": m.content})
            else:
                messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": messages,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = int((time.monotonic() - start) * 1000)

        content_blocks = data.get("content", [])
        content = " ".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )

        usage = data.get("usage", {})

        logger.info(
            "anthropic.generated",
            model=model,
            latency_ms=latency_ms,
            tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        )

        return ModelResponse(
            content=content,
            model_used=model,
            provider="anthropic",
            usage=TokenUsage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            ),
            latency_ms=latency_ms,
        )
