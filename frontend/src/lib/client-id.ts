const STORAGE_KEY = "tpa_client_id";

function generate(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function getClientId(): string {
  if (typeof window === "undefined") return ""; // SSR safety
  let id = localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = generate();
    localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}
