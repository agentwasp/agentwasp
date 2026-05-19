import base64
import time

import httpx
import structlog

from .base import LLMProvider
from .types import Message, ModelRequest, ModelResponse, TokenUsage
from ..utils.path_safety import validate_media_path

logger = structlog.get_logger()

# Vision-capable Ollama model name keywords
_OLLAMA_VISION_KEYWORDS = {"llava", "bakllava", "moondream", "minicpm-v", "cogvlm", "vision", "qwen3.5", "qwen3-vl", "llama4", "glm-ocr", "deepseek-ocr", "gemini-3-flash"}

# Curated catalog of popular Ollama models
# Organized by category. Covers small VPS to powerful workstations.
OLLAMA_CATALOG = [
    # --- General Purpose ---
    {"name": "qwen2.5:0.5b",         "size": "0.4GB",  "cat": "General",   "desc": "Ultra-light, fast, basic tasks"},
    {"name": "qwen2.5:1.5b",         "size": "1.0GB",  "cat": "General",   "desc": "Good balance speed/quality"},
    {"name": "qwen2.5:3b",           "size": "1.9GB",  "cat": "General",   "desc": "Excellent for 8GB systems"},
    {"name": "qwen2.5:7b",           "size": "4.4GB",  "cat": "General",   "desc": "Best quality for 8-16GB"},
    {"name": "qwen2.5:14b",          "size": "9.0GB",  "cat": "General",   "desc": "High quality, needs 16GB+"},
    {"name": "qwen2.5:32b",          "size": "20GB",   "cat": "General",   "desc": "Premium, needs 32GB+"},
    {"name": "qwen3:0.6b",           "size": "0.4GB",  "cat": "General",   "desc": "Qwen3, ultra-light"},
    {"name": "qwen3:1.7b",           "size": "1.0GB",  "cat": "General",   "desc": "Qwen3, improved reasoning"},
    {"name": "qwen3:4b",             "size": "2.5GB",  "cat": "General",   "desc": "Qwen3, best small model"},
    {"name": "qwen3:8b",             "size": "4.9GB",  "cat": "General",   "desc": "Qwen3, strong 8GB model"},
    {"name": "qwen3:14b",            "size": "9.0GB",  "cat": "General",   "desc": "Qwen3, needs 16GB+"},
    {"name": "qwen3:32b",            "size": "20GB",   "cat": "General",   "desc": "Qwen3, needs 32GB+"},
    {"name": "llama3.2:1b",          "size": "1.3GB",  "cat": "General",   "desc": "Meta Llama 3.2, tiny"},
    {"name": "llama3.2:3b",          "size": "2.0GB",  "cat": "General",   "desc": "Meta Llama 3.2, small"},
    {"name": "llama3.1:8b",          "size": "4.7GB",  "cat": "General",   "desc": "Meta Llama 3.1, strong"},
    {"name": "llama3.3:70b",         "size": "43GB",   "cat": "General",   "desc": "Meta Llama 3.3, flagship, needs 64GB+"},
    {"name": "gemma3:1b",            "size": "0.8GB",  "cat": "General",   "desc": "Google Gemma 3, ultra-light"},
    {"name": "gemma3:4b",            "size": "2.5GB",  "cat": "General",   "desc": "Google Gemma 3, efficient"},
    {"name": "gemma3:12b",           "size": "7.5GB",  "cat": "General",   "desc": "Google Gemma 3, high quality"},
    {"name": "gemma3:27b",           "size": "16GB",   "cat": "General",   "desc": "Google Gemma 3, premium, needs 24GB+"},
    {"name": "gemma4:2b",            "size": "1.5GB",  "cat": "General",   "desc": "Google Gemma 4, latest generation, tiny"},
    {"name": "gemma4:4b",            "size": "3.0GB",  "cat": "General",   "desc": "Google Gemma 4, latest, frontier at size"},
    {"name": "gemma4:26b",           "size": "16GB",   "cat": "General",   "desc": "Google Gemma 4, high quality, needs 24GB+"},
    {"name": "gemma4:31b",           "size": "20GB",   "cat": "General",   "desc": "Google Gemma 4, flagship local, needs 32GB+"},
    {"name": "mistral:7b",           "size": "4.1GB",  "cat": "General",   "desc": "Mistral 7B, fast and capable"},
    {"name": "mistral-nemo:latest",  "size": "7.1GB",  "cat": "General",   "desc": "Mistral Nemo 12B, Apache 2.0"},
    {"name": "phi4:latest",          "size": "9.1GB",  "cat": "General",   "desc": "Microsoft Phi-4 14B, strong reasoning"},
    {"name": "phi4-mini:latest",     "size": "2.5GB",  "cat": "General",   "desc": "Microsoft Phi-4 Mini 3.8B, efficient"},
    {"name": "phi3.5:latest",           "size": "2.2GB",  "cat": "General",   "desc": "Microsoft Phi-3.5 3.8B, strong reasoning"},
    {"name": "phi3.5:3.8b",            "size": "2.2GB",  "cat": "General",   "desc": "Microsoft Phi-3.5, compact, fast"},
    {"name": "glm4:latest",            "size": "5.5GB",  "cat": "General",   "desc": "Zhipu GLM-4 9B, strong multilingual"},
    {"name": "glm4:9b",                "size": "5.5GB",  "cat": "General",   "desc": "Zhipu GLM-4, competitive with Llama 3"},
    {"name": "glm-4.7-flash:latest",   "size": "18GB",   "cat": "General",   "desc": "Zhipu GLM-4.7 Flash, top 30B class model, needs 24GB+"},
    {"name": "glm-4.7:cloud",          "size": "☁",      "cat": "General",   "desc": "Zhipu GLM-4.7, advanced coding & reasoning — cloud inference"},
    {"name": "glm-4.6:cloud",          "size": "☁",      "cat": "General",   "desc": "Zhipu GLM-4.6, agentic reasoning and coding — cloud inference"},
    {"name": "mistral-small3.1:latest","size": "15GB",   "cat": "General",   "desc": "Mistral Small 3.1 24B, vision + function calling, needs 24GB+"},
    {"name": "mistral-small3.2:latest","size": "15GB",   "cat": "General",   "desc": "Mistral Small 3.2 24B, improved function calling, needs 24GB+"},
    {"name": "mistral-large-3:cloud",  "size": "☁",      "cat": "General",   "desc": "Mistral Large 3, 675B MoE, production-grade multimodal — cloud"},
    {"name": "ministral-3:3b",         "size": "2.0GB",  "cat": "General",   "desc": "Ministral 3B, edge deployment, ultra-fast"},
    {"name": "ministral-3:8b",         "size": "5.0GB",  "cat": "General",   "desc": "Ministral 8B, edge deployment, strong"},
    {"name": "ministral-3:14b",        "size": "9.0GB",  "cat": "General",   "desc": "Ministral 14B, best edge model, needs 16GB+"},
    {"name": "olmo-3:7b",              "size": "4.7GB",  "cat": "General",   "desc": "AllenAI OLMo-3 7B, fully open scientific LLM"},
    {"name": "olmo-3:32b",             "size": "20GB",   "cat": "General",   "desc": "AllenAI OLMo-3 32B, open research flagship, needs 32GB+"},
    {"name": "olmo-3.1:32b",           "size": "20GB",   "cat": "General",   "desc": "AllenAI OLMo-3.1 32B, updated open research model, needs 32GB+"},
    {"name": "nemotron-3-nano:4b",     "size": "2.5GB",  "cat": "General",   "desc": "NVIDIA Nemotron-3 Nano 4B, agentic, efficient"},
    {"name": "nemotron-3-nano:30b",    "size": "18GB",   "cat": "General",   "desc": "NVIDIA Nemotron-3 Nano 30B, agentic model, needs 24GB+"},
    {"name": "granite4:350m",          "size": "0.2GB",  "cat": "General",   "desc": "IBM Granite 4 350M, ultra-light tool-calling"},
    {"name": "granite4:1b",            "size": "0.6GB",  "cat": "General",   "desc": "IBM Granite 4 1B, light tool-calling"},
    {"name": "granite4:3b",            "size": "2.0GB",  "cat": "General",   "desc": "IBM Granite 4 3B, instruction following & tools"},
    {"name": "tinyllama:latest",       "size": "0.6GB",  "cat": "General",   "desc": "Tiny general purpose"},
    # --- Reasoning ---
    {"name": "deepseek-r1:1.5b",     "size": "1.1GB",  "cat": "Reasoning", "desc": "DeepSeek R1, reasoning light"},
    {"name": "deepseek-r1:7b",       "size": "4.7GB",  "cat": "Reasoning", "desc": "DeepSeek R1, deep reasoning"},
    {"name": "deepseek-r1:14b",      "size": "9.0GB",  "cat": "Reasoning", "desc": "DeepSeek R1, needs 16GB+"},
    {"name": "deepseek-r1:32b",      "size": "20GB",   "cat": "Reasoning", "desc": "DeepSeek R1, needs 32GB+"},
    {"name": "deepseek-r1:70b",      "size": "43GB",   "cat": "Reasoning", "desc": "DeepSeek R1, needs 64GB+"},
    {"name": "qwq:32b",              "size": "20GB",   "cat": "Reasoning", "desc": "QwQ-32B, strong reasoning, needs 32GB+"},
    {"name": "marco-o1:latest",      "size": "4.7GB",  "cat": "Reasoning", "desc": "Marco-o1 7B, open reasoning model"},
    {"name": "nemotron:latest",           "size": "40GB",   "cat": "Reasoning", "desc": "NVIDIA Nemotron-70B, top RLHF quality, needs 64GB+"},
    {"name": "nemotron:70b",              "size": "40GB",   "cat": "Reasoning", "desc": "NVIDIA Llama-3.1-Nemotron-70B, RLHF tuned"},
    {"name": "nemotron-mini:latest",      "size": "2.5GB",  "cat": "Reasoning", "desc": "NVIDIA Nemotron-Mini 4B, efficient, commercial-friendly"},
    {"name": "nemotron-cascade-2:30b",    "size": "18GB",   "cat": "Reasoning", "desc": "NVIDIA Nemotron-Cascade-2 30B MoE, 3B active, needs 24GB+"},
    {"name": "nemotron-3-super:120b",     "size": "70GB",   "cat": "Reasoning", "desc": "NVIDIA Nemotron-3 Super 120B MoE, 12B active, needs 80GB+"},
    {"name": "nemotron-3-super:cloud",    "size": "☁",      "cat": "Reasoning", "desc": "NVIDIA Nemotron-3 Super, cloud inference"},
    {"name": "lfm2:latest",               "size": "15GB",   "cat": "Reasoning", "desc": "Liquid AI LFM2 24B hybrid, on-device optimized, needs 24GB+"},
    {"name": "lfm2:24b",                  "size": "15GB",   "cat": "Reasoning", "desc": "Liquid Foundation Model 2, hybrid architecture"},
    {"name": "lfm2.5-thinking:latest",    "size": "0.8GB",  "cat": "Reasoning", "desc": "Liquid LFM2.5 Thinking 1.2B, hybrid on-device thinking model"},
    {"name": "phi4-reasoning:latest",     "size": "9.0GB",  "cat": "Reasoning", "desc": "Microsoft Phi-4 Reasoning 14B, strong chain-of-thought"},
    {"name": "phi4-mini-reasoning:latest","size": "2.5GB",  "cat": "Reasoning", "desc": "Microsoft Phi-4 Mini Reasoning 3.8B, efficient CoT"},
    {"name": "qwen3-next:80b",            "size": "48GB",   "cat": "Reasoning", "desc": "Qwen3-Next 80B, strong reasoning, needs 64GB+"},
    {"name": "glm-5:cloud",               "size": "☁",      "cat": "Reasoning", "desc": "Z.ai GLM-5 744B MoE, 40B active, top reasoning — cloud"},
    {"name": "deepseek-v3.2:cloud",       "size": "☁",      "cat": "Reasoning", "desc": "DeepSeek V3.2, high efficiency + superior intelligence — cloud"},
    {"name": "kimi-k2-thinking:cloud",    "size": "☁",      "cat": "Reasoning", "desc": "Kimi K2 Thinking, Moonshot AI best open-source thinking — cloud"},
    {"name": "kimi-k2.5:cloud",           "size": "☁",      "cat": "Reasoning", "desc": "Kimi K2.5, native multimodal agentic model — cloud"},
    {"name": "kimi-k2:1t-cloud",          "size": "☁",      "cat": "Reasoning", "desc": "Kimi K2, 1T param MoE, state-of-the-art — cloud only"},
    # --- Code ---
    {"name": "qwen2.5-coder:1.5b",   "size": "1.0GB",  "cat": "Code",      "desc": "Code generation, light"},
    {"name": "qwen2.5-coder:7b",     "size": "4.4GB",  "cat": "Code",      "desc": "Code generation, strong"},
    {"name": "qwen2.5-coder:14b",    "size": "9.0GB",  "cat": "Code",      "desc": "Code generation, needs 16GB+"},
    {"name": "qwen2.5-coder:32b",    "size": "20GB",   "cat": "Code",      "desc": "Best code model, needs 32GB+"},
    {"name": "gpt-oss:20b",               "size": "12GB",   "cat": "Code",      "desc": "OpenAI open-weight 20B, reasoning & agentic tasks"},
    {"name": "gpt-oss:120b",              "size": "70GB",   "cat": "Code",      "desc": "OpenAI open-weight 120B, powerful, needs 80GB+"},
    {"name": "gpt-oss-safeguard:20b",     "size": "12GB",   "cat": "Code",      "desc": "OpenAI safety reasoning 20B, built on gpt-oss"},
    {"name": "gpt-oss-safeguard:120b",    "size": "70GB",   "cat": "Code",      "desc": "OpenAI safety reasoning 120B, needs 80GB+"},
    {"name": "qwen3-coder-next:latest",   "size": "5.0GB",  "cat": "Code",      "desc": "Qwen3 Coder Next, coding-focused, latest generation"},
    {"name": "devstral:latest",           "size": "14GB",   "cat": "Code",      "desc": "Mistral DevStral, agentic coding, needs 24GB+"},
    {"name": "devstral-small-2:24b",      "size": "15GB",   "cat": "Code",      "desc": "Mistral DevStral Small 2 24B, multi-file codebase editing"},
    {"name": "devstral-2:123b",           "size": "75GB",   "cat": "Code",      "desc": "Mistral DevStral 2 123B, best agentic coder, needs 80GB+"},
    {"name": "minimax-m2:cloud",          "size": "☁",      "cat": "Code",      "desc": "MiniMax M2, high-efficiency coding & agentic — cloud"},
    {"name": "minimax-m2.1:cloud",        "size": "☁",      "cat": "Code",      "desc": "MiniMax M2.1, multilingual code engineering — cloud"},
    {"name": "minimax-m2.5:cloud",        "size": "☁",      "cat": "Code",      "desc": "MiniMax M2.5, real-world agentic workflows — cloud"},
    {"name": "minimax-m2.7:cloud",        "size": "☁",      "cat": "Code",      "desc": "MiniMax M2.7, coding & professional tasks — cloud"},
    {"name": "codellama:7b",         "size": "3.8GB",  "cat": "Code",      "desc": "Meta code model"},
    {"name": "starcoder2:3b",        "size": "1.7GB",  "cat": "Code",      "desc": "BigCode, multi-language"},
    {"name": "starcoder2:7b",        "size": "4.0GB",  "cat": "Code",      "desc": "BigCode, strong"},
    # --- Vision (multimodal) ---
    {"name": "qwen3-vl:2b",             "size": "1.5GB",  "cat": "Vision",    "desc": "Qwen3-VL 2B, most powerful vision-language in Qwen family"},
    {"name": "qwen3-vl:4b",             "size": "2.5GB",  "cat": "Vision",    "desc": "Qwen3-VL 4B, strong vision understanding"},
    {"name": "qwen3-vl:8b",             "size": "5.0GB",  "cat": "Vision",    "desc": "Qwen3-VL 8B, high quality vision-language"},
    {"name": "qwen3-vl:30b",            "size": "18GB",   "cat": "Vision",    "desc": "Qwen3-VL 30B, premium vision model, needs 24GB+"},
    {"name": "qwen3-vl:32b",            "size": "20GB",   "cat": "Vision",    "desc": "Qwen3-VL 32B, top open vision model, needs 32GB+"},
    {"name": "glm-ocr:latest",          "size": "5.5GB",  "cat": "Vision",    "desc": "Zhipu GLM-OCR, complex document understanding & OCR"},
    {"name": "deepseek-ocr:3b",         "size": "2.0GB",  "cat": "Vision",    "desc": "DeepSeek OCR 3B, token-efficient vision OCR"},
    {"name": "gemini-3-flash-preview:cloud", "size": "☁", "cat": "Vision",    "desc": "Google Gemini 3 Flash, frontier speed + multimodal — cloud"},
    {"name": "qwen3.5:0.8b",        "size": "0.5GB",  "cat": "Vision",    "desc": "Qwen3.5 multimodal, ultra-light"},
    {"name": "qwen3.5:2b",          "size": "1.4GB",  "cat": "Vision",    "desc": "Qwen3.5 multimodal, small"},
    {"name": "qwen3.5:4b",          "size": "2.5GB",  "cat": "Vision",    "desc": "Qwen3.5 multimodal, efficient"},
    {"name": "qwen3.5:9b",          "size": "5.5GB",  "cat": "Vision",    "desc": "Qwen3.5 multimodal, strong"},
    {"name": "qwen3.5:27b",         "size": "16GB",   "cat": "Vision",    "desc": "Qwen3.5 multimodal, high quality, needs 24GB+"},
    {"name": "qwen3.5:35b",         "size": "21GB",   "cat": "Vision",    "desc": "Qwen3.5 multimodal, premium, needs 32GB+"},
    {"name": "llama4:scout",        "size": "11GB",   "cat": "Vision",    "desc": "Meta Llama4 Scout 16x17B MoE, multimodal, needs 16GB+"},
    {"name": "llama4:maverick",     "size": "80GB",   "cat": "Vision",    "desc": "Meta Llama4 Maverick 128x17B MoE, needs 80GB+"},
    {"name": "llava:7b",            "size": "4.7GB",  "cat": "Vision",    "desc": "Image understanding"},
    {"name": "llava:13b",           "size": "8.0GB",  "cat": "Vision",    "desc": "Image understanding, needs 16GB+"},
    {"name": "llava-llama3:latest", "size": "5.5GB",  "cat": "Vision",    "desc": "LLaVA on Llama3, improved quality"},
    {"name": "llama3.2-vision:11b", "size": "7.9GB",  "cat": "Vision",    "desc": "Meta multimodal, strong vision"},
    {"name": "moondream:latest",    "size": "1.7GB",  "cat": "Vision",    "desc": "Tiny vision model, 1.8B params"},
    # --- Embedding ---
    {"name": "nomic-embed-text:latest",   "size": "0.3GB", "cat": "Embedding", "desc": "Text embeddings, 768 dim"},
    {"name": "mxbai-embed-large:latest",  "size": "0.7GB", "cat": "Embedding", "desc": "Text embeddings, 1024 dim"},
    {"name": "all-minilm:latest",         "size": "0.1GB", "cat": "Embedding", "desc": "Sentence embeddings, 384 dim, ultra-fast"},
    {"name": "bge-m3:latest",             "size": "1.2GB", "cat": "Embedding", "desc": "BGE-M3, multilingual, best quality"},
]


class OllamaProvider(LLMProvider):
    """Ollama local model provider."""

    def __init__(self, base_url: str = "http://agent-ollama:11434", default_model: str = "qwen2.5:1.5b"):
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._available_models: list[str] = []
        self._loaded_model: str = ""
        self._model_info: dict[str, dict] = {}  # name → {param_size, size_bytes}

    def provider_name(self) -> str:
        return "ollama"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    self._model_info = {
                        m["name"]: {
                            "param_size": m.get("details", {}).get("parameter_size", ""),
                            "size_bytes": m.get("size", 0),
                        }
                        for m in data.get("models", [])
                    }
                    self._available_models = list(self._model_info.keys())
                    return True
        except Exception as e:
            logger.debug("ollama.health_check.failed", error=str(e))
        return False

    def available_models(self) -> list[str]:
        return self._available_models

    def supports_vision(self, model: str = "") -> bool:
        m = (model or self.default_model).lower()
        return any(kw in m for kw in _OLLAMA_VISION_KEYWORDS)

    def model_sizes(self) -> dict[str, str]:
        """Return {model_name: human_readable_size} for installed models."""
        result = {}
        for name, info in self._model_info.items():
            param = info.get("param_size", "")
            if param:
                result[name] = param
            else:
                # Format bytes to human-readable
                size_bytes = info.get("size_bytes", 0)
                if size_bytes >= 1_073_741_824:
                    result[name] = f"{size_bytes / 1_073_741_824:.1f}GB"
                elif size_bytes >= 1_048_576:
                    result[name] = f"{size_bytes / 1_048_576:.0f}MB"
                else:
                    result[name] = ""
        return result

    async def unload_model(self, model_name: str):
        """Unload a model from RAM by setting keep_alive to 0."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model_name, "keep_alive": 0},
                )
            logger.info("ollama.model_unloaded", model=model_name)
        except Exception as e:
            logger.debug("ollama.unload_failed", model=model_name, error=str(e))

    async def load_model(self, model_name: str) -> bool:
        """Pre-load a model into RAM. Returns True if successful."""
        try:
            # First unload any loaded model to free RAM
            if self._loaded_model and self._loaded_model != model_name:
                await self.unload_model(self._loaded_model)

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model_name, "keep_alive": "10m"},
                )
                if resp.status_code == 200:
                    self._loaded_model = model_name
                    logger.info("ollama.model_loaded", model=model_name)
                    return True
                else:
                    body = resp.text
                    logger.error("ollama.load_failed", model=model_name, status=resp.status_code, body=body[:200])
                    return False
        except Exception as e:
            logger.error("ollama.load_failed", model=model_name, error=str(e))
            return False

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self.default_model
        start = time.monotonic()

        # Auto-load model if different from currently loaded
        if model != self._loaded_model:
            loaded = await self.load_model(model)
            if not loaded:
                raise RuntimeError(f"Failed to load model '{model}'. It may need more RAM than available.")

        messages = []
        for i, m_obj in enumerate(request.messages):
            msg: dict = {"role": m_obj.role, "content": m_obj.content}
            if (
                m_obj.role == "user"
                and request.image_path
                and i == len(request.messages) - 1
                and self.supports_vision(model)
            ):
                try:
                    safe_path = validate_media_path(request.image_path)
                    with open(safe_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode()
                    msg["images"] = [img_b64]
                except Exception as e:
                    logger.warning("ollama.image_inject_failed", error=str(e))
            messages.append(msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = int((time.monotonic() - start) * 1000)
        content = data.get("message", {}).get("content", "")

        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        logger.info(
            "ollama.generated",
            model=model,
            latency_ms=latency_ms,
            tokens=prompt_tokens + completion_tokens,
        )

        return ModelResponse(
            content=content,
            model_used=model,
            provider="ollama",
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            latency_ms=latency_ms,
        )

    async def pull_model(self, model_name: str) -> str:
        """Download a model. Returns status message."""
        logger.info("ollama.pull.starting", model=model_name)

        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "unknown")
        logger.info("ollama.pull.complete", model=model_name, status=status)

        await self.health_check()
        return status

    async def delete_model(self, model_name: str) -> bool:
        """Delete a downloaded model to free disk space."""
        try:
            # Unload from RAM first
            await self.unload_model(model_name)

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    "DELETE",
                    f"{self.base_url}/api/delete",
                    json={"name": model_name},
                )
                resp.raise_for_status()
            logger.info("ollama.delete.complete", model=model_name)
            await self.health_check()
            return True
        except Exception as e:
            logger.error("ollama.delete.failed", model=model_name, error=str(e))
            return False

    def get_catalog(self) -> list[dict]:
        """Return the curated catalog of downloadable models."""
        return OLLAMA_CATALOG
