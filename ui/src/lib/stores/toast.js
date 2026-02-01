import { writable } from "svelte/store";

let nextId = 0;

function createToastStore() {
  const { subscribe, update } = writable([]);

  function add(message, type = "success") {
    const id = nextId++;
    update((items) => [...items, { id, message, type }]);
    setTimeout(() => remove(id), 3000);
  }

  function remove(id) {
    update((items) => items.filter((t) => t.id !== id));
  }

  return {
    subscribe,
    success: (msg) => add(msg, "success"),
    error: (msg) => add(msg, "error"),
    remove,
  };
}

export const toasts = createToastStore();
