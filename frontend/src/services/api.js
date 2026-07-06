const configuredApiUrl = import.meta.env.VITE_API_URL;

if (!configuredApiUrl) {
  throw new Error("Missing VITE_API_URL. Set it to your deployed backend URL in the frontend environment.");
}

export const API_URL = configuredApiUrl.replace(/\/+$/, "");

let authToken = localStorage.getItem("sentinel_token");

export function setToken(token) {
  authToken = token;
}

export async function api(path, options = {}) {
  const apiPath = path.startsWith("/") ? path : `/${path}`;
  const headers = { ...(options.headers || {}) };
  let body = options.body;

  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  let response;
  try {
    response = await fetch(`${API_URL}${apiPath}`, {
      ...options,
      headers,
      body
    });
  } catch (error) {
    throw new Error(`Unable to reach API server at ${API_URL}. Please check VITE_API_URL and backend CORS settings.`);
  }

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    throw new Error(data?.detail || "Request failed");
  }
  return data;
}
