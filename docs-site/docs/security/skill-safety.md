---
id: skill-safety
title: Skill Safety
description: Capability levels, intent gating, action announcer, response guard.
---

# Skill Safety

The Policy Layer is the operator's contract with the agent: it bounds what the agent can claim, what it can do, and how it must report what it did. This page documents the four enforcement points before output reaches the user.

## Principles

1. **Explicit intent for side effects.** The agent does not infer "you probably want me to send an email" from a status question.
2. **Honest narration.** The response cannot claim an action that did not actually run.
3. **Grounded facts.** Verdicts about external state (delivered, in transit, price is X, status is Y) require supporting skill output.
4. **Schedule honesty.** `task_manager` only does interval scheduling; clock-time and daypart requests must be disclosed, not silently reinterpreted.
5. **Forensic traceability.** Every response emits a `DecisionTrace`. Every CONTROLLED+ skill writes to the AuditLog.

## Capability levels

| Level | Logged | Confirmation in SEMI mode | Examples |
|-------|--------|---------------------------|----------|
| SAFE | No | No | `calculate`, `datetime_skill`, `system_info` |
| MONITORED | No | No | `web_search`, `fetch_url`, `browser` (read-only) |
| CONTROLLED | Yes | No | `gmail`, `reminders`, `task_manager` |
| RESTRICTED | Yes | Yes | `shell`, `python_exec`, `http_request` |
| PRIVILEGED | Yes | Yes | `self_improve`, broker-mediated docker commands |

`SkillRegistry._CAPABILITY_MAP` maps every built-in skill to a level. Default for unmapped is CONTROLLED. Custom Python skills declare their level in their class.

## The four enforcement points

```
LLM candidate response
        │
        ▼
1. Intent Gate         ─ blocks side-effect skills without explicit intent
        │
        ▼
2. Action Announcer    ─ strips unverified action claims, surfaces failures
        │
        ▼
3. Response Guard      ─ schedule honesty + factual grounding + sanitizer
        │
        ▼
4. Response Validator  ─ deterministic grounding/incomplete/drift check
        │
        ▼
Outgoing response
```

All four layers run in deterministic Python code. None of them call the LLM (Response Validator may trigger one corrective LLM round, but the check itself is regex/string matching). This is a hard architectural choice — the policy layer must not depend on the same model that produced the candidate.

## 1. Intent Gate

`src/policy/intent_gate.py`

Side-effect skills are gated:

```python
SIDE_EFFECT_SKILLS = {"gmail", "agent_manager", "task_manager"}
```

Each gated skill has an intent regex. The gate runs after the LLM produces a `<skill>` call but before the skill executes. If the user message does not match the regex, the call is dropped and the response gets a corrective system message.

| Skill | Required intent (examples) |
|-------|----------------------------|
| `gmail` (send) | Verb-object phrases that explicitly mean "send email" + a clear recipient or content reference |
| `agent_manager` (create) | Phrases that explicitly mean "create an agent / sub-agent / bot" |
| `task_manager` (create) | Recurring keywords: *"every"*, *"daily"*, *"hourly"*, etc. |

The gate also detects placeholder content via `_PLACEHOLDER_SUBJECTS` and `_PLACEHOLDER_BODIES`. An email send call with a placeholder subject or body is blocked even if intent is present, unless the user message itself supplies the content.

`filter_inferred_side_effects()` applies the gate to a list of skill calls and returns `(allowed, dropped)`. Drops are recorded in the DecisionTrace.

## 2. Action Announcer

`src/policy/action_announcer.py`

After execution, the announcer compares the response text to actual skill outcomes. Three rules:

1. **`strip_unverified_claims`** — if the response says "I sent the email" but no `gmail.send` skill ran successfully, the claim is removed.
2. **`strip_contradicting_failures`** — if the response says "task created" but `task_manager.create` returned an error, the success claim is removed and the failure surfaced.
3. **`render_actions_block`** — appends a structured `Actions:` block listing what actually happened.

The announcer covers three action families: `email_send`, `task_create`, `agent_create`. Verb patterns are multilingual; failure keywords cover common error markers.

## 3. Response Guard

`src/policy/response_guard.py`

Three sub-checks run in order:

### `enforce_schedule_honesty`

`task_manager` only supports interval scheduling. The guard handles two directions of dishonesty:

| Direction | Trigger | Action |
|-----------|---------|--------|
| Agent-side | Response asserts a clock time in scheduling context | Strip the time claim |
| User-side (clock) | User requested a specific time AND a real task was created | Append disclaimer that `task_manager` only supports intervals |
| User-side (daypart) | User requested a daypart phrase AND a real task was created | Append disclaimer |

Trace fields: `applied`, `claimed_time`, `had_real_create`, `origin in {"user_text", "user_text_daypart"}`.

### `enforce_factual_grounding`

Replaces fabricated verdicts (delivered, in transit, out for delivery, pending, etc.) with an honest fallback when no skill output supports them.

Two-stage check:

1. **`_response_makes_status_claim`** — does the response use a verdict keyword in a scheduling context?
2. **`_skill_output_supports_verdict`** — does any successful skill output contain that verdict word *within 200 characters of a user-named entity*?

`_user_named_entities` extracts entity codes via `_USER_ENTITY_RE`:

```
[A-Z]{2}\d{9}[A-Z]{2}     # postal/courier 11-char alphanumeric
1Z[A-Z0-9]{16}            # UPS
\d{12,22}                 # generic long numeric (FedEx)
[A-Z]{4,6}\d{6,10}        # alphanumeric mix
```

If a verdict keyword appears in skill output but never within 200 chars of any user-named entity, it is **not** evidence — the response is replaced with the language-localized fallback.

### `sanitize_markdown`

Telegram does not render markdown by default in agent output paths, so raw markdown leaks visibly. The sanitizer strips:

| Pattern | Action |
|---------|--------|
| `![alt](url)` | Removed |
| `[text](url)` | Collapsed to `text (url)` (negative lookbehind `(?<!!)` keeps image syntax separate) |
| `**bold**` / `__bold__` | Inner text kept |
| `` `code` `` (inline) | Inner text kept |
| `# Header` lines | `#` prefix stripped, title kept |
| `---` / `***` (horizontal rules) | Removed |

## 4. Response Validator

`src/validation/response_validator.py`

After the guard chain, the validator performs deterministic post-LLM checks. None of them call the LLM. Each check returns `(passed, reason, should_retry)`:

| Check | Trigger |
|-------|---------|
| `grounding_fail` | External-data query but no skill produced verified data |
| `incomplete` | Trace shows skill execution started but did not complete |
| `drift` | Response refers to a different domain than the request |
| `planning_mode_violation` | Response asserts execution while planning mode is active |
| `incomplete_multipart` | Multi-part request not fully answered |

When `should_retry=True`, the agent gets exactly one corrective LLM round with a precise prompt naming the missing section.

## Specialized guards

### Low-Intent Cold-Start Guard

`events/handlers.py` lines 681–743. See [Sandboxing](/security/sandboxing#cold-start-hallucination-guard).

### Multi-URL Aggregator

`events/handlers.py` ~line 5355. See [Sandboxing](/security/sandboxing#multi-url-aggregator-error-prefix-detection).

### Agent Name Preservation

`events/handlers.py` lines 2450–2474 — `_AGENT_NAME_PATTERNS`.

Three regexes match name extractors (multilingual). Non-greedy multi-token capture `[\w-]+(?:\s+[\w-]+){0,4}?` with a lookahead stop-set on clause connectors and punctuation. Quoted form takes priority via the first alternation group.

## Regression suite

`tests/test_policy_regressions.py` exercises 50+ deterministic cases against `policy/regression_checks.py`. The suite runs at Docker image build time; build fails if any check fails. New policy changes should add a regression case before shipping.

See [Testing and Audit](/security/testing-and-audit) for how to run tests and what the audit methodology covers.

## See also

- [Sandboxing](/security/sandboxing) — container, shell, Python, browser, SSRF
- [Privilege Boundaries](/security/privilege-boundaries) — broker, self-improve
- [Audit Logs](/security/audit-logs) — what's logged
- [Testing and Audit](/security/testing-and-audit) — regression methodology
- [Known Limitations](/known-limitations) — residual risks
