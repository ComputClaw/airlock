# Airlock — Agent Guide

How to use Airlock as an AI agent. Follow these steps in order.

---

## Step 1: Discover

Read the static SKILL.md to understand what Airlock is and how it works:

```
GET https://airlock.sh/skill.md
  — or —
Read SKILL.md from the GitHub repo
```

If Airlock isn't deployed yet, help the user deploy it (Docker, Render, Railway, Fly.io).

## Step 2: Connect

Read the dynamic skill document from the running instance:

```
GET https://<airlock-host>/skill.md
```

This tells you:
- The instance URL
- Available profiles (ark_ IDs, descriptions, lock status)
- Available credentials (names, value_exists flags)
- SDK reference

## Step 3: Set Up Credentials

Check what credentials exist:

```
GET /credentials
→ [{"name": "API_KEY", "value_exists": true}, ...]
```

If you need credentials that don't exist yet, create the slots:

```
POST /credentials
{
  "credentials": [
    {"name": "SIMPHONY_API_KEY", "description": "Simphony REST API key"},
    {"name": "DB_HOST", "description": "Oracle database hostname"}
  ]
}
```

You're creating the slot — name and description only. Tell the user to fill in the values in the web UI.

## Step 4: Set Up a Profile

Create a profile for your use case:

```
POST /profiles
{"description": "Oracle reporting — read only"}
→ {"profile_id": "ark_7f3x9kw2m4p", "locked": false}
```

Add the credentials you need:

```
POST /profiles/ark_7f3x9kw2m4p/credentials
{"credentials": ["SIMPHONY_API_KEY", "DB_HOST"]}
```

Check that values are filled in:

```
GET /profiles/ark_7f3x9kw2m4p
→ {
    "locked": false,
    "credentials": [
      {"name": "SIMPHONY_API_KEY", "value_exists": true},
      {"name": "DB_HOST", "value_exists": false}
    ]
  }
```

If values are missing, tell the user:
> "DB_HOST still needs a value. Open the Airlock web UI and fill it in."

Once all values are set, tell the user to **lock the profile** in the web UI. Only locked profiles can execute.

## Step 5: Install Requirements

Check what's installed:

```
GET /requirements
→ ["fastapi", "uvicorn"]  (base packages only)
```

Add what you need:

```
POST /requirements
{"packages": ["httpx", "pandas", "openpyxl"]}
→ {"installed": ["httpx", "pandas", "openpyxl"]}
```

If installation fails, you'll get an error with pip output. Fix the package name and retry.

## Step 6: Validate

**Always run a validation script before doing real work.** This confirms:
- Your profile is locked and working
- Credentials are accessible
- Required packages are installed
- External APIs are reachable

```
POST /execute
{
  "profile_id": "ark_7f3x9kw2m4p",
  "script": "import httpx\n\n# Verify packages\nprint('httpx imported OK')\n\n# Verify credentials\nkeys = settings.keys()\nprint(f'Available keys: {keys}')\nassert 'SIMPHONY_API_KEY' in keys, 'Missing SIMPHONY_API_KEY'\nassert 'DB_HOST' in keys, 'Missing DB_HOST'\n\n# Verify connectivity (optional)\nhost = settings.get('DB_HOST')\nprint(f'DB_HOST = {host}')\n\nset_result({'status': 'ok', 'keys': keys})"
}
```

Poll the result:

```
GET /executions/{id}
→ {"status": "completed", "result": {"status": "ok", "keys": [...]}}
```

If this passes, you're ready. If not, the error tells you exactly what's wrong.

## Step 7: Execute

Now write and run your actual scripts:

```
POST /execute
{
  "profile_id": "ark_7f3x9kw2m4p",
  "script": "import httpx\nimport pandas as pd\n\n# Fetch data\nresp = httpx.get(\n    settings.get('API_URL') + '/reports/revenue',\n    headers={'Authorization': settings.get('SIMPHONY_API_KEY')}\n)\ndata = resp.json()\n\n# Process\ndf = pd.DataFrame(data['items'])\nsummary = df.groupby('location')['revenue'].sum().to_dict()\n\nset_result(summary)",
  "timeout": 30
}
```

Poll with the returned `poll_url` until status is terminal (completed/error/timeout).

## Step 8: Use LLM Integration (Optional)

If your script needs AI-generated content (summaries, insights), use `llm.complete()`:

```python
# Data processing (deterministic)
import httpx
resp = httpx.get(settings.get('API_URL') + '/reports')
data = resp.json()
total = sum(item['revenue'] for item in data)

# AI summary (non-deterministic, clearly separated)
summary = llm.complete(
    f"Write a 2-sentence executive summary of this revenue data: total=${total}, "
    f"locations={len(data)}, top={data[0]['location']}"
)

set_result({"total": total, "summary": summary})
```

When `llm.complete()` is called:
1. Execution pauses
2. You see `{"status": "awaiting_llm", "llm_request": {"prompt": "..."}}`
3. Run the prompt through your own LLM
4. POST the response to `/executions/{id}/respond`
5. Execution resumes

## Best Practices

### Do
- **Validate first** — always run a test script before real work
- **Install requirements early** — do this once, not per execution
- **Check value_exists** — before asking the user to lock, verify all credentials have values
- **Use set_result()** — return structured data, not just print statements
- **Handle errors** — wrap risky operations in try/except
- **Keep scripts focused** — one task per execution, not a mega-script

### Don't
- **Don't hardcode credentials** — always use `settings.get()`
- **Don't print secrets** — output is sanitized, but don't rely on it
- **Don't use LLM for data** — keep data processing deterministic, LLM only for presentation
- **Don't skip validation** — a 5-second test saves minutes of debugging
- **Don't install requirements per execution** — install once, they persist

## Troubleshooting

| Problem | Solution |
|---------|----------|
| 401 on execute | Profile ID wrong, expired, or revoked. Check `GET /profiles` |
| 409 on execute | Profile is unlocked. Tell user to lock it in the web UI |
| Missing key in settings | Credential not in profile. Add it while unlocked, then re-lock |
| Import error | Package not installed. `POST /requirements` first |
| Timeout | Script too slow. Increase timeout or optimize the code |
| Connection refused | External API unreachable. Check network allowlist if configured |
