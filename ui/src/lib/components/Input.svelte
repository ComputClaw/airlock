<script>
  /** @type {{ label?: string, type?: string, value?: string, mono?: boolean, error?: string, placeholder?: string, id?: string, autocomplete?: string, required?: boolean, minlength?: number }} */
  let {
    label = "",
    type = "text",
    value = $bindable(""),
    mono = false,
    error = "",
    placeholder = "",
    id = undefined,
    autocomplete = undefined,
    required = false,
    minlength = undefined,
  } = $props();
</script>

<div class="input-group">
  {#if label}
    <label class="input-label" for={id}>{label}</label>
  {/if}
  <input
    class="input-field"
    class:mono
    class:has-error={!!error}
    {type}
    {id}
    {placeholder}
    {autocomplete}
    {required}
    {minlength}
    bind:value
  />
  {#if error}
    <p class="input-error">{error}</p>
  {/if}
</div>

<style>
  .input-group {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .input-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .input-field {
    width: 100%;
    padding: 0.625rem 0.875rem;
    background: var(--bg-raised);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-size: 0.875rem;
    outline: none;
    transition: border-color 150ms ease;
  }

  .input-field:focus {
    border-color: var(--accent);
  }

  .input-field.mono {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
  }

  .input-field.has-error {
    border-color: var(--status-error);
  }

  .input-field::placeholder {
    color: var(--text-muted);
  }

  .input-error {
    font-size: 0.75rem;
    color: var(--status-error);
  }
</style>
