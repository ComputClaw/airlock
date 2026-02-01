<script>
  import { onMount } from "svelte";
  import PageHeader from "../components/PageHeader.svelte";
  import Button from "../components/Button.svelte";
  import Card from "../components/Card.svelte";
  import Input from "../components/Input.svelte";
  import StatusPill from "../components/StatusPill.svelte";
  import EmptyState from "../components/EmptyState.svelte";
  import { api } from "../api.js";
  import { navigate } from "../router.js";
  import { toasts } from "../stores/toast.js";

  let profiles = $state([]);
  let loading = $state(true);
  let showCreateForm = $state(false);

  let newDescription = $state("");
  let creating = $state(false);

  onMount(loadProfiles);

  async function loadProfiles() {
    loading = true;
    try {
      const res = await api.get("/api/admin/profiles");
      if (res.ok) profiles = await res.json();
    } catch {
      // handled by api client
    } finally {
      loading = false;
    }
  }

  async function handleCreate(e) {
    e.preventDefault();
    creating = true;
    try {
      const res = await api.post("/api/admin/profiles", {
        description: newDescription,
      });
      if (res.ok) {
        toasts.success("Profile created.");
        newDescription = "";
        showCreateForm = false;
        await loadProfiles();
      } else {
        const data = await res.json();
        toasts.error(data.detail || "Failed to create profile.");
      }
    } catch {
      toasts.error("Connection error.");
    } finally {
      creating = false;
    }
  }

  function truncateId(id) {
    if (!id || id.length <= 16) return id;
    return id.slice(0, 16) + "...";
  }
</script>

<PageHeader title="Profiles">
  {#snippet action()}
    <Button onclick={() => (showCreateForm = !showCreateForm)}>
      {showCreateForm ? "Cancel" : "Create Profile"}
    </Button>
  {/snippet}
</PageHeader>

{#if showCreateForm}
  <Card>
    <form class="create-form" onsubmit={handleCreate}>
      <Input label="Description" bind:value={newDescription} placeholder="What is this profile for?" />
      <div class="form-actions">
        <Button variant="secondary" onclick={() => (showCreateForm = false)}>Cancel</Button>
        <Button type="submit" loading={creating}>Create Profile</Button>
      </div>
    </form>
  </Card>
{/if}

{#if loading}
  <p class="loading-text">Loading...</p>
{:else if profiles.length === 0}
  <EmptyState message="No profiles yet. Create one to get started." />
{:else}
  <div class="profile-list">
    {#each profiles as profile}
      <Card clickable onclick={() => navigate("profile-detail", { id: profile.id })}>
        <div class="profile-row">
          <div class="profile-info">
            <span class="profile-id mono">{truncateId(profile.id)}</span>
            {#if profile.description}
              <span class="profile-desc">{profile.description}</span>
            {/if}
          </div>
          <div class="profile-meta">
            <StatusPill status={profile.locked ? "locked" : "unlocked"} />
            {#if profile.credential_count !== undefined}
              <span class="cred-count">{profile.credential_count} credentials</span>
            {/if}
          </div>
        </div>
      </Card>
    {/each}
  </div>
{/if}

<style>
  .create-form {
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

  .profile-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .profile-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .profile-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .profile-id {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.875rem;
    color: var(--text-primary);
  }

  .profile-desc {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .profile-meta {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-shrink: 0;
  }

  .cred-count {
    font-size: 0.75rem;
    color: var(--text-muted);
  }
</style>
