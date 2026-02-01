<script>
  /** @type {{ variant?: string, disabled?: boolean, loading?: boolean, type?: string, onclick?: Function }} */
  let {
    variant = "primary",
    disabled = false,
    loading = false,
    type = "button",
    onclick = undefined,
    children,
  } = $props();
</script>

<button
  class="btn btn--{variant}"
  {type}
  disabled={disabled || loading}
  {onclick}
>
  {#if loading}
    <span class="spinner"></span>
  {/if}
  {@render children()}
</button>

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border-radius: var(--radius);
    font-size: 0.875rem;
    font-weight: 500;
    line-height: 1.5;
    transition: background 150ms ease, border-color 150ms ease, color 150ms ease, opacity 150ms ease;
    cursor: pointer;
    border: 1px solid transparent;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn--primary {
    background: var(--accent);
    color: #fff;
  }
  .btn--primary:hover:not(:disabled) {
    background: var(--accent-hover);
  }

  .btn--secondary {
    background: transparent;
    border-color: var(--border);
    color: var(--text-secondary);
  }
  .btn--secondary:hover:not(:disabled) {
    border-color: var(--border-hover);
    color: var(--text-primary);
  }

  .btn--danger {
    background: var(--status-error);
    color: #fff;
  }
  .btn--danger:hover:not(:disabled) {
    background: #dc2626;
  }

  .btn--ghost {
    background: transparent;
    color: var(--text-secondary);
  }
  .btn--ghost:hover:not(:disabled) {
    color: var(--text-primary);
  }

  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
