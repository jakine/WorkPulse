function getCsrfToken() {
  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function formatError(data) {
  if (!data) return "Request failed.";
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map(String).join(" ");
  if (typeof data === "object") {
    return Object.entries(data)
      .map(([key, value]) => {
        const text = Array.isArray(value) ? value.map(String).join(" ") : String(value);
        return key === "non_field_errors" ? text : `${key}: ${text}`;
      })
      .join(" ");
  }
  return "Request failed.";
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (method !== "GET" && method !== "HEAD") {
    headers["X-CSRFToken"] = getCsrfToken();
  }

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return readResponse(response);
}

export async function apiUpload(path, formData) {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
    credentials: "include",
    body: formData,
  });
  return readResponse(response);
}

async function readResponse(response) {
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    const error = new Error(formatError(data));
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

export async function apiList(path) {
  const join = path.includes("?") ? "&" : "?";
  const data = await api(`${path}${join}page_size=100`);
  if (Array.isArray(data)) return data;
  return data.results || [];
}
