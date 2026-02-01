# Airlock

**A trust boundary between AI agents and infrastructure.**

Airlock lets AI agents execute code against authenticated APIs without ever seeing the credentials. The agent writes the code. Airlock runs it with injected secrets in a sandboxed environment. Only sanitized results come back.

## The Problem

AI agents need to access data from external APIs — but giving an LLM your API keys means those credentials flow through the model provider's infrastructure, appear in conversation context, and can be leaked through prompt injection or hallucination.

## The Solution

```
Agent writes Python code
        ↓
Airlock receives code + declared dependencies
        ↓
Secrets injected as environment variables (agent never sees them)
        ↓
Code runs in isolated Docker container
  - Network: allowlisted hosts only
  - Timeout: configurable (default 60s)
  - Memory: capped (default 512MB)
  - Filesystem: read-only except /output
        ↓
Sanitized results returned to agent
  - stdout/stderr with secrets redacted
  - Files from /output
```

## Key Principles

1. **Secrets never touch the LLM.** They exist only inside the execution container.
2. **Execution is deterministic.** Same code + same data = same results. The AI adds interpretation, not randomness.
3. **Network is allowlisted.** Code can only reach declared API endpoints. No phoning home.
4. **Containers are ephemeral.** Spun up per execution, killed after. No state leaks between runs.
5. **Output is sanitized.** Even if code accidentally prints a secret, it gets redacted before reaching the agent.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full design.

## Status

🚧 Under construction. Built by Martin Bundgaard and Comput.
