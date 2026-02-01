# Airlock

**A trust boundary between AI agents and infrastructure.**

Airlock lets AI agents execute deterministic Python code against authenticated APIs — without ever seeing the credentials. The agent writes code, Airlock runs it in an isolated worker with injected secrets, and returns sanitized results.

**Website:** [airlock.sh](https://airlock.sh)

## Core Principle: Deterministic Execution

> **Same code + same source data = same numbers. Every time.**

All data fetching, aggregation, calculation, and report building is deterministic Python. LLM is optional and only used for presentation — summaries, conclusions, insights. The data in any report is always deterministic. The AI adds interpretation, not randomness.

## How It Works

```
User deploys Airlock (single Docker container)
        ↓
Opens web UI → adds API credentials → creates profiles
        ↓
Agent reads GET /skill.md → discovers available profiles
        ↓
Agent POSTs code + profile_id to /execute
        ↓
Airlock runs code with profile's credentials injected
  - Network: allowlisted hosts only
  - Secrets: injected at runtime, never exposed
  - Isolation: sandboxed execution environment
        ↓
If script calls llm.complete():
  - Execution pauses
  - Agent sees {status: "awaiting_llm", prompt: "..."}
  - Agent runs LLM, POSTs response back
  - Script resumes
        ↓
Sanitized results returned (secrets redacted)
```

## Key Concepts

### Profiles — The Key Innovation

A **profile** is scoped access to credentials:

- **Opaque ID**: `ark_` + random string (e.g., `ark_7f3x9kw2m4...`)
- The profile ID acts as both **identifier AND auth** for the API
- User creates profiles in the web UI, selecting which credentials are included
- Optional **expiration date** — auto-revokes after a set date
- **Revocable** from the UI at any time
- The agent only ever sees the profile ID — **never the credentials behind it**
- Different profiles can expose different subsets of credentials (read-only vs admin)

### Web UI for Credential Management

Airlock exposes a web UI on its HTTP port. When you deploy the container and open the IP in a browser, you get:

- **Login** — first boot generates an admin token printed to console
- **Credential management** — add/edit/delete API credentials (stored encrypted)
- **Profile creation** — create profiles with unique `ark_` IDs, select which credentials each profile can access
- **Expiration controls** — set optional expiration on profiles
- **Execution history** — what ran, when, success/fail, duration
- **Stats dashboard** — executions per profile, error rates, avg duration

### Agent-Facing API

The API an agent interacts with is intentionally minimal:

```
POST /execute
  {profile_id: "ark_7f3x...", script: "import httpx..."}
  → 202 {execution_id: "exec_abc123"}

GET /executions/{id}
  → {status: "completed", result: {...}, stdout: "..."}

POST /executions/{id}/respond
  → (for LLM pause/resume)

GET /skill.md
  → Dynamic SKILL.md with available profiles and SDK reference
```

### Two-Layer SKILL.md

- **Static SKILL.md** (on GitHub / airlock.sh): Explains what Airlock is, how to deploy it, how the API works. Any agent can read this before Airlock is even deployed.
- **Dynamic `GET /skill.md`** (on running instance): Returns the actual instance URL, available profiles (ID + description + expiry), SDK reference. Agent reads this to self-onboard.

## Distribution

Single Docker image. No external dependencies.

```bash
docker run -p 9090:9090 ghcr.io/computclaw/airlock:latest
```

That's it. Open `http://localhost:9090` in your browser to configure.

- **SQLite** for state (credentials, profiles, execution history)
- **Web UI** baked into the image
- **No external dependencies**
- **v1**: local network only
- **v2**: optional tunnel integration (ngrok/bore/cloudflare) — one toggle in UI

### One-Click Deploy

Deploy to your favorite cloud platform:

- Render
- Railway
- Fly.io

_(Deploy buttons coming soon)_

## Agent Self-Onboarding Flow

The full journey from discovery to execution:

```
1. Agent reads static SKILL.md from GitHub
   → Discovers what Airlock is, how the API works

2. Agent generates deploy instructions for user
   → "Run this Docker command" or one-click cloud deploy

3. User deploys, opens web UI
   → Adds API credentials, creates profiles (ark_...)

4. Agent reads dynamic GET /skill.md from running instance
   → Sees available profiles, SDK reference, instance URL

5. Agent starts executing code with profile ID
   → POST /execute {profile_id: "ark_...", script: "..."}
```

## Security Model

- **Credentials never leave Airlock** — agents only see opaque profile IDs
- **Output sanitization** — all output scanned for secrets before return
- **Encrypted storage** — credentials stored encrypted in SQLite
- **Profile scoping** — each profile only exposes selected credentials
- **Expiration & revocation** — time-limited access, revocable instantly
- **Network isolation** — code can only reach allowlisted hosts
- **Sandboxed execution** — non-root, resource-limited, read-only filesystem

## Status

🚧 Under construction. Built by Martin Bundgaard and Comput.

See [docs/architecture.md](docs/architecture.md) for the full design.
