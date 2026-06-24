const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY || "";

async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Reminders
  getReminders: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/reminders${q ? "?" + q : ""}`);
  },
  createReminder: (body) =>
    request("/reminders", { method: "POST", body: JSON.stringify(body) }),
  updateReminder: (id, body, userId) => {
    const q = userId ? `?user_id=${userId}` : "";
    return request(`/reminders/${id}${q}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },
  deleteReminder: (id, userId) => {
    const q = userId ? `?user_id=${userId}` : "";
    return request(`/reminders/${id}${q}`, { method: "DELETE" });
  },
  snoozeReminder: (id, minutes, userId) => {
    const q = userId ? `?user_id=${userId}` : "";
    return request(`/reminders/${id}/snooze${q}`, {
      method: "POST",
      body: JSON.stringify({ minutes }),
    });
  },

  // Notes
  getNotes: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/notes${q ? "?" + q : ""}`);
  },
  createNote: (body) =>
    request("/notes", { method: "POST", body: JSON.stringify(body) }),
  deleteNote: (id, userId) => {
    const q = userId ? `?user_id=${userId}` : "";
    return request(`/notes/${id}${q}`, { method: "DELETE" });
  },

  // History
  getHistory: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/history${q ? "?" + q : ""}`);
  },

  // Users
  getUsers: () => request("/users"),
  updateTimezone: (userId, timezone) =>
    request(`/users/${userId}/timezone`, {
      method: "PATCH",
      body: JSON.stringify({ timezone }),
    }),
};
