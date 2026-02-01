# Airlock — Agent Skill Document

> **This is the static SKILL.md.** It tells you what Airlock is and how to use it.
> For instance-specific info (available profiles, instance URL), read `GET /skill.md` on a running Airlock instance.

## What is Airlock?

Airlock is a trust boundary between you (an AI agent) and authenticated infrastructure. It lets you execute Python code against real APIs — without ever seeing the credentials.

You write code. Airlock runs it with the right credentials injected. You get the results back.

## Why Airlock?

You need to call APIs (fetch data, create reports, automate workflows), but you shouldn't hold API keys. Airlock solves this:

- **You never see credentials** — only an opaque profile ID (`ark_...`)
- **You write Python** — full access to httpx, pandas, etc.
- **Airlock injects secrets** — credentials are resolved at runtime
- **Output is sanitized** — secrets are redacted before you see results
- **Deterministic execution** — same code + same data = same result, every time

## Getting Started

### Step 1: Deploy Airlock

Ask the user to run:

```bash
docker run -p 9090:9090 ghcr.io/computclaw/airlock:latest
```

Or deploy to a cloud platform (Render, Railway, Fly.io).

On first boot, an admin token is printed to the container console. The user needs this to log in.

### Step 2: User Configures Airlock

The user opens `http://<host>:9090` in their browser and:

1. Logs in with the admin token
2. Adds API credentials (e.g., `SIMPHONY_API_KEY`, `STRIPE_SECRET_KEY`)
3. Creates a **profile** — selects which credentials are included
4. Gets a profile ID: `ark_7f3x9kw2m4p...`
5. Shares the profile ID with you

### Step 3: Read Dynamic Skill Document

Once Airlock is running and configured:

```
GET http://<host>:9090/skill.md
```

This returns the instance-specific skill document with:
- Available profiles (ID, description, expiration)
- Which credential keys each profile has access to
- SDK reference
- Example code

### Step 4: Execute Code

```
POST http://<host>:9090/execute
Content-Type: application/json

{
  "profile_id": "ark_7f3x9kw2m4p",
  "script": "import httpx\nresponse = httpx.get(settings.get('API_URL'), headers={'Authorization': f'Bearer {settings.get(\"API_KEY\")}'})\nset_result(response.json())"
}
```

Response:
```json
{
  "execution_id": "exec_a1b2c3d4",
  "status": "pending"
}
```

### Step 5: Poll for Results

```
GET http://<host>:9090/executions/exec_a1b2c3d4
```

Response (when complete):
```json
{
  "execution_id": "exec_a1b2c3d4",
  "status": "completed",
  "result": { "data": [...] },
  "stdout": "...",
  "execution_time_ms": 1234
}
```

## API Reference

### `POST /execute`

Submit Python code for execution.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `profile_id` | string | yes | Profile ID (`ark_...`) — acts as authentication |
| `script` | string | yes | Python code to execute |
| `timeout` | integer | no | Max execution time in seconds (default: 60) |

Returns `202` with `{execution_id, status}`.

### `GET /executions/{id}`

Poll for execution status and results.

**Statuses:**
| Status | Meaning |
|--------|---------|
| `pending` | Queued, waiting for a worker |
| `running` | Code is executing |
| `awaiting_llm` | Script called `llm.complete()`, waiting for your response |
| `completed` | Finished successfully |
| `error` | Execution failed |
| `timeout` | Exceeded time limit |

### `POST /executions/{id}/respond`

Provide an LLM response when status is `awaiting_llm`.

```json
{
  "response": "Your LLM-generated text here..."
}
```

### `GET /skill.md`

Returns the dynamic skill document for this instance. Read this to discover available profiles and capabilities.

### `GET /health`

Returns `{"status": "ok"}` if the instance is healthy.

## Script SDK

These functions are available inside your Python scripts:

### `settings.get(key) → str`

Get a credential or setting value. The available keys depend on which credentials are linked to the profile you're using.

```python
api_key = settings.get("STRIPE_SECRET_KEY")
base_url = settings.get("API_BASE_URL")
```

### `settings.keys() → list[str]`

List all available setting keys for the current profile.

```python
available = settings.keys()
# ["STRIPE_SECRET_KEY", "API_BASE_URL", ...]
```

### `llm.complete(prompt, model="default") → str`

Pause execution and request an LLM completion from the calling agent. Use this only for presentation — summaries, narratives, insights. Never for data computation.

```python
data = fetch_revenue_data()
summary = llm.complete(f"Summarize this revenue data in 3 bullet points:\n{data}")
set_result({"data": data, "summary": summary})
```

### `set_result(data)`

Set the return value of the script. `data` must be JSON-serializable.

```python
set_result({"revenue": 142000, "growth": 0.15})
```

## Example: Full Script

```python
import httpx

# Fetch data using injected credentials
response = httpx.get(
    f"{settings.get('API_BASE_URL')}/v1/revenue",
    headers={"Authorization": f"Bearer {settings.get('API_KEY')}"},
    params={"period": "2025-Q1"}
)
data = response.json()

# Compute deterministic results
total = sum(item["amount"] for item in data["transactions"])
avg = total / len(data["transactions"]) if data["transactions"] else 0

# Optional: ask the agent's LLM for a narrative
summary = llm.complete(
    f"Write a brief revenue summary. Total: ${total:,.2f}, "
    f"Average transaction: ${avg:,.2f}, "
    f"Transaction count: {len(data['transactions'])}"
)

set_result({
    "total_revenue": total,
    "average_transaction": avg,
    "transaction_count": len(data["transactions"]),
    "summary": summary
})
```

## Important Notes

- **Never hardcode credentials** in your scripts — always use `settings.get()`
- **Output is sanitized** — if you accidentally print a credential value, it will be redacted as `[REDACTED...last4]`
- **Deterministic first** — compute all data with Python, use `llm.complete()` only for presentation
- **Poll, don't block** — the execute endpoint returns immediately; poll `/executions/{id}` for results
- **Profile scope** — you can only access credentials that were linked to your profile by the user
