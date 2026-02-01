<script>
  import { onMount } from "svelte";
  import PageHeader from "../components/PageHeader.svelte";
  import Button from "../components/Button.svelte";
  import Card from "../components/Card.svelte";
  import Input from "../components/Input.svelte";
  import StatusPill from "../components/StatusPill.svelte";
  import EmptyState from "../components/EmptyState.svelte";
  import { api } from "../api.js";
  import { toasts } from "../stores/toast.js";

  let credentials = $state([]);
  let loading = $state(true);
  let showAddForm = $state(false);

  // Add form state
  let newName = $state("");
  let newDescription = $state("");
  let newValue = $state("");
  let saving = $state(false);

  onMount(loadCredentials);

  async function loadCredentials() {
    loading = true;
    try {
      const res = await api.get("/api/admin/credentials");
      if (res.ok) credentials = await res.json();
    } catch {
      // handled by api client
    } finally {
      loading = false;
    }
  }

  async function handleAdd(e) {
    e.preventDefault();
    saving = true;
    try {
      const res = await api.post("/api/admin/credentials", {
        name: newName,
        description: newDescription,
        value: newValue || undefined,
      });
      if (res.ok) {
        toasts.success("Credential created.");
        newName = "";
        newDescription = "";
        newValue = "";
        showAddForm = false;
        await loadCredentials();
      } else {
        const data = await res.json();
        toasts.error(data.detail || "Failed to create credential.");
      }
    } catch {
      toasts.error("Connection error.");
    } finally {
      saving = false;
    }
  }
</script>

<PageHeader title="Credentials">
  {#snippet action()}
    <Button onclick={() => (showAddForm = !showAddForm)}>
      {showAddForm ? "Cancel" : "Add Credential"}
    </Button>
  {/snippet}
</PageHeader>

{#if showAddForm}
  <Card>
    <form class="add-form" onsubmit={handleAdd}>
      <Input label="Name" bind:value={newName} mono placeholder="e.g. SIMPHONY_API_KEY" required />
      <Input label="Description" bind:value={newDescription} placeholder="What is this credential for?" />
      <Input label="Value" type="password" bind:value={newValue} mono placeholder="Secret value (optional)" />
      <div class="form-actions">
        <Button variant="secondary" onclick={() => (showAddForm = false)}>Cancel</Button>
        <Button type="submit" loading={saving}>Save Credential</Button>
      </div>
    </form>
  </Card>
{/if}

{#if loading}
  <p class="loading-text">Loading...</p>
{:else if credentials.length === 0}
  <EmptyState message="No credentials yet. Add one to get started." />
{:else}
  <div class="cred-list">
    {#each credentials as cred}
      <Card>
        <div class="cred-row">
          <div class="cred-info">
            <span class="cred-name mono">{cred.name}</span>
            {#if cred.description}
              <span class="cred-desc">{cred.description}</span>
            {/if}
          </div>
          <StatusPill status={cred.value_exists ? "value-set" : "no-value"} />
        </div>
      </Card>
    {/each}
  </div>
{/if}

<style>
  .add-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 0.5rem;
  }

  .loading-text {
    color: var(--text-muted);
    font-size: 0.875rem;
    padding: 1rem 0;
  }

  .cred-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .cred-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .cred-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .cred-name {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.875rem;
    color: var(--text-primary);
  }

  .cred-desc {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
