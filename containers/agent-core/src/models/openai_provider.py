import asyncio
import base64
import time

import httpx
import structlog

from .base import LLMProvider
from .types import ModelRequest, ModelResponse, TokenUsage
from ..utils.path_safety import validate_media_path

logger = structlog.get_logger()

OPENAI_MODELS = [
    # GPT-5
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    # GPT-4o
    "gpt-4o",
    "gpt-4o-mini",
    # Reasoning (o-series)
    "o3",
    "o3-mini",
    "o1",
    "o1-mini",
    "o1-pro",
    # Legacy
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]
XAI_MODELS = [
    # Grok 4
    "grok-4.20-0309-reasoning",
    "grok-4.20-0309-non-reasoning",
    "grok-4-1-fast-reasoning",
    "grok-4-1-fast-non-reasoning",
    # Grok 2 (legacy)
    "grok-2",
    "grok-2-mini",
]
MISTRAL_MODELS = [
    # Large / Medium
    "mistral-large-latest",
    "mistral-large-3",
    "mistral-medium-3.1",
    # Small
    "mistral-small-latest",
    "mistral-small-4",
    "mistral-small-3.2",
    # Ministral
    "ministral-8b-latest",
    "ministral-3b-latest",
    # Reasoning
    "magistral-medium-1.2",
    "magistral-small-1.2",
    # Code
    "codestral-latest",
    "devstral-2",
]
DEEPSEEK_MODELS = [
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-coder",
]
MOONSHOT_MODELS = [
    # Kimi
    "kimi-k2.5",
    "kimi-k2",
    "kimi-k2-thinking",
    # Moonshot legacy
    "moonshot-v1-128k",
    "moonshot-v1-32k",
    "moonshot-v1-8k",
]
OPENROUTER_MODELS = [
    "openai/gpt-5.4",
    "openai/gpt-4o",
    "anthropic/claude-opus-4-6",
    "anthropic/claude-sonnet-4-6",
    "google/gemini-2.5-pro",
    "google/gemini-2.0-flash",
    "meta-llama/llama-4-maverick",
    "mistralai/mistral-large-2411",
    "deepseek/deepseek-r1",
    "x-ai/grok-3",
]
PERPLEXITY_MODELS = [
    "sonar-pro",
    "sonar",
    "sonar-reasoning-pro",
    "sonar-reasoning",
    "llama-3.1-sonar-large-128k-online",
    "llama-3.1-sonar-small-128k-online",
]
HUGGINGFACE_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-72B-Instruct",
]
LMSTUDIO_MODELS  = []  # Dynamic — fetched from local /v1/models endpoint

# Models that support image input
_VISION_MODELS = {"gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview"}


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible provider. Works for OpenAI and xAI (Grok)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        provider_label: str = "openai",
        models: list[str] | None = None,
        default_model: str = "",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._provider_label = provider_label
        self._models = models or OPENAI_MODELS
        self._default_model = default_model or (self._models[0] if self._models else "")
        self._healthy = False

    def provider_name(self) -> str:
        return self._provider_label

    async def health_check(self) -> bool:
        if not self._api_key:
            self._healthy = False
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                self._healthy = resp.status_code == 200
                return self._healthy
        except Exception as e:
            logger.debug(f"{self._provider_label}.health_check.failed", error=str(e))
            self._healthy = False
            return False

    def available_models(self) -> list[str]:
        return self._models

    def supports_vision(self, model: str = "") -> bool:
        m = model or self._default_model
        return any(v in m for v in _VISION_MODELS)

    def supports_audio(self, model: str = "") -> bool:
        # OpenAI Whisper transcription available whenever we have a valid key
        return bool(self._api_key) and self._provider_label == "openai"

    def transcribe_audio_sync(self, audio_path: str) -> str:
        """Synchronous Whisper transcription — safe to run in asyncio.to_thread().

        Uses httpx.Client (sync) so it never touches the event loop.
        File I/O and HTTP are both blocking here, which is correct inside a thread.
        """
        import mimetypes
        try:
            safe_audio_path = validate_media_path(audio_path)
        except ValueError as ve:
            logger.warning("openai.whisper_path_rejected", error=str(ve))
            raise
        mime, _ = mimetypes.guess_type(safe_audio_path)
        if not mime:
            mime = "audio/ogg"
        try:
            with open(safe_audio_path, "rb") as f:
                audio_bytes = f.read()
            if not audio_bytes:
                raise ValueError("audio file is empty")
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": (safe_audio_path.split("/")[-1], audio_bytes, mime)},
                    data={"model": "whisper-1"},
                )
                resp.raise_for_status()
                return resp.json().get("text", "")
        except Exception as e:
            logger.warning("openai.whisper_failed", error=str(e))
            raise  # re-raise so handlers.py can classify the failure type

    async def transcribe_audio(self, audio_path: str) -> str:
        """Async shim — runs transcribe_audio_sync in a thread pool."""
        return await asyncio.to_thread(self.transcribe_audio_sync, audio_path)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self._default_model
        start = time.monotonic()

        # Build messages — inject image into last user message if present
        messages = []
        for i, m in enumerate(request.messages):
            if (
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
                            {"type": "text", "text": m.content},
                            {"type": "image_url", "image_url": {
                                "url": f"data:{mime};base64,{img_b64}",
                                "detail": "auto",
                            }},
                        ],
                    })
                except Exception as e:
                    logger.warning("openai.image_inject_failed", error=str(e))
                    messages.append({"role": m.role, "content": m.content})
            else:
                messages.append({"role": m.role, "content": m.content})

        # Per-model API quirks:
        # - gpt-5.x + o-series: require `max_completion_tokens` (reject `max_tokens`)
        # - o-series reasoning models: also reject custom `temperature`
        _ml = model.lower()
        _is_o_series = (
            _ml.startswith("o1") or _ml.startswith("o3") or _ml.startswith("o4")
        )
        _uses_completion_tokens = _ml.startswith("gpt-5") or _is_o_series
        token_key = "max_completion_tokens" if _uses_completion_tokens else "max_tokens"
        payload = {
            "model": model,
            "messages": messages,
            token_key: request.max_tokens,
        }
        if not _is_o_series:
            payload["temperature"] = request.temperature

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        latency_ms = int((time.monotonic() - start) * 1000)
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        logger.info(
            f"{self._provider_label}.generated",
            model=model,
            latency_ms=latency_ms,
            tokens=usage.get("total_tokens", 0),
        )

        return ModelResponse(
            content=content,
            model_used=model,
            provider=self._provider_label,
            usage=TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            latency_ms=latency_ms,
        )
