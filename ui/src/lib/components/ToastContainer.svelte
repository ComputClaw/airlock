<script>
  import { toasts } from "../stores/toast.js";
</script>

{#if $toasts.length > 0}
  <div class="toast-container">
    {#each $toasts as toast (toast.id)}
      <div class="toast toast--{toast.type}">
        <span class="toast-message">{toast.message}</span>
        <button class="toast-close" aria-label="Dismiss" onclick={() => toasts.remove(toast.id)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    {/each}
  </div>
{/if}

<style>
  .toast-container {
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 200;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: var(--bg-overlay);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.75rem 1rem;
    min-width: 280px;
    max-width: 400px;
    animation: slideIn 150ms ease;
  }

  .toast--success {
    border-left: 3px solid var(--status-success);
  }

  .toast--error {
    border-left: 3px solid var(--status-error);
  }

  .toast-message {
    flex: 1;
    font-size: 0.8125rem;
    color: var(--text-primary);
  }

  .toast-close {
    flex-shrink: 0;
    color: var(--text-muted);
    padding: 0.125rem;
    transition: color 150ms ease;
  }

  .toast-close:hover {
    color: var(--text-primary);
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateX(1rem);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }
</style>
