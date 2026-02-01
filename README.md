# Airlock

**A trust boundary between AI agents and infrastructure.**

Airlock lets AI agents execute deterministic Python code against authenticated APIs — without ever seeing the credentials. The agent writes code, Airlock runs it in an isolated worker pool with injected secrets, and returns sanitized results.

## Core Principle: Deterministic Execution

> **Same code + same source data = same numbers. Every time.**

All data fetching, aggregation, calculation, and report building is deterministic Python. LLM is optional and only used for presentation — summaries, conclusions, insights. The data in any report is always deterministic. The AI adds interpretation, not randomness.

## How It Works

```
Agent POSTs code to Airlock
        ↓
Airlock routes to an idle worker in the project's pool
        ↓
Worker executes code with secrets as env vars
  - Network: allowlisted hosts only
  - Secrets: injected at container start
  - Isolation: per-project worker pools
        ↓
If script calls llm.complete():
  - Execution pauses
  - Agent sees {status: "awaiting_llm", prompt: "..."}
  - Agent runs LLM, POSTs response back
  - Script resumes
        ↓
Sanitized results returned (secrets redacted)
```

## Architecture at a Glance

- **Worker Pool Model**: Per-project pools of long-running Docker containers. Warm, fast, isolated.
- **Polling API**: Agent POSTs code → gets 202 + execution_id → polls until done. No webhooks, works behind NAT.
- **LLM via Polling**: Scripts can request LLM completions. Airlock holds zero LLM credentials — the agent provides them.
- **Secret Isolation**: Secrets exist only inside worker containers as env vars. Output is redacted before return.

## Lifecycle

```
project create → project up --replicas N → requests routed → project down
```

## Status

🚧 Under construction. Built by Martin Bundgaard and Comput.

See [docs/architecture.md](docs/architecture.md) for the full design.
