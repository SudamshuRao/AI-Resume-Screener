import axios from "axios";

const LOG = "[API]";

const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL}/api/v1`,
});

// ── Request interceptor: attach JWT + log outgoing calls ──────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    console.log(
      `${LOG} → ${config.method?.toUpperCase()} ${config.baseURL}${config.url}`,
      config.params || config.data || ""
    );
    return config;
  },
  (error) => {
    console.error(`${LOG} Request setup error:`, error);
    return Promise.reject(error);
  }
);

// ── Response interceptor: log responses + handle 401 auto-logout ──────────────
api.interceptors.response.use(
  (response) => {
    console.log(
      `${LOG} ← ${response.status} ${response.config.method?.toUpperCase()} ${response.config.url}`
    );
    return response;
  },
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url ?? "unknown";
    const method = error.config?.method?.toUpperCase() ?? "?";
    const detail = error.response?.data?.detail ?? error.message;

    console.error(
      `${LOG} ✗ ${status ?? "ERR"} ${method} ${url} — ${detail}`,
      error.response?.data ?? error
    );

    // Auto-logout on 401 (expired / invalid token)
    if (status === 401) {
      console.warn(`${LOG} 401 received — clearing session`);
      localStorage.removeItem("token");
      // Dispatch a custom event so AuthContext can react without a hard page reload
      if (!window.location.pathname.startsWith("/auth")) {
        window.dispatchEvent(new Event("session:expired"));
      }
    }

    return Promise.reject(error);
  }
);

export default api;