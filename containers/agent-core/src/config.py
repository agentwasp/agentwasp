from zoneinfo import ZoneInfo

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://agent-redis:6379/0"
    database_url: str = ""
    ollama_base_url: str = "http://agent-ollama:11434"
    timezone: str = "America/Santiago"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    # Phase 3 — Additional AI providers (all OpenAI-compatible)
    mistral_api_key: str = ""
    deepseek_api_key: str = ""
    openrouter_api_key: str = ""
    perplexity_api_key: str = ""
    huggingface_api_key: str = ""
    lmstudio_base_url: str = ""  # e.g. "http://localhost:1234/v1"; empty = disabled
    moonshot_api_key: str = ""   # Kimi / Moonshot AI (moonshot-v1-128k, 32k, 8k)
    gmail_address: str = ""
    gmail_app_password: str = ""
    log_level: str = "INFO"

    # Skills
    skills_enabled: bool = True
    skills_max_rounds: int = 3

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_health_check_interval: int = 300
    scheduler_reflection_interval: int = 21600
    scheduler_memory_cleanup_interval: int = 86400
    scheduler_snapshot_interval: int = 86400
    scheduler_notify_chat_id: str = ""
    scheduler_proactive_interval: int = 3600  # 1 hour
    proactive_quiet_start: int = 23  # 11 PM local
    proactive_quiet_end: int = 8  # 8 AM local
    proactive_max_daily: int = 6

    # Dashboard
    dashboard_enabled: bool = True
    dashboard_port: int = 8080
    dashboard_host: str = "0.0.0.0"
    dashboard_secret: str = ""
    media_signing_secret: str = ""
    media_signing_debug: bool = False  # Must be True explicitly for dev/transition mode

    @model_validator(mode="after")
    def validate_media_signing(self) -> "Settings":
        _default = "wasp-media-default-secret-change-me"
        if not self.media_signing_debug:
            if not self.media_signing_secret or self.media_signing_secret == _default:
                raise ValueError(
                    "MEDIA_SIGNING_SECRET must be set to a strong secret when "
                    "MEDIA_SIGNING_DEBUG is False. "
                    "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
                )
            if len(self.media_signing_secret) < 32:
                raise ValueError(
                    "MEDIA_SIGNING_SECRET must be at least 32 characters in production."
                )
        elif not self.media_signing_secret:
            # Debug mode: use default insecure secret so code never sees empty string
            self.media_signing_secret = _default
        return self

    @field_validator("dashboard_secret")
    @classmethod
    def validate_dashboard_secret(cls, v: str) -> str:
        if v and len(v) < 16:
            raise ValueError("DASHBOARD_SECRET must be at least 16 characters")
        return v

    # Goal Engine
    goal_engine_enabled: bool = True
    goal_tick_interval: int = 15  # seconds between ticks
    goal_max_concurrent: int = 3  # max goals processed per tick
    goal_default_max_steps: int = 50
    goal_default_max_runtime: int = 3600  # 1 hour
    # Goal Engine — Advanced control layer
    goal_budget_max_tokens_planning: int = 4000
    goal_budget_max_tokens_execution: int = 20000
    goal_budget_max_replans: int = 3
    goal_budget_max_memory_bytes: int = 1_048_576  # 1 MiB
    goal_default_autonomy_mode: str = "full"  # assist | semi | full
    goal_meta_reflection_interval: int = 300  # 5 minutes
    goal_cpu_backpressure_threshold: float = 85.0

    # Integrations platform
    integrations_enabled: bool = True
    integrations_policy_mode: str = "semi"  # assist | semi | full
    integrations_cb_failure_threshold: int = 5
    integrations_cb_recovery_timeout: float = 60.0

    # Sovereign Mode — operator-focused master switch
    # When True: autonomy=full, warn-only risk, max skill rounds raised, budgets doubled
    sovereign_mode: bool = False

    # Multi-Agent Orchestration
    agents_enabled: bool = True
    agents_max_active: int = 10
    agents_max_concurrent_steps: int = 5
    agents_cpu_threshold: float = 85.0
    agents_global_token_budget_per_minute: int = 100_000
    agents_tick_interval: int = 15

    # Redis stream names
    stream_incoming: str = "events:incoming"
    stream_outgoing: str = "events:outgoing"
    consumer_group: str = "agent-core-group"
    consumer_name: str = "core-1"

    # ── Next-Gen Cognitive Systems ─────────────────────────────────────────
    # System 1: Vector Semantic Memory
    # Safe fallback: if Ollama unavailable, hash-based pseudo-embedding is used.
    # Never crashes — all failures return empty results silently.
    vector_memory_enabled: bool = True   # enabled by default with safe fallback
    vector_top_k: int = 8
    vector_embed_model: str = "nomic-embed-text"
    # Pluggable embedding provider: "ollama" | "openai" | "hash"
    # "ollama" uses OLLAMA_BASE_URL + vector_embed_model (default)
    # "openai" uses OPENAI_API_KEY + vector_embed_model (e.g. text-embedding-3-small)
    # "hash"   deterministic fallback, always available, non-semantic
    embedding_provider: str = "ollama"

    # Memory backend strategy:
    # - internal: AgentWasp filesystem/Postgres/Redis memory only
    # - supermemory: Supermemory-only conversational memory/context path
    # - tandem: bounded Supermemory profile/search plus existing internal memory
    memory_backend: str = "tandem"

    # Supermemory backend — works with hosted API or local self-hosted server.
    # Keep rerank/rewrite disabled by default to protect chat latency and token cost.
    supermemory_api_key: str = ""
    supermemory_base_url: str = "https://api.supermemory.ai"
    supermemory_container_tag: str = "agentwasp"
    supermemory_scope: str = "chat"  # chat | project | global
    supermemory_timeout_seconds: float = 1.5
    supermemory_context_budget_chars: int = 1800
    supermemory_search_limit: int = 3
    supermemory_search_threshold: float = 0.35
    supermemory_rerank: bool = False
    supermemory_rewrite_query: bool = False
    supermemory_ingest_enabled: bool = True
    supermemory_strict: bool = False

    # Memory Ranking System — composite relevance scoring before injection
    # score = 0.5 * similarity + 0.3 * recency + 0.2 * importance
    memory_ranking_enabled: bool = True
    memory_episodic_max: int = 3       # max episodic memories injected
    memory_semantic_max: int = 5       # max semantic/vector memories injected
    memory_procedural_max: int = 3     # max procedural memories injected
    memory_goal_max: int = 5           # max goal-specific memories injected
    memory_recency_half_life_hours: float = 24.0  # recency decay half-life

    # Resource Governor — prevents runaway task/goal/agent creation
    governor_enabled: bool = True
    governor_max_goals_per_user: int = 10
    governor_max_agents_per_user: int = 5
    governor_max_tasks_per_hour: int = 50
    governor_max_llm_calls_per_minute: int = 30
    governor_max_api_calls_per_minute: int = 60

    # System 2: Dual-Layer Planner (Planner + Critic)
    # A second LLM pass validates the generated TaskGraph before execution.
    plan_critic_enabled: bool = True
    plan_critic_max_tokens: int = 1200

    # System 3: Meta-Agent Supervisor
    # Enables complex goal decomposition into coordinated agent teams.
    meta_agent_enabled: bool = False
    meta_agent_max_team_size: int = 5

    # System 4: World Model
    # Structured world-state tracking using existing temporal + KG data.
    world_model_enabled: bool = True

    # System 5: Skill Evolution Engine
    # Automatically synthesises composite skills from recurring patterns.
    skill_evolution_enabled: bool = True
    skill_pattern_threshold: int = 5  # minimum occurrences before synthesis

    # System 6: Episodic Temporal Reasoning
    # Generates [TEMPORAL INSIGHTS] blocks for the LLM context.
    temporal_reasoning_enabled: bool = True
    temporal_reasoning_max_insights: int = 5


settings = Settings()


def get_tz() -> ZoneInfo:
    """Return configured timezone as ZoneInfo."""
    return ZoneInfo(settings.timezone)


def now_local():
    """Return current datetime in configured timezone."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone(get_tz())
