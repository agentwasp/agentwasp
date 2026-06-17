"""Secret Redaction — automatically scrubs API keys and secrets from logs.

Applied to all text before it is written to audit_log or any observability sink.
Covers known API key formats for all supported providers.
"""
from __future__ import annotations

import re

# Each tuple: (pattern, replacement_label)
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # OpenAI — sk-proj-... (new format) and sk-... (classic)
    (re.compile(r'\bsk-proj-[A-Za-z0-9_-]{20,}\b'), 'sk-proj-***REDACTED***'),
    (re.compile(r'\bsk-[A-Za-z0-9]{20,}\b'), 'sk-***REDACTED***'),
    # Anthropic — sk-ant-api03-...
    (re.compile(r'\bsk-ant-[A-Za-z0-9_-]{20,}\b'), 'sk-ant-***REDACTED***'),
    # Google AI / Gemini — AIza... (real keys are AIza + 33-39 alphanumeric chars)
    (re.compile(r'\bAIza[A-Za-z0-9_-]{25,}\b'), 'AIza***REDACTED***'),
    # xAI / Grok
    (re.compile(r'\bxai-[A-Za-z0-9_-]{20,}\b'), 'xai-***REDACTED***'),
    # Moonshot / Kimi
    (re.compile(r'\bsk-[A-Za-z0-9]{40,}\b'), 'sk-***REDACTED***'),
    # Supermemory API keys
    (re.compile(r'\bsm_[A-Za-z0-9_-]{20,}\b'), 'sm_***REDACTED***'),
    # HuggingFace — hf_...
    (re.compile(r'\bhf_[A-Za-z0-9]{20,}\b'), 'hf_***REDACTED***'),
    # Generic Bearer tokens in HTTP headers/text
    (re.compile(r'(?i)Bearer\s+[A-Za-z0-9._\-]{20,}'), 'Bearer ***REDACTED***'),
    # Authorization header values
    (re.compile(r'(?i)(?:Authorization|api[-_]?key|apikey|api[-_]?token|access[-_]?token)["\s:=]+[A-Za-z0-9._\-]{20,}'),
     'Authorization: ***REDACTED***'),
    # Passwords in key=value pairs (common in CLI output / config)
    (re.compile(r'(?i)(?:password|passwd|pwd|secret)["\s:=]+\S{8,}'), 'password=***REDACTED***'),
    # Generic long random-looking strings that appear after "key" keyword
    (re.compile(r'(?i)\b(?:key|token|secret)["\s:=]+[A-Za-z0-9+/=_\-]{32,}\b'), 'key=***REDACTED***'),
    # AWS access key IDs (AKIA...) — standard format is AKIA + 16 uppercase alphanumeric
    (re.compile(r'\bAKIA[A-Z0-9]{12,}\b'), 'AKIA***REDACTED***'),
    (re.compile(r'(?i)aws[_\-]?secret[_\-]?(?:access[_\-]?)?key["\s:=]+[A-Za-z0-9+/]{40}\b'), 'aws_secret=***REDACTED***'),
    # Stripe keys
    (re.compile(r'\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{24,}\b'), 'stripe_***REDACTED***'),
    # Slack bot/user tokens
    (re.compile(r'\bxox[bposa]-[A-Za-z0-9\-]{10,}\b'), 'xox***REDACTED***'),
    # SendGrid API keys
    (re.compile(r'\bSG\.[A-Za-z0-9_\-]{22,}\.[A-Za-z0-9_\-]{43,}\b'), 'SG.***REDACTED***'),
]

# Minimum text length to bother scanning (avoids overhead on very short strings)
_MIN_LEN = 10


def redact(text: str) -> str:
    """Scrub known secret patterns from text. Returns sanitized string."""
    if not text or len(text) < _MIN_LEN:
        return text
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_dict(data: dict, keys: list[str] | None = None) -> dict:
    """Redact secrets from string values in a dict. Optionally target specific keys."""
    result = {}
    for k, v in data.items():
        if isinstance(v, str):
            if keys is None or k in keys:
                result[k] = redact(v)
            else:
                result[k] = v
        elif isinstance(v, dict):
            result[k] = redact_dict(v, keys)
        else:
            result[k] = v
    return result
