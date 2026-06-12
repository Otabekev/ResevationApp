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
export const getMyBusinesses = () => api.get("/businesses/mine").then((r) => r.data);
export const getBusiness = (id) => api.get(`/businesses/${id}`).then((r) => r.data);
export const createBusiness = (data) => api.post("/businesses", data).then((r) => r.data);
export const updateBusiness = (id, data) => api.patch(`/businesses/${id}`, data).then((r) => r.data);

// ── Services ──────────────────────────────────────────────────────────────────
export const getServices = (bizId) => api.get(`/businesses/${bizId}/services/all`).then((r) => r.data);
export const createService = (bizId, data) => api.post(`/businesses/${bizId}/services`, data).then((r) => r.data);
export const updateService = (bizId, svcId, data) =>
  api.patch(`/businesses/${bizId}/services/${svcId}`, data).then((r) => r.data);
export const deleteService = (bizId, svcId) =>
  api.delete(`/businesses/${bizId}/services/${svcId}`);

// ── Staff ─────────────────────────────────────────────────────────────────────
export const getStaff = (bizId) => api.get(`/businesses/${bizId}/staff`).then((r) => r.data);
export const createStaff = (bizId, data) =>
  api.post(`/businesses/${bizId}/staff`, data).then((r) => r.data);
export const updateStaff = (bizId, staffId, data) =>
  api.patch(`/businesses/${bizId}/staff/${staffId}`, data).then((r) => r.data);
export const setStaffServices = (bizId, staffId, serviceIds) =>
  api.put(`/businesses/${bizId}/staff/${staffId}/services`, serviceIds).then((r) => r.data);
export const createStaffInvite = (bizId, staffId) =>
  api.post(`/businesses/${bizId}/staff/${staffId}/invite`).then((r) => r.data);

// ── Schedule ──────────────────────────────────────────────────────────────────
export const getWorkingHours = (bizId) =>
  api.get(`/businesses/${bizId}/working-hours`).then((r) => r.data);
export const setWorkingHours = (bizId, hours) =>
  api.put(`/businesses/${bizId}/working-hours`, { hours }).then((r) => r.data);
export const getStaffWorkingHours = (bizId, staffId) =>
  api.get(`/businesses/${bizId}/staff/${staffId}/working-hours`).then((r) => r.data);
export const setStaffWorkingHours = (bizId, staffId, hours) =>
  api.put(`/businesses/${bizId}/staff/${staffId}/working-hours`, { hours }).then((r) => r.data);
export const clearStaffWorkingHours = (bizId, staffId) =>
  api.delete(`/businesses/${bizId}/staff/${staffId}/working-hours`);
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
