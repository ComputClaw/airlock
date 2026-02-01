# Airlock

**A trust boundary between AI agents and infrastructure.**

**Website:** [airlock.sh](https://airlock.sh)

## The Problem

AI agents are great at reasoning. They're terrible at holding secrets and doing math.

**No serious company gives production credentials to an LLM.** Think about what that actually means: your Stripe API key, your database connection string, your Oracle auth token — flowing through model context windows, sitting in plaintext logs, one prompt injection away from exfiltration. The LLM hallucinates a weird API call? Congratulations, your production key is now in an error message somewhere. Compliance teams shut this down on sight, and they're right to. It's a non-starter for any real enterprise work.

**Non-deterministic workflows don't work in business.** Your CFO asks "why is this number different from yesterday?" and you can't say "the AI felt different today." But that's exactly what happens when you put an LLM in the execution loop. It decides to parse the date differently. It rounds a number. It skips a row because it "seemed like a duplicate." Reports, pipelines, monitoring — they need to produce the same output given the same input. Every time. No exceptions. The moment you let an LLM make decisions about data, you lose that guarantee.

These aren't edge cases. They're the two walls that every AI-in-the-enterprise project hits.

## The Solution

Airlock solves both problems at once.

**Credentials stay in a trusted environment the agent can't see.** The agent gets an opaque profile ID. Airlock resolves that to real credentials at runtime, injects them into the execution environment, and scrubs them from the output before anything goes back. The agent never sees, touches, or transmits a single secret.

**Execution is deterministic Python — not an LLM guessing its way through API calls.** The agent writes real code. `httpx.get()`, `pandas.DataFrame()`, actual Python that does exactly what it says. Same code, same data, same numbers. If you want the AI to write a summary or add insights, it does that *at the end* — interpretation on top of deterministic data, not randomness in the middle of the pipeline.

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
- Both agents and users can create profiles; agents add credential references, users fill in values and lock
- Optional **expiration date** — auto-revokes after a set date
- **Revocable** from the UI at any time
- The agent only ever sees the profile ID — **never the credentials behind it**
- Different profiles can expose different subsets of credentials (read-only vs admin)

### Web UI for Credential Management

Airlock exposes a web UI on its HTTP port. When you deploy the container and open the URL in a browser, you get:

- **First-visit setup** — first user sets an admin password (no console access needed)
- **Credential management** — add/edit/delete API credentials (stored encrypted). Agents can create credential slots (name + description), users fill in values.
- **Profile management** — profiles start **unlocked** (agent and user add credentials), user **locks** when ready for production. Locked profiles can execute.
- **Expiration controls** — set optional expiration on profiles
- **Execution history** — what ran, when, success/fail, duration
- **Stats dashboard** — executions per profile, error rates, avg duration
- **Export/import** — migrate your entire Airlock state between hosts (encrypted, UI-only)

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

3. User opens web UI
   → Sets admin password (first visit), adds credential values, locks profiles

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
