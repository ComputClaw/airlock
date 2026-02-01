# Airlock Implementation Plan

Each phase produces a deployable artifact. You can `docker run` it after every phase and see something working.

---

## Phase 1: Foundation ✅

**Goal:** Runnable container with admin auth and empty web UI shell.

**Deliverables:**
- FastAPI server on `:9090`
- `GET /health` → `{"status": "ok"}`
- First-visit password setup (no console token)
- SQLite database initialized (empty tables for credentials, profiles, executions)
- Web UI shell: setup/login page + dashboard (Svelte + Vite, served as static files)
- `Dockerfile` (multi-stage: Node frontend + Python backend) + `docker-compose.yml`
- GitHub Actions CI: lint, test, build image on push
- Volume mount for `/data` (SQLite persistence)

**Testable:**
- `docker run -p 9090:9090 airlock` → container starts
- `curl localhost:9090/health` → 200
- Open `localhost:9090` → first visit: set password → dashboard
- Subsequent visits: login with password → dashboard

**Version:** `v0.1.0` ✅

---

## Phase 2: Credential Management

**Goal:** Users and agents can manage credential slots. Users set values through the web UI. Agents create slots and read metadata via API.

**Deliverables:**
- **Web UI:** Credential CRUD (add with value, edit value, edit description, delete, list)
- **Agent API:** `GET /credentials` (list all: name, description, `value_exists`), `POST /credentials` (create slots: name + description, no value)
- Credentials encrypted at rest in SQLite (AES-256, key derived from instance secret)
- Instance secret generated on first boot, stored in `/data/.secret`
- Each credential: name, value (encrypted), description, created_at
- Credential values never displayed in full after creation (masked in UI)
- Values can ONLY be set/edited through the web UI, never through the agent API

**Testable:**
- **Web UI:** Add credential "SIMPHONY_API_KEY" with value → stored encrypted in DB
- **Web UI:** List credentials → shows names + descriptions, values masked
- **Web UI:** Edit credential value → updates, all profiles using it get new value
- **Web UI:** Delete credential → gone (fails if referenced by locked profile)
- **Agent API:** `POST /credentials [{"name": "DB_HOST", "description": "Oracle DB hostname"}]` → slot created, `value_exists: false`
- **Agent API:** `GET /credentials` → lists all credentials with `value_exists` flags
- Agent cannot set or read credential values (no endpoint for it)
- Restart container → credentials persist (volume mount)

**Version:** `v0.2.0`

---

## Phase 3: Profile System

**Goal:** Users and agents can create and configure profiles. Users lock profiles through the web UI.

**Deliverables:**
- **Web UI:** Profile CRUD — create, add/remove credentials, lock, revoke, set expiration
- **Agent API:**
  - `GET /profiles` — list all profiles with lock state, credential list + `value_exists` flags
  - `GET /profiles/{id}` — single profile detail
  - `POST /profiles` — create profile (starts unlocked)
  - `POST /profiles/{id}/credentials` — add credentials to unlocked profile
  - `DELETE /profiles/{id}/credentials` — remove credentials from unlocked profile
- Profile ID generation: `ark_` + 24 char random alphanumeric
- Profile states: **unlocked** (setup) → **locked** (production), one-way
- Unlocked: agent and user can add/remove credential references
- Locked: no structural changes, profile usable for execution
- Only the user can lock a profile (via web UI)
- Optional expiration date (auto-revoke after date)
- Revoke button (instant, irreversible)
- Copy profile ID to clipboard

**Testable:**
- **Agent API:** `POST /profiles {"description": "Oracle reporting"}` → get `ark_...` ID, `locked: false`
- **Agent API:** `POST /profiles/{id}/credentials {"credentials": ["SIMPHONY_API_KEY"]}` → credential added
- **Agent API:** `GET /profiles/{id}` → shows credentials with `value_exists` flags
- **Agent API:** Add credentials to locked profile → 409 (rejected)
- **Web UI:** Lock profile → `locked: true`, now usable for execution
- **Web UI:** Revoke profile → status shows "revoked", agent gets 401
- **Agent API:** `GET /profiles` → lists all profiles with full metadata
- Copy `ark_` ID → paste somewhere → correct

**Version:** `v0.3.0`

---

## Phase 4: Execution Engine

**Goal:** Agents can submit Python code and get results. The core of Airlock.

**Deliverables:**
- `POST /execute` — submit code with `profile_id` + `script` + optional `timeout`
  - Returns `execution_id` + `poll_url` (full URL for load-balancer-safe polling)
  - Profile must be **locked** to execute
- `GET /executions/{id}` — poll for status and results (agents should use `poll_url`)
- Profile authentication: `ark_` ID validated, must be locked + not expired/revoked
- Docker-based worker pool: long-running worker containers per project, Airlock routes to idle workers
- Secret injection: profile's credentials available via `settings.get(key)` and `settings.keys()`
- `set_result(data)` SDK function for structured output
- Execution timeout (default 60s, configurable per request)
- Execution statuses: `pending` → `running` → `completed` / `error` / `timeout`
- Execution history stored in SQLite
- Execution history visible in web UI (per-profile filtering)

**Testable:**
- `POST /execute {profile_id: "ark_...", script: "import math; set_result(math.pi)"}` → 202 with `poll_url`
- Poll `poll_url` → `{status: "completed", result: 3.14159...}`
- Script using `settings.get("SIMPHONY_API_KEY")` → gets the real value
- Unlocked profile → 409 (not ready)
- Invalid/revoked/expired `ark_` ID → 401
- Script exceeds timeout → `{status: "timeout"}`
- Script raises exception → `{status: "error", error: "..."}`
- Web UI shows execution history with timestamps, statuses, durations

**Version:** `v0.4.0` — **This is the first version an agent can actually use.**

---

## Phase 5: Security Hardening

**Goal:** Output sanitization, network controls, resource limits.

**Deliverables:**
- Output sanitization: scan stdout, stderr, result, error for credential values
  - Exact match against all credentials in the profile
  - Replace with `[REDACTED...last4]`
- Network allowlist per profile (optional, configured in web UI)
  - Default: all outbound allowed
  - When set: only allowlisted hosts reachable
- Resource limits on workers: memory cap, CPU time limit
- Workers run as non-root user
- Read-only filesystem (except `/tmp`)
- Sanitization log: record when redaction happens (visible in execution detail)

**Testable:**
- Script that prints `settings.get("API_KEY")` to stdout → stdout shows `[REDACTED...xxxx]`
- Script that returns credential in result → result shows `[REDACTED...xxxx]`
- Profile with allowlist `["api.oracle.com"]` → script can reach oracle.com, can't reach google.com
- Script trying to write to `/app/` → permission denied
- Script allocating 2GB when limit is 512MB → killed

**Version:** `v0.5.0`

---

## Phase 6: LLM Pause/Resume

**Goal:** Scripts can request LLM completions from the calling agent.

**Deliverables:**
- `llm.complete(prompt, model="default")` SDK function
- When called: worker pauses, execution status → `awaiting_llm`
- `GET /executions/{id}` returns `{status: "awaiting_llm", llm_request: {prompt, model}}`
- `POST /executions/{id}/respond` — agent provides LLM response
- Worker resumes with the response as return value of `llm.complete()`
- Timeout on LLM wait (configurable, default 5 minutes)
- Multiple `llm.complete()` calls per script supported (sequential)

**Testable:**
- Script: `summary = llm.complete("Summarize: " + data)` → status becomes `awaiting_llm`
- Agent polls, sees prompt, POSTs response → script resumes, completes
- LLM wait timeout → execution fails with descriptive error
- Script with 2 sequential `llm.complete()` calls → both round-trips work

**Version:** `v0.6.0`

---

## Phase 7: Dynamic SKILL.md

**Goal:** Running instance serves a self-describing skill document for agent onboarding.

**Deliverables:**
- `GET /skill.md` — unauthenticated, returns Markdown
- Content: instance URL, available profiles (ID + description + expiry), credential names per profile, SDK reference, example code
- Auto-generated from current database state
- Updates in real-time as profiles are created/revoked

**Testable:**
- `curl localhost:9090/skill.md` → valid Markdown with profile list
- Create new profile → skill.md immediately includes it
- Revoke profile → disappears from skill.md
- Agent reads skill.md → has everything needed to start executing

**Version:** `v0.7.0`

---

## Phase 8: Migration

**Goal:** Users can move their entire Airlock state between hosts.

**Deliverables:**
- Web UI: Settings → Export → enter passphrase → download `.airlock` file
- Web UI: Settings → Import → upload `.airlock` file → enter passphrase → preview → confirm
- Export: encrypted SQLite dump (AES-256 with user passphrase)
- Import: preview what's coming in, choose merge strategy (skip dupes / overwrite)
- Selective export: choose which profiles to include
- Optional auto-backup: scheduled encrypted snapshots to `/data/backups/`
- **No API endpoints** — UI only, human in the loop

**Testable:**
- Export → download file → it's encrypted (not readable as plaintext)
- Import on fresh instance → all profiles + credentials restored
- `ark_` IDs preserved → agents continue working without reconfiguration
- Wrong passphrase → import fails with clear error
- Selective export → only chosen profiles included

**Version:** `v0.8.0`

---

## Phase 9: Cloud Deploy

**Goal:** One-click deployment and agent-driven deployment.

**Deliverables:**
- `render.yaml` — Render blueprint (one-click deploy button)
- `railway.toml` — Railway config
- `fly.toml` — Fly.io config
- Deploy buttons in README and on airlock.sh
- Static SKILL.md (for GitHub/airlock.sh) updated with deployment payloads per platform
- Agent can read static SKILL.md → deploy via platform MCP → read dynamic /skill.md → start working

**Testable:**
- Click "Deploy to Render" → working Airlock instance in ~2 minutes
- Agent reads SKILL.md → programmatically deploys → gets URL → reads /skill.md → executes code
- All platforms: persistent storage configured correctly (DB survives redeploys)

**Version:** `v0.9.0`

---

## Phase 10: Release & Distribution

**Goal:** Automated releases, published images, documentation site.

**Deliverables:**
- GitHub Actions: on version tag push → build + push image to GHCR (`ghcr.io/computclaw/airlock`)
- Also push to Docker Hub (`computclaw/airlock`) for discoverability
- GitHub Releases with changelog (auto-generated from commits)
- Semantic versioning: `v{major}.{minor}.{patch}`
- `latest` tag always points to newest stable release
- airlock.sh landing page with docs, deploy buttons, SKILL.md link
- README badges: version, image size, CI status

**Testable:**
- Push tag `v1.0.0` → image appears on GHCR + Docker Hub within minutes
- `docker pull ghcr.io/computclaw/airlock:v1.0.0` → works
- `docker pull ghcr.io/computclaw/airlock:latest` → same image
- GitHub Release page shows changelog
- airlock.sh serves landing page

**Version:** `v1.0.0` 🎉

---

## Build & Release Pipeline

Managed by Comput (that's me). Martin focuses on development.

### CI (every push)
- Lint (ruff)
- Type check (mypy)
- Unit tests (pytest)
- Build Docker image (verify it builds)

### Release (on version tag)
1. CI passes
2. Build multi-arch image (amd64 + arm64)
3. Push to GHCR: `ghcr.io/computclaw/airlock:{version}` + `latest`
4. Push to Docker Hub: `computclaw/airlock:{version}` + `latest`
5. Create GitHub Release with auto-generated changelog
6. Update airlock.sh with new version reference

### Development Flow
```
Martin runs from source locally (no Docker needed during dev)
  → CC implements phase spec
  → Comput reviews via git diff
  → Comput writes next phase spec
  → Repeat until phase complete
  → Comput tags release → CI builds + publishes
```

---

## Summary

| Phase | What | Agent-Usable | Version |
|-------|------|:---:|---------|
| 1 | Foundation | ❌ | v0.1.0 |
| 2 | Credentials | ❌ | v0.2.0 |
| 3 | Profiles | ❌ | v0.3.0 |
| 4 | **Execution Engine** | ✅ | v0.4.0 |
| 5 | Security | ✅ | v0.5.0 |
| 6 | LLM Pause/Resume | ✅ | v0.6.0 |
| 7 | Dynamic SKILL.md | ✅ | v0.7.0 |
| 8 | Migration | ✅ | v0.8.0 |
| 9 | Cloud Deploy | ✅ | v0.9.0 |
| 10 | Release & Docs | ✅ | v1.0.0 |

Phase 4 is the inflection point — that's where Airlock becomes usable. Everything before is setup, everything after is polish and distribution.
