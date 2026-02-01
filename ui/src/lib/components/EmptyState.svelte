<script>
  /** @type {{ message: string }} */
  let { message } = $props();
</script>

<div class="empty">
  <p>{message}</p>
</div>

<style>
  .empty {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 3rem 1rem;
    color: var(--text-muted);
    font-size: 0.875rem;
  }
</style>
