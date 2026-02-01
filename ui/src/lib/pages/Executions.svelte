<script>
  import { onMount } from "svelte";
  import PageHeader from "../components/PageHeader.svelte";
  import StatusPill from "../components/StatusPill.svelte";
  import EmptyState from "../components/EmptyState.svelte";
  import { api } from "../api.js";

  let executions = $state([]);
  let loading = $state(true);
  let expandedId = $state(null);

  onMount(async () => {
    try {
      const res = await api.get("/api/admin/executions");
      if (res.ok) executions = await res.json();
    } catch {
      // handled by api client
    } finally {
      loading = false;
    }
  });

  function toggleExpand(id) {
    expandedId = expandedId === id ? null : id;
  }

  function formatTime(ms) {
    if (!ms) return "-";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  function formatDate(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    return d.toLocaleString();
  }

  function truncateId(id) {
    if (!id || id.length <= 16) return id;
    return id.slice(0, 16) + "...";
  }
</script>

<PageHeader title="Executions" />

{#if loading}
  <p class="loading-text">Loading...</p>
{:else if executions.length === 0}
  <EmptyState message="No executions yet." />
{:else}
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Time</th>
        </tr>
      </thead>
      <tbody>
        {#each executions as exec}
          <tr class="exec-row" class:expanded={expandedId === (exec.execution_id || exec.id)} onclick={() => toggleExpand(exec.execution_id || exec.id)}>
            <td class="mono">{truncateId(exec.execution_id || exec.id)}</td>
            <td><StatusPill status={exec.status} /></td>
            <td>{formatTime(exec.execution_time_ms)}</td>
            <td>{formatDate(exec.created_at)}</td>
          </tr>
          {#if expandedId === (exec.execution_id || exec.id)}
            <tr class="detail-row">
              <td colspan="4">
                <div class="detail">
                  {#if exec.script}
                    <div class="detail-block">
                      <h4>Script</h4>
                      <pre class="code-block">{exec.script}</pre>
                    </div>
                  {/if}
                  {#if exec.stdout}
                    <div class="detail-block">
                      <h4>stdout</h4>
                      <pre class="code-block">{exec.stdout}</pre>
                    </div>
                  {/if}
                  {#if exec.stderr}
                    <div class="detail-block">
                      <h4>stderr</h4>
                      <pre class="code-block stderr">{exec.stderr}</pre>
                    </div>
                  {/if}
                  {#if exec.result}
                    <div class="detail-block">
                      <h4>Result</h4>
                      <pre class="code-block">{JSON.stringify(exec.result, null, 2)}</pre>
                    </div>
                  {/if}
                  {#if exec.error}
                    <div class="detail-block">
                      <h4>Error</h4>
                      <pre class="code-block stderr">{exec.error}</pre>
                    </div>
                  {/if}
                </div>
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .loading-text {
    color: var(--text-muted);
    font-size: 0.875rem;
    padding: 1rem 0;
  }

  .table-wrapper {
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    text-align: left;
    padding: 0.625rem 0.75rem;
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid var(--border);
  }

  td {
    padding: 0.625rem 0.75rem;
    font-size: 0.875rem;
    border-bottom: 1px solid var(--border);
  }

  .exec-row {
    cursor: pointer;
    transition: background 150ms ease;
  }

  .exec-row:hover {
    background: var(--bg-raised);
  }

  .exec-row.expanded {
    background: var(--bg-raised);
  }

  .detail-row td {
    padding: 0;
    border-bottom: 1px solid var(--border);
  }

  .detail {
    padding: 1rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .detail-block h4 {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.375rem;
  }

  .code-block {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.8125rem;
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.75rem;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.5;
  }

  .code-block.stderr {
    color: var(--status-error);
  }

  .mono {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }
</style>
