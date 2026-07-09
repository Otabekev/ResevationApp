import axios from "axios";

// In production the frontend lives on Vercel and `/api/*` is rewritten to the
// Railway backend (see vercel.json) — same-origin from the browser, no CORS.
// For local dev or preview environments, set VITE_API_BASE_URL to point at a
// remote backend directly (e.g. https://<railway>/api/v1).
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

const api = axios.create({
  baseURL,
  timeout: 15000,
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// ── 401 handling with silent refresh ─────────────────────────────────────────
// On the first 401, try to rotate tokens with the stored refresh token; queue
// any requests that 401 while the refresh is in flight, then replay them.
// Only if refresh itself fails do we clear the session and go to /login.
let refreshing = null;

function hardLogout() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("active_business");
  if (!window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

async function refreshTokens() {
  const refresh_token = localStorage.getItem("refresh_token");
  if (!refresh_token) throw new Error("no refresh token");
  // Plain axios (not `api`) so this never loops through the interceptor.
  const { data } = await axios.post(`${baseURL}/auth/refresh`, { refresh_token }, { timeout: 15000 });
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  return data.access_token;
}

// ── Transient-failure retry ──────────────────────────────────────────────────
// The backend can be briefly unreachable through no fault of the request: a
// Railway redeploy restart, a Neon Postgres cold-start after idle, or a momentary
// network blip. Without a retry, that single hiccup bubbles straight up as a hard
// "error, try again" screen. So we transparently retry SAFE (idempotent) reads a
// few times with backoff before giving up — the user never sees the blip.
const MAX_RETRIES = 3;
const RETRY_BASE_MS = 600;

function isRetryable(config) {
  // Safe to replay through a transient blip: all reads, PLUS writes explicitly
  // flagged idempotent (e.g. "replace the whole week's working hours" — sending
  // it again changes nothing). Non-idempotent writes (create booking, add break)
  // are never auto-retried, so a blip can't double-create.
  const m = (config?.method || "get").toLowerCase();
  return m === "get" || m === "head" || config?.retryable === true;
}

function isTransient(err) {
  // No response at all = network error / timeout / connection refused (backend
  // restarting, DNS/edge not ready). 502/503/504 = the edge has no healthy
  // backend yet, or a gateway timeout. All of these recover on their own.
  if (!err.response) return true;
  return [502, 503, 504].includes(err.response.status);
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    const status = err.response?.status;

    if (status === 401 && original && !original._retried) {
      original._retried = true;
      try {
        refreshing = refreshing || refreshTokens();
        const newToken = await refreshing;
        refreshing = null;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        refreshing = null;
        hardLogout();
      }
    }

    // Retry transient backend unavailability (restart / cold-start / blip) on
    // idempotent requests with backoff (0.6s, 1.2s, 1.8s) so a momentary failure
    // doesn't surface as a hard error — covers reads and idempotent setup writes.
    if (original && isRetryable(original) && isTransient(err)) {
      original._retryCount = original._retryCount || 0;
      if (original._retryCount < MAX_RETRIES) {
        original._retryCount += 1;
        await new Promise((r) => setTimeout(r, RETRY_BASE_MS * original._retryCount));
        return api(original);
      }
    }

    return Promise.reject(err);
  }
);

export default api;

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authTelegram = (initData) =>
  api.post("/auth/telegram", { init_data: initData }).then((r) => r.data);

export const authTelegramWidget = (payload) =>
  api.post("/auth/telegram-widget", payload).then((r) => r.data);

// Bot deep-link login: the browser polls this with its nonce until the user
// confirms in the bot, at which point it returns the minted tokens (one-time).
export const pollWebLogin = (nonce) =>
  api.get(`/auth/tg-login/poll/${nonce}`).then((r) => r.data);

export const getMe = () => api.get("/auth/me").then((r) => r.data);
export const updateMyLanguage = (language) =>
  api.patch("/auth/me/language", { language }).then((r) => r.data);

// ── Businesses ────────────────────────────────────────────────────────────────
export const getCategories = () => api.get("/businesses/categories").then((r) => r.data);
// Telegram location handshake: the browser polls this with its nonce until the
// owner shares their business location in the bot, then it returns the coords.
export const pollLocationShare = (nonce) =>
  api.get(`/businesses/location-share/poll/${nonce}`).then((r) => r.data);
export const getMyBusinesses = () => api.get("/businesses/mine").then((r) => r.data);
export const getBusiness = (id) => api.get(`/businesses/${id}`).then((r) => r.data);
export const createBusiness = (data) => api.post("/businesses", data).then((r) => r.data);
export const updateBusiness = (id, data) => api.patch(`/businesses/${id}`, data, { retryable: true }).then((r) => r.data);

// ── Services ──────────────────────────────────────────────────────────────────
export const getServices = (bizId) => api.get(`/businesses/${bizId}/services/all`).then((r) => r.data);
export const createService = (bizId, data) => api.post(`/businesses/${bizId}/services`, data).then((r) => r.data);
export const updateService = (bizId, svcId, data) =>
  api.patch(`/businesses/${bizId}/services/${svcId}`, data, { retryable: true }).then((r) => r.data);
export const deleteService = (bizId, svcId) =>
  api.delete(`/businesses/${bizId}/services/${svcId}`);

// ── Staff ─────────────────────────────────────────────────────────────────────
export const getStaff = (bizId) => api.get(`/businesses/${bizId}/staff`).then((r) => r.data);
export const createStaff = (bizId, data) =>
  api.post(`/businesses/${bizId}/staff`, data).then((r) => r.data);
// Create a provider profile for the owner themselves (auto-linked, no invite).
export const addSelfProvider = (bizId, data = {}) =>
  api.post(`/businesses/${bizId}/staff/me`, data).then((r) => r.data);
export const updateStaff = (bizId, staffId, data) =>
  api.patch(`/businesses/${bizId}/staff/${staffId}`, data, { retryable: true }).then((r) => r.data);
export const deleteStaff = (bizId, staffId) =>
  api.delete(`/businesses/${bizId}/staff/${staffId}`).then((r) => r.data);
export const setStaffServices = (bizId, staffId, serviceIds) =>
  api.put(`/businesses/${bizId}/staff/${staffId}/services`, serviceIds, { retryable: true }).then((r) => r.data);
export const createStaffInvite = (bizId, staffId) =>
  api.post(`/businesses/${bizId}/staff/${staffId}/invite`).then((r) => r.data);

// ── Schedule ──────────────────────────────────────────────────────────────────
export const getWorkingHours = (bizId) =>
  api.get(`/businesses/${bizId}/working-hours`).then((r) => r.data);
export const setWorkingHours = (bizId, hours) =>
  api.put(`/businesses/${bizId}/working-hours`, { hours }, { retryable: true }).then((r) => r.data);
export const getStaffWorkingHours = (bizId, staffId) =>
  api.get(`/businesses/${bizId}/staff/${staffId}/working-hours`).then((r) => r.data);
export const setStaffWorkingHours = (bizId, staffId, hours) =>
  api.put(`/businesses/${bizId}/staff/${staffId}/working-hours`, { hours }, { retryable: true }).then((r) => r.data);
export const clearStaffWorkingHours = (bizId, staffId) =>
  api.delete(`/businesses/${bizId}/staff/${staffId}/working-hours`, { retryable: true });
export const getBreaks = (bizId) => api.get(`/businesses/${bizId}/breaks`).then((r) => r.data);
export const addBreak = (bizId, data) =>
  api.post(`/businesses/${bizId}/breaks`, data).then((r) => r.data);
export const deleteBreak = (bizId, breakId) =>
  api.delete(`/businesses/${bizId}/breaks/${breakId}`);
export const getBlockedTimes = (bizId) =>
  api.get(`/businesses/${bizId}/blocked-times`).then((r) => r.data);
export const addBlockedTime = (bizId, data) =>
  api.post(`/businesses/${bizId}/blocked-times`, data).then((r) => r.data);
export const deleteBlockedTime = (bizId, btId) =>
  api.delete(`/businesses/${bizId}/blocked-times/${btId}`);

// ── Availability ──────────────────────────────────────────────────────────────
export const getAvailability = (bizId, serviceId, date, staffId) =>
  api
    .get("/availability", {
      params: { business_id: bizId, service_id: serviceId, date, staff_id: staffId || undefined },
    })
    .then((r) => r.data);

// ── Bookings ──────────────────────────────────────────────────────────────────
export const getBookings = (bizId, params) =>
  api.get(`/businesses/${bizId}/bookings`, { params }).then((r) => r.data);
export const createManualBooking = (bizId, data) =>
  api.post(`/businesses/${bizId}/bookings`, data).then((r) => r.data);
export const updateBookingStatus = (bookingId, status) =>
  api.patch(`/bookings/${bookingId}/status`, { status }).then((r) => r.data);
export const cancelBooking = (bookingId, reason) =>
  api.patch(`/bookings/${bookingId}/cancel`, { reason }).then((r) => r.data);

// ── Analytics ─────────────────────────────────────────────────────────────────
export const getAnalytics = (bizId, days = 30) =>
  api.get(`/businesses/${bizId}/analytics`, { params: { days } }).then((r) => r.data);

// ── Admin ─────────────────────────────────────────────────────────────────────
export const getAdminStats = () => api.get("/admin/stats").then((r) => r.data);
export const getAdminBusinesses = (params) =>
  api.get("/admin/businesses", { params }).then((r) => r.data);
export const updateBusinessStatus = (bizId, status) =>
  api.patch(`/admin/businesses/${bizId}/status`, { status }).then((r) => r.data);
export const getAdminBusinessDetail = (bizId) =>
  api.get(`/admin/businesses/${bizId}/detail`).then((r) => r.data);
export const getAdminRecent = () => api.get("/admin/recent").then((r) => r.data);
export const getAdminUsers = (params) => api.get("/admin/users", { params }).then((r) => r.data);
export const setUserActive = (userId, is_active) =>
  api.patch(`/admin/users/${userId}/active`, { is_active }).then((r) => r.data);
export const getNeedsAttention = () => api.get("/admin/needs-attention").then((r) => r.data);
export const searchAdminBookings = (params) =>
  api.get("/admin/bookings/search", { params }).then((r) => r.data);
export const getAdminInsights = () => api.get("/admin/insights").then((r) => r.data);
export const getSystemHealth = () => api.get("/admin/system-health").then((r) => r.data);

// ── Broadcasts (super-admin announcements) ─────────────────────────────────────
export const getBroadcastAudienceCounts = () =>
  api.get("/admin/broadcast/audience-counts").then((r) => r.data);
export const getBroadcasts = () => api.get("/admin/broadcasts").then((r) => r.data);
export const createBroadcast = (data) => api.post("/admin/broadcast", data).then((r) => r.data);
export const sendBroadcastTest = (text) =>
  api.post("/admin/broadcast/test", { text }).then((r) => r.data);
export const cancelBroadcast = (id) =>
  api.post(`/admin/broadcasts/${id}/cancel`).then((r) => r.data);
