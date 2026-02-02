# Airlock

**A trust boundary between AI agents and infrastructure.**

**Website:** [airlock.sh](https://airlock.sh)

## The Problem

AI agents are great at reasoning. They're terrible at holding secrets and doing math.

**No serious company gives production credentials to an LLM.** Your Stripe API key, your database connection string, your Oracle auth token — flowing through model context windows, sitting in plaintext logs, one prompt injection away from exfiltration. Compliance teams shut this down on sight, and they're right to.

**Non-deterministic workflows don't work in business.** Your CFO asks "why is this number different from yesterday?" and you can't say "the AI felt different today." Reports, pipelines, monitoring — they need to produce the same output given the same input. Every time.

These aren't edge cases. They're the two walls that every AI-in-the-enterprise project hits.

## The Solution

**Credentials stay in a trusted environment the agent can't see.** The agent gets an opaque profile key. Airlock resolves that to real credentials at runtime, injects them into the execution environment, and scrubs them from the output. The agent never sees, touches, or transmits a single secret.

**Execution is deterministic Python — not an LLM guessing its way through API calls.** The agent writes real code. `httpx.get()`, `pandas.DataFrame()`, actual Python that does exactly what it says. Same code, same data, same numbers.

## Quick Start

```bash
docker run -p 9090:9090 ghcr.io/computclaw/airlock:latest
```

Open `http://localhost:9090` in your browser. That's it.

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│  1. DEPLOY                                              │
│     User runs Docker container, opens web UI            │
│     Sets admin password on first visit                  │
├─────────────────────────────────────────────────────────┤
│  2. CREDENTIALS                                         │
│     Agent creates credential slots (name + description) │
│     User fills in actual values via web UI              │
│     All values encrypted at rest (AES-256-GCM)          │
├─────────────────────────────────────────────────────────┤
│  3. PROFILES                                            │
│     Agent or user creates a profile                     │
│     Selects which credentials the profile can access    │
│     User locks the profile → generates ark_ID:SECRET    │
│     Key shown once, copy it, won't be shown again       │
├─────────────────────────────────────────────────────────┤
│  4. EXECUTE                                             │
│     Agent sends code + HMAC hash + Bearer auth          │
│     Airlock verifies identity + code integrity          │
│     Injects credentials into sandboxed Python worker    │
│     Returns sanitized results (secrets redacted)        │
└─────────────────────────────────────────────────────────┘
```

## Credentials

Agents and users collaborate to manage credentials:

- **Agent creates slots** — defines what credentials are needed (name + description), e.g., "Stripe API Key", "Database URL"
- **User fills values** — enters actual secrets via the web UI (never through the API)
- **Encrypted at rest** — AES-256-GCM with a master key stored in the persistent volume
- **Agent never sees values** — the API returns `value_exists: true/false`, never the actual secret
- **Export/import** — migrate your entire Airlock state between hosts, encrypted with a user-chosen passphrase

## Profiles

A profile is scoped, authenticated access to a set of credentials:

- **Two-part key:** `ark_ID:SECRET` — generated when the user locks the profile
- **Auth flow:** Agent sends `Authorization: Bearer ark_ID` + `HMAC-SHA256(secret, script)` as a hash in the request body
- **Code integrity:** The HMAC proves the script hasn't been tampered with in transit
- **Lifecycle:** unlocked (configuring) → locked (production-ready) → revocable at any time
- **Expiration:** optional expiry date, auto-revokes after
- **Key regeneration:** rotate the key without recreating the profile
- **Scoped access:** each profile only exposes selected credentials

```
Profile lifecycle:

  CREATE → add credentials → LOCK → execute → REVOKE
                                ↑         │
                                └─────────┘
                              (regenerate key)
```

## Deployment

Single Docker image. No external dependencies.

```bash
# Standalone
docker run -d -p 9090:9090 -v airlock_data:/data ghcr.io/computclaw/airlock:latest

# Docker Compose
docker compose up -d
```

The `-v airlock_data:/data` volume persists credentials, profiles, execution history, and the encryption master key across restarts.

### Cloud Deploy

One-click deploy to:

- **Render** — persistent disk for `/data`
- **Railway** — volume mount for `/data`
- **Fly.io** — volume for `/data`

_(Deploy buttons coming soon)_

### Requirements

Agents can declare Python package requirements:

```
POST /requirements
{"packages": ["httpx", "pandas", "openpyxl"]}
```

Packages are `pip install`'d in the running container and persisted in the database — automatically reinstalled on restart.

## Agent Integration

### Self-Onboarding

Airlock is designed so agents can discover and onboard themselves:

1. **Static SKILL.md** (GitHub / airlock.sh) — agent learns what Airlock is and how the API works
2. **User deploys** — `docker run` or one-click cloud
3. **Dynamic `GET /skill.md`** (running instance) — returns available profiles, SDK reference, instance URL
4. **Agent starts executing** — `POST /execute` with profile auth

### API Surface

```
# Agent endpoints (no admin auth needed)
GET  /skill.md                        → Dynamic skill doc for self-onboarding
GET  /credentials                     → List credential slots (no values)
POST /credentials                     → Create credential slot
GET  /profiles                        → List available profiles
GET  /profiles/{id}                   → Profile details
POST /profiles                        → Create a profile
POST /profiles/{id}/credentials       → Add credential to profile
DELETE /profiles/{id}/credentials     → Remove credential from profile
POST /requirements                    → Install Python packages
GET  /requirements                    → List installed packages
POST /execute                         → Execute code (Bearer auth + HMAC)
GET  /executions/{id}                 → Poll for results
POST /executions/{id}/respond         → Resume LLM pause

# Admin endpoints (session token from web UI login)
POST /api/admin/profiles/{id}/lock    → Lock profile, returns ark_ID:SECRET
POST /api/admin/profiles/{id}/revoke  → Revoke profile
POST /api/admin/profiles/{id}/regenerate-key → Rotate key
```

### LLM Pause/Resume

Scripts can call `llm.complete(prompt)` to pause execution and ask the agent for LLM reasoning:

```python
# Inside a script running in Airlock
result = llm.complete("Summarize these Q4 numbers: " + json.dumps(data))
```

The execution pauses, the agent sees `{status: "awaiting_llm", prompt: "..."}`, runs the LLM, and posts the response back. Deterministic data processing + LLM interpretation, cleanly separated.

## Security Model

- **Credentials never leave Airlock** — agents only see opaque profile keys
- **HMAC code integrity** — `HMAC-SHA256(secret, script)` proves code wasn't tampered with
- **Encrypted storage** — AES-256-GCM, master key in persistent volume
- **Output sanitization** — all output scanned for secrets before return
- **Profile scoping** — each profile only exposes selected credentials
- **Expiration & revocation** — time-limited access, instantly revocable
- **Sandboxed execution** — non-root, resource-limited, isolated Python worker
- **No TLS in v1** — rely on infrastructure (Render/Railway/Fly/nginx). Airlock focuses on what runs above the transport layer.

## Architecture

```
┌────────────────────────────────┐
│         Docker Container        │
│                                 │
│  ┌──────────┐   ┌───────────┐  │
│  │ Svelte   │   │  Python   │  │
│  │ Web UI   │   │  FastAPI  │  │
│  │ (static) │   │  Backend  │  │
│  └────┬─────┘   └─────┬─────┘  │
│       │               │         │
│       └───────┬───────┘         │
│               │                 │
│         ┌─────┴──────┐          │
│         │   SQLite    │          │
│         │  (encrypted │          │
│         │   values)   │          │
│         └─────┬──────┘          │
│               │                 │
│         /data volume            │
│  (credentials, profiles,        │
│   master key, history)          │
└────────────────────────────────┘
```

Single Docker image, multi-stage build: Svelte frontend + Python FastAPI backend. Everything in one container.

## Status

🚧 **Under active development.**

- ✅ Phase 1: Foundation (API, execution engine, web UI)
- ✅ Phase 2: Docker execution (sandboxed Python workers)
- ✅ Phase 3: Credential management (encrypted storage, agent/user collaboration)
- 🔨 Phase 4: Profile system (two-part keys, HMAC auth, lock/revoke lifecycle)

Built by [Martin Bundgaard](https://github.com/ComputClaw) and [Comput](https://comput.sh).

## Docs

- [Architecture](docs/architecture.md) — full system design
- [Agent Guide](docs/agent-guide.md) — 8-step workflow from discovery to execution
- [Specs](specs/) — detailed implementation specs for each phase
