<script>
  /** @type {{ title: string, action?: import('svelte').Snippet }} */
  let { title, action = undefined } = $props();
</script>

<header class="page-header">
  <h1>{title}</h1>
  {#if action}
    <div class="action">
      {@render action()}
    </div>
  {/if}
</header>

<style>
  .page-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
  }

  h1 {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
  }
</style>
