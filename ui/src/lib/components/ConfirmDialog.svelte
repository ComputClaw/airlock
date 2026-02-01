<script>
  import Button from "./Button.svelte";

  /** @type {{ open: boolean, title?: string, message?: string, confirmLabel?: string, variant?: string, onconfirm?: Function, oncancel?: Function }} */
  let {
    open = $bindable(false),
    title = "Confirm",
    message = "Are you sure?",
    confirmLabel = "Confirm",
    variant = "danger",
    onconfirm = undefined,
    oncancel = undefined,
  } = $props();

  function handleConfirm() {
    open = false;
    onconfirm?.();
  }

  function handleCancel() {
    open = false;
    oncancel?.();
  }

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) handleCancel();
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="overlay" onclick={handleBackdrop}>
    <div class="dialog">
      <h3>{title}</h3>
      <p>{message}</p>
      <div class="actions">
        <Button variant="secondary" onclick={handleCancel}>Cancel</Button>
        <Button {variant} onclick={handleConfirm}>{confirmLabel}</Button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .dialog {
    background: var(--bg-overlay);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    max-width: 400px;
    width: 90%;
  }

  h3 {
    font-size: 1.125rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }

  p {
    color: var(--text-secondary);
    font-size: 0.875rem;
    margin-bottom: 1.25rem;
    line-height: 1.5;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }
</style>
