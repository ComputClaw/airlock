<script>
  import { onMount } from "svelte";
  import Card from "../components/Card.svelte";
  import Button from "../components/Button.svelte";
  import StatusPill from "../components/StatusPill.svelte";
  import ConfirmDialog from "../components/ConfirmDialog.svelte";
  import EmptyState from "../components/EmptyState.svelte";
  import { api } from "../api.js";
  import { navigate } from "../router.js";
  import { toasts } from "../stores/toast.js";

  /** @type {{ id: string }} */
  let { id } = $props();

  let profile = $state(null);
  let loading = $state(true);
  let showLockConfirm = $state(false);
  let showRevokeConfirm = $state(false);
  let copied = $state(false);

  onMount(loadProfile);

  async function loadProfile() {
    loading = true;
    try {
      const res = await api.get(`/api/admin/profiles/${id}`);
      if (res.ok) {
        profile = await res.json();
      } else {
        toasts.error("Profile not found.");
        navigate("profiles");
      }
    } catch {
      // handled by api client
    } finally {
      loading = false;
    }
  }

  async function handleLock() {
    try {
      const res = await api.post(`/api/admin/profiles/${id}/lock`);
      if (res.ok) {
        toasts.success("Profile locked.");
        await loadProfile();
      } else {
        const data = await res.json();
        toasts.error(data.detail || "Failed to lock profile.");
      }
    } catch {
      toasts.error("Connection error.");
    }
  }

  async function handleRevoke() {
    try {
      const res = await api.post(`/api/admin/profiles/${id}/revoke`);
      if (res.ok) {
        toasts.success("Profile revoked.");
        await loadProfile();
      } else {
        const data = await res.json();
        toasts.error(data.detail || "Failed to revoke profile.");
      }
    } catch {
      toasts.error("Connection error.");
    }
  }

  async function copyId() {
    try {
      await navigator.clipboard.writeText(id);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch {
      toasts.error("Failed to copy.");
    }
  }
</script>

{#if loading}
  <p class="loading-text">Loading...</p>
{:else if profile}
  <div class="detail-header">
    <button class="back" onclick={() => navigate("profiles")}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
      Profiles
    </button>
  </div>

  <div class="status-banner" class:locked={profile.locked} class:unlocked={!profile.locked} class:revoked={profile.revoked}>
    <StatusPill status={profile.revoked ? "revoked" : profile.locked ? "locked" : "unlocked"} />
    <span class="profile-id mono">{profile.id}</span>
    {#if profile.locked && !profile.revoked}
      <button class="copy-btn" onclick={copyId}>
        {copied ? "Copied!" : "Copy ID"}
      </button>
    {/if}
  </div>

  {#if profile.description}
    <Card>
      <h3 class="section-label">Description</h3>
      <p class="description">{profile.description}</p>
    </Card>
  {/if}

  <section class="credentials-section">
    <h3 class="section-label">Credentials</h3>
    {#if profile.credentials && profile.credentials.length > 0}
      <div class="cred-list">
        {#each profile.credentials as cred}
          <div class="cred-row">
            <span class="cred-name mono">{cred.name}</span>
            <StatusPill status={cred.value_exists ? "value-set" : "no-value"} />
          </div>
        {/each}
      </div>
    {:else}
      <EmptyState message="No credentials attached to this profile." />
    {/if}
  </section>

  {#if !profile.locked && !profile.revoked}
    <div class="actions">
      <Button variant="primary" onclick={() => (showLockConfirm = true)}>Lock Profile</Button>
    </div>
  {:else if profile.locked && !profile.revoked}
    <div class="actions">
      <Button variant="danger" onclick={() => (showRevokeConfirm = true)}>Revoke Profile</Button>
    </div>
  {/if}

  <ConfirmDialog
    bind:open={showLockConfirm}
    title="Lock Profile"
    message="Once locked, credentials cannot be added or removed. This cannot be undone."
    confirmLabel="Lock Profile"
    variant="primary"
    onconfirm={handleLock}
  />

  <ConfirmDialog
    bind:open={showRevokeConfirm}
    title="Revoke Profile"
    message="This profile will no longer be able to execute scripts. This cannot be undone."
    confirmLabel="Revoke"
    variant="danger"
    onconfirm={handleRevoke}
  />
{/if}

<style>
  .loading-text {
    color: var(--text-muted);
    font-size: 0.875rem;
    padding: 1rem 0;
  }

  .detail-header {
    margin-bottom: 1rem;
  }

  .back {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
    font-weight: 500;
    transition: color 150ms ease;
  }

  .back:hover {
    color: var(--text-primary);
  }

  .status-banner {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.25rem;
    border-radius: var(--radius);
    margin-bottom: 1rem;
    border: 1px solid var(--border);
  }

  .status-banner.locked {
    background: rgba(34, 197, 94, 0.04);
  }

  .status-banner.unlocked {
    background: rgba(245, 158, 11, 0.04);
  }

  .status-banner.revoked {
    background: rgba(239, 68, 68, 0.04);
  }

  .profile-id {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.875rem;
    color: var(--text-secondary);
  }

  .copy-btn {
    margin-left: auto;
    padding: 0.25rem 0.625rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    transition: color 150ms ease, border-color 150ms ease;
  }

  .copy-btn:hover {
    color: var(--text-primary);
    border-color: var(--border-hover);
  }

  .section-label {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 0.75rem;
  }

  .description {
    font-size: 0.875rem;
    color: var(--text-primary);
    line-height: 1.5;
  }

  .credentials-section {
    margin-top: 1.5rem;
  }

  .cred-list {
    display: flex;
    flex-direction: column;
  }

  .cred-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
  }

  .cred-row:last-child {
    border-bottom: none;
  }

  .cred-name {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.8125rem;
    color: var(--text-primary);
  }

  .actions {
    margin-top: 2rem;
    display: flex;
    gap: 0.5rem;
  }
</style>
