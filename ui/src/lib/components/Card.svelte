<script>
  /** @type {{ clickable?: boolean, padding?: string, onclick?: Function }} */
  let {
    clickable = false,
    padding = "1.25rem",
    onclick = undefined,
    children,
  } = $props();
</script>

{#if clickable}
  <button class="card clickable" style:padding {onclick}>
    {@render children()}
  </button>
{:else}
  <div class="card" style:padding>
    {@render children()}
  </div>
{/if}

<style>
  .card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    width: 100%;
    text-align: left;
  }

  .clickable {
    cursor: pointer;
    transition: border-color 150ms ease;
  }

  .clickable:hover {
    border-color: var(--border-hover);
  }
</style>
