<script>
  import { onMount } from "svelte";
  import Card from "../components/Card.svelte";
  import PageHeader from "../components/PageHeader.svelte";
  import EmptyState from "../components/EmptyState.svelte";
  import StatusPill from "../components/StatusPill.svelte";
  import { api } from "../api.js";
  import { navigate } from "../router.js";

  let stats = $state({ stored_credentials: 0, active_profiles: 0, total_executions: 0 });
  let executions = $state([]);
  let loading = $state(true);

  onMount(async () => {
    try {
      const [statsRes, execRes] = await Promise.all([
        api.get("/api/admin/stats"),
        api.get("/api/admin/executions"),
      ]);
      if (statsRes.ok) stats = await statsRes.json();
      if (execRes.ok) executions = await execRes.json();
    } catch {
      // handled by api client
    } finally {
      loading = false;
    }
  });

  const statCards = $derived([
    { label: "Credentials", value: stats.stored_credentials, page: "credentials" },
    { label: "Profiles", value: stats.active_profiles, page: "profiles" },
    { label: "Executions", value: stats.total_executions, page: "executions" },
  ]);

  const recentExecutions = $derived(executions.slice(0, 5));
</script>

<PageHeader title="Overview" />

<div class="stat-grid">
  {#each statCards as card}
    <Card clickable onclick={() => navigate(card.page)}>
      <span class="stat-value">{card.value}</span>
      <span class="stat-label">{card.label}</span>
    </Card>
  {/each}
</div>

<section class="recent">
  <h2>Recent Executions</h2>
  {#if loading}
    <p class="loading-text">Loading...</p>
  {:else if recentExecutions.length === 0}
    <EmptyState message="No executions yet." />
  {:else}
    <div class="exec-list">
      {#each recentExecutions as exec}
        <div class="exec-row">
          <span class="exec-id mono">{exec.execution_id || exec.id}</span>
          <StatusPill status={exec.status} />
          {#if exec.execution_time_ms}
            <span class="exec-time">{exec.execution_time_ms}ms</span>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .stat-value {
    display: block;
    font-size: 2rem;
    font-weight: 700;
    color: var(--accent);
    line-height: 1.2;
  }

  .stat-label {
    display: block;
    font-size: 0.8125rem;
    color: var(--text-secondary);
    font-weight: 500;
    margin-top: 0.25rem;
  }

  .recent {
    margin-top: 1rem;
  }

  .recent h2 {
    font-size: 1.125rem;
    font-weight: 600;
    margin-bottom: 1rem;
  }

  .loading-text {
    color: var(--text-muted);
    font-size: 0.875rem;
    padding: 1rem 0;
  }

  .exec-list {
    display: flex;
    flex-direction: column;
  }

  .exec-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.625rem 0;
    border-bottom: 1px solid var(--border);
  }

  .exec-row:last-child {
    border-bottom: none;
  }

  .exec-id {
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }

  .exec-time {
    color: var(--text-muted);
    font-size: 0.75rem;
    margin-left: auto;
  }

  .mono {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
  }

  @media (max-width: 640px) {
    .stat-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
