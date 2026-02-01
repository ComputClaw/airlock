import { writable, derived } from "svelte/store";

const TOKEN_KEY = "airlock_session_token";

function createAuthStore() {
  const token = writable(sessionStorage.getItem(TOKEN_KEY));

  return {
    subscribe: token.subscribe,
    setToken(value) {
      sessionStorage.setItem(TOKEN_KEY, value);
      token.set(value);
    },
    clearToken() {
      sessionStorage.removeItem(TOKEN_KEY);
      token.set(null);
    },
    getToken() {
      return sessionStorage.getItem(TOKEN_KEY);
    },
  };
}

export const auth = createAuthStore();
export const isAuthenticated = derived(auth, ($auth) => !!$auth);
