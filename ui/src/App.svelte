<script>
  import { onMount } from "svelte";
  import { route, navigate, initRouter } from "./lib/router.js";
  import { auth, isAuthenticated } from "./lib/stores/auth.js";
  import Sidebar from "./lib/components/Sidebar.svelte";
  import ToastContainer from "./lib/components/ToastContainer.svelte";
  import Setup from "./lib/pages/Setup.svelte";
  import Login from "./lib/pages/Login.svelte";
  import Overview from "./lib/pages/Overview.svelte";
  import Credentials from "./lib/pages/Credentials.svelte";
  import Profiles from "./lib/pages/Profiles.svelte";
  import ProfileDetail from "./lib/pages/ProfileDetail.svelte";
  import Executions from "./lib/pages/Executions.svelte";
  import Settings from "./lib/pages/Settings.svelte";

  let ready = $state(false);

  onMount(async () => {
    try {
      // Check if setup is needed
      const statusRes = await fetch("/api/admin/status");
      const statusData = await statusRes.json();

      if (statusData.setup_required) {
        navigate("setup");
        ready = true;
        return;
      }

      // Check if we have a valid token
      const token = auth.getToken();
      if (token) {
        const statsRes = await fetch("/api/admin/stats", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (statsRes.ok) {
          initRouter();
          ready = true;
          return;
        }
        // Token invalid
        auth.clearToken();
      }

      // Not authenticated
      navigate("login");
      ready = true;
    } catch {
      // Server unreachable — show login and let it handle errors
      navigate("login");
      ready = true;
    }
  });

  let isAuthPage = $derived($route.page === "setup" || $route.page === "login");
</script>

{#if !ready}
  <div class="loading">
    <p>Loading...</p>
  </div>
{:else if isAuthPage}
  {#if $route.page === "setup"}
    <Setup />
  {:else}
    <Login />
  {/if}
{:else}
  <Sidebar />
  <main class="content">
    {#if $route.page === "overview"}
      <Overview />
    {:else if $route.page === "credentials"}
      <Credentials />
    {:else if $route.page === "profiles"}
      <Profiles />
    {:else if $route.page === "profile-detail"}
      <ProfileDetail id={$route.params.id} />
    {:else if $route.page === "executions"}
      <Executions />
    {:else if $route.page === "settings"}
      <Settings />
    {:else}
      <Overview />
    {/if}
  </main>
{/if}

<ToastContainer />

<style>
  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    color: var(--text-muted);
    font-size: 0.875rem;
  }

  .content {
    margin-left: var(--sidebar-width);
    padding: 2rem;
    max-width: calc(var(--content-max-width) + var(--sidebar-width) + 4rem);
  }
</style>
