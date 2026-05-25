# Contributing

WASP welcomes contributions. Please read before opening a PR.

## License implications

WASP is licensed under [Apache 2.0](../LICENSE.md). By submitting a contribution, you agree that your contribution is licensed under the same Apache 2.0 terms, including the explicit patent grant in Section 3 of the license. There is no separate CLA — the inbound = outbound model applies.

If you are not comfortable with this, please do not contribute code. Documentation and bug reports are always welcome regardless.

## Dev setup

```bash
git clone https://github.com/wasp-agent/wasp.git
cd wasp

# Install from this checkout (sources live in place; rebuilds reflect your edits)
./install.sh --install-method local --local-source "$PWD" --install-dir "$PWD"
```

This uses your checkout as the install dir, so source edits are immediate (subject to container rebuilds).

For Python-side hot iteration:

```bash
docker compose exec agent-core bash
# Inside the container:
python -m pytest tests/
```

## Style

- **Python**: pep8-ish, type hints encouraged, `from __future__ import annotations` at module top.
- **Bash**: `set -Eeuo pipefail`, ShellCheck-clean.
- **Comments**: write the WHY, not the WHAT. Code should explain itself.
- **Don't add error handling for impossible cases.** If a function is only called with validated input, don't re-validate.

## Commit messages

Imperative, lowercase, concise:

```
fix browser engine drift after cloudflare block

The drift counter was incrementing even when the engine was bound,
making metrics inconsistent. Move the bump inside the unbound branch.
```

Avoid "refactor" / "cleanup" without detail. Explain what specifically changed.

## PR guidelines

1. **One topic per PR.** Don't bundle a bug fix with a refactor.
2. **Tests where it makes sense.** Especially policy / planner / context changes.
3. **Update docs** when changing user-visible behavior.
4. **No new hardcoded URLs / domains / preferences.** WASP must remain neutral about which sites the agent uses; resolution happens at runtime via `web_search`.
5. **Run before opening:**
   ```bash
   bash -n install.sh bin/wasp scripts/*.sh
   docker compose --project-directory . config --quiet
   ```

## Where to work

- **Skills**: `containers/agent-core/src/skills/builtin/` — one file per skill, inherits `SkillBase`.
- **Memory tiers**: `containers/agent-core/src/memory/` — episodic, semantic, procedural, KG, etc.
- **Planning**: `containers/agent-core/src/intent/`, `goal_orchestrator/`, `agent_manager/`.
- **Policy/context**: `containers/agent-core/src/agent/context.py`, `policy/`.
- **Dashboard**: `containers/agent-core/src/dashboard/` — FastAPI + Jinja templates.

## Building a release tarball

The installer's default `tarball` method downloads `wasp-release.tar.gz` from
the project's hosted artifact. To regenerate that artifact cleanly, use the
provided build script — it uses an allowlist staging copy, excludes private
artifacts (operator audit reports, the public-domain nginx config, runtime
data volumes, byte caches), and refuses to package if any forbidden
operator-specific identifier survives the scan:

```bash
sudo release-prep/scripts/build-release.sh \
    --source "$PWD" \
    --out "$PWD/release-prep/wasp-release.tar.gz"
```

The script is the only supported packaging path. Do NOT run `tar` directly
release artifact is still sitting in `containers/agent-nginx/html/`.

## Reporting bugs

Open a GitHub issue with:
- `wasp health` output
- Last 50 lines of `wasp logs agent-core`
- OS / Docker version (`docker version`, `cat /etc/os-release`)
- What you did and what you expected vs got

## Reporting security issues

Do **not** open a public issue. See [SECURITY.md](SECURITY.md).
