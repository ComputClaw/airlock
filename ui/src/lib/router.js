import { writable } from "svelte/store";

/** @typedef {{ page: string, params: Record<string, string> }} Route */

/** @type {import('svelte/store').Writable<Route>} */
export const route = writable({ page: "overview", params: {} });

/** Parse the current URL path into a route object. */
function parsePath(path = window.location.pathname) {
  const clean = path.replace(/\/+$/, "") || "/";

  if (clean === "/setup") return { page: "setup", params: {} };
  if (clean === "/login") return { page: "login", params: {} };
  if (clean === "/" || clean === "/overview") return { page: "overview", params: {} };
  if (clean === "/credentials") return { page: "credentials", params: {} };
  if (clean === "/executions") return { page: "executions", params: {} };
  if (clean === "/settings") return { page: "settings", params: {} };

  // /profiles/:id
  const profileMatch = clean.match(/^\/profiles\/([^/]+)$/);
  if (profileMatch) return { page: "profile-detail", params: { id: profileMatch[1] } };

  if (clean === "/profiles") return { page: "profiles", params: {} };

  // Fallback
  return { page: "overview", params: {} };
}

/** Navigate to a new page. */
export function navigate(page, params = {}) {
  let path;
  switch (page) {
    case "setup": path = "/setup"; break;
    case "login": path = "/login"; break;
    case "overview": path = "/overview"; break;
    case "credentials": path = "/credentials"; break;
    case "profiles": path = "/profiles"; break;
    case "profile-detail": path = `/profiles/${params.id}`; break;
    case "executions": path = "/executions"; break;
    case "settings": path = "/settings"; break;
    default: path = "/overview";
  }

  history.pushState(null, "", path);
  route.set({ page, params });
}

/** Initialize the router — parse current URL and listen for back/forward. */
export function initRouter() {
  route.set(parsePath());

  window.addEventListener("popstate", () => {
    route.set(parsePath());
  });
}
