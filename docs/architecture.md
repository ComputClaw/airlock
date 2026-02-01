# Airlock Architecture

## Overview

Airlock is a Python code execution service designed as a trust boundary between AI agents and authenticated infrastructure. It accepts code from untrusted sources (LLMs), runs it with injected secrets in a sandboxed container, and returns sanitized results.

## Components

### 1. API Server

A lightweight HTTP API that receives execution requests and returns results.

**Stack:** FastAPI (Python)

**Endpoints:**

```
POST /execute
  Request:
    {
      "code": "string",              # Python code to execute
      "project": "string",           # Project/config identifier
      "timeout": 60,                 # Max execution time (seconds)
      "allowlist": ["api.example.com"]  # Optional override of network allowlist
    }
  
  Response:
    {
      "status": "success" | "error" | "timeout",
      "stdout": "string",            # Sanitized stdout
      "stderr": "string",            # Sanitized stderr  
      "output_files": [...],         # Files written to /output
      "execution_time_ms": 1234,
      "exit_code": 0
    }

GET /projects
  Lists available projects and their declared capabilities (which APIs they can reach).

GET /health
  Health check.
```

### 2. Project Configs

Each "project" defines a set of secrets and network rules. Stored as YAML files on the server.

```yaml
# projects/simphony-reports.yaml
name: simphony-reports
description: "Oracle Simphony revenue and sales reporting"

secrets:
  SIMPHONY_API_KEY: "${vault:simphony_api_key}"
  SIMPHONY_BASE_URL: "https://api.simphony.oracle.com"
  OPERA_API_KEY: "${vault:opera_api_key}"

network_allowlist:
  - "api.simphony.oracle.com"
  - "api.opera.oracle.com"

limits:
  timeout: 60
  memory_mb: 512
  max_output_mb: 10

packages:
  - requests
  - pandas
  - openpyxl
```

The agent knows project names and their descriptions, but never sees the secret values.

### 3. Secret Store

Secrets are stored outside the application in a simple encrypted file, environment variables, or a vault service. They are only read at execution time and injected into the container environment.

**Phase 1:** Encrypted YAML file on disk (simple, good enough for single-machine)
**Phase 2:** HashiCorp Vault or similar (when scaling)

### 4. Executor (Docker)

Each execution spins up a fresh Docker container:

```
Base image: python:3.12-slim + project packages
Mounts:
  - /code/main.py    (the agent's code, read-only)
  - /output/          (writable, returned to agent)
Environment:
  - Project secrets injected as env vars
Network:
  - Custom network with iptables rules for allowlist
  - DNS resolution only for allowlisted hosts
Limits:
  - --memory=512m
  - --cpus=1
  - --read-only (except /output and /tmp)
  - --no-new-privileges
  - --security-opt=no-new-privileges
Lifecycle:
  - Created → Started → Wait for exit or timeout → Killed → Removed
```

### 5. Output Sanitizer

Before returning results to the agent, all output passes through a sanitizer that:

1. Scans stdout/stderr for any secret values (exact match)
2. Scans for common secret patterns (API keys, tokens, bearer strings)
3. Replaces matches with `[REDACTED]`
4. Truncates output to configured maximum size

## Data Flow

```
                    ┌─────────────────────────────────┐
                    │           AI Agent               │
                    │  (writes code, reads results)    │
                    └──────────┬──────────────────┬────┘
                               │ POST /execute    │ Response
                               │ {code, project}  │ {stdout, files}
                    ┌──────────▼──────────────────▼────┐
                    │         Airlock API Server        │
                    │                                   │
                    │  1. Validate request               │
                    │  2. Load project config            │
                    │  3. Resolve secrets                │
                    │  4. Spin up container              │
                    │  5. Inject secrets as env vars     │
                    │  6. Apply network allowlist        │
                    │  7. Execute code                   │
                    │  8. Collect output                 │
                    │  9. Sanitize (redact secrets)      │
                    │ 10. Return results                 │
                    └──────────┬───────────────────┬────┘
                               │                   │
                    ┌──────────▼────┐    ┌─────────▼────┐
                    │  Secret Store │    │   Docker      │
                    │  (encrypted)  │    │   Container   │
                    │               │    │               │
                    │  key: value   │───▶│  ENV vars     │
                    │  key: value   │    │  allowlisted  │
                    └───────────────┘    │  network      │
                                         └───────────────┘
```

## Security Boundaries

| Boundary | What's protected | How |
|----------|-----------------|-----|
| Agent ↔ Airlock | Secrets never sent to agent | Injected in container only, sanitized output |
| Container ↔ Network | No unauthorized API calls | iptables allowlist per project |
| Container ↔ Host | No container escape | Read-only FS, no privileges, resource limits |
| Executions ↔ Each other | No cross-contamination | Fresh container per execution, no shared state |

## Future Considerations

- **Persistent projects**: Pre-built Docker images per project (faster cold start)
- **Code caching**: Hash code, skip re-execution for identical requests
- **Async execution**: Long-running reports with polling/webhooks
- **Multi-language**: Not just Python — Node, SQL, etc.
- **Audit log**: Every execution logged with code, results, timing
- **OpenClaw skill**: A SKILL.md that teaches any agent how to use Airlock
