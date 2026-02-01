<script>
  import Input from "../components/Input.svelte";
  import Button from "../components/Button.svelte";
  import { navigate } from "../router.js";
  import { auth } from "../stores/auth.js";

  let password = $state("");
  let confirm = $state("");
  let error = $state("");
  let loading = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    error = "";

    if (password.length < 8) {
      error = "Password must be at least 8 characters.";
      return;
    }
    if (password !== confirm) {
      error = "Passwords do not match.";
      return;
    }

    loading = true;
    try {
      const res = await fetch("/api/admin/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await res.json();
      if (res.ok) {
        auth.setToken(data.token);
        navigate("overview");
      } else {
        error = data.detail || "Setup failed.";
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
    <p class="subtitle">Set your admin password to get started.</p>

    <form onsubmit={handleSubmit}>
      <div class="fields">
        <Input
          label="Password"
          type="password"
          bind:value={password}
          placeholder="Min. 8 characters"
          autocomplete="new-password"
          required
          minlength={8}
        />
        <Input
          label="Confirm Password"
          type="password"
          bind:value={confirm}
          placeholder="Confirm password"
          autocomplete="new-password"
          required
          minlength={8}
        />
      </div>
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <Button variant="primary" type="submit" {loading}>Create Account</Button>
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

  .fields {
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
