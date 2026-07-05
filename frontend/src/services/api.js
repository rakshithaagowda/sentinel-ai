export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

let authToken = localStorage.getItem("sentinel_token");

export function setToken(token) {
  authToken = token;
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  let body = options.body;

  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    body
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    throw new Error(data?.detail || "Request failed");
  }
  return data;
}
