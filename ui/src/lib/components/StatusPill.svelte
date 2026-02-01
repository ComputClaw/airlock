<script>
  /** @type {{ status: string, label?: string }} */
  let { status, label = undefined } = $props();

  const statusConfig = {
    locked: { color: "success", text: "Locked" },
    unlocked: { color: "warning", text: "Unlocked" },
    "value-set": { color: "success", text: "Value Set" },
    "no-value": { color: "warning", text: "No Value" },
    active: { color: "success", text: "Active" },
    expired: { color: "error", text: "Expired" },
    revoked: { color: "error", text: "Revoked" },
    completed: { color: "success", text: "Completed" },
    error: { color: "error", text: "Error" },
    timeout: { color: "error", text: "Timeout" },
    pending: { color: "warning", text: "Pending" },
    running: { color: "info", text: "Running" },
    awaiting_llm: { color: "info", text: "Awaiting LLM" },
  };

  let config = $derived(statusConfig[status] || { color: "warning", text: status });
  let displayLabel = $derived(label || config.text);
</script>

<span class="pill pill--{config.color}">{displayLabel}</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 500;
    line-height: 1.5;
    white-space: nowrap;
  }

  .pill--success {
    background: rgba(34, 197, 94, 0.12);
    color: #22c55e;
  }

  .pill--warning {
    background: rgba(245, 158, 11, 0.12);
    color: #f59e0b;
  }

  .pill--error {
    background: rgba(239, 68, 68, 0.12);
    color: #ef4444;
  }

  .pill--info {
    background: rgba(99, 102, 241, 0.12);
    color: #6366f1;
  }
</style>
