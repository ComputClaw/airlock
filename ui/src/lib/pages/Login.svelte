<script>
  import Input from "../components/Input.svelte";
  import Button from "../components/Button.svelte";
  import { navigate } from "../router.js";
  import { auth } from "../stores/auth.js";

  let password = $state("");
  let error = $state("");
  let loading = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    error = "";
    loading = true;

    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (res.ok) {
        auth.setToken(data.token);
        navigate("overview");
      } else {
        error = data.detail || "Invalid password.";
      }
    } catch {
      error = "Cannot reach Airlock server.";
    } finally {
      loading = false;
    }
  }
</script>

<div class="auth-page">
  <div class="auth-card">
    <h1 class="wordmark">Airlock</h1>
    <p class="subtitle">Code execution trust boundary</p>

    <form onsubmit={handleSubmit}>
      <Input
        label="Password"
        type="password"
        bind:value={password}
        placeholder="Admin password"
        autocomplete="current-password"
        required
      />
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <Button variant="primary" type="submit" {loading}>Sign In</Button>
    </form>
  </div>
</div>

<style>
  .auth-page {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 1rem;
  }

  .auth-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2.5rem;
    width: 100%;
    max-width: 400px;
    text-align: center;
  }

  .wordmark {
    font-size: 1.75rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
  }

  .subtitle {
    color: var(--text-secondary);
    font-size: 0.875rem;
    margin-bottom: 2rem;
  }

  form {
    text-align: left;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .error {
    color: var(--status-error);
    font-size: 0.8125rem;
    text-align: center;
  }

  form :global(.btn) {
    width: 100%;
  }
</style>
