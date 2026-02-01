<script>
  import PageHeader from "../components/PageHeader.svelte";
  import Card from "../components/Card.svelte";
</script>

<PageHeader title="Settings" />

<div class="settings-grid">
  <Card>
    <h3 class="card-title">Export Data</h3>
    <p class="card-desc">Export credentials and profiles for backup or migration.</p>
    <p class="card-status">Coming soon</p>
  </Card>

  <Card>
    <h3 class="card-title">Import Data</h3>
    <p class="card-desc">Import credentials and profiles from a previous export.</p>
    <p class="card-status">Coming soon</p>
  </Card>
</div>

<Card>
  <h3 class="card-title">About Airlock</h3>
  <p class="card-desc">Code execution trust boundary for AI agents.</p>
  <p class="version mono">v0.1.0</p>
</Card>

<style>
  .settings-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .card-title {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.375rem;
  }

  .card-desc {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .card-status {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.75rem;
    font-style: italic;
  }

  .version {
    font-family: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
    font-size: 0.8125rem;
    color: var(--text-muted);
    margin-top: 0.5rem;
  }

  @media (max-width: 640px) {
    .settings-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
