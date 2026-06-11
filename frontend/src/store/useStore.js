import { create } from "zustand";

const _load = (key) => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const useStore = create((set) => ({
  // Auth
  user: _load("user"),
  accessToken: localStorage.getItem("access_token") || null,
  isAuthenticated: !!localStorage.getItem("access_token"),

  setAuth: (user, token, refreshToken) => {
    localStorage.setItem("access_token", token);
    if (refreshToken) localStorage.setItem("refresh_token", refreshToken);
    localStorage.setItem("user", JSON.stringify(user));
    set({ user, accessToken: token, isAuthenticated: true });
  },
  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("active_business");
    localStorage.removeItem("user");
    set({ user: null, accessToken: null, isAuthenticated: false, activeBusiness: null });
  },

  // Active business (owner context) — persisted across page refreshes
  activeBusiness: _load("active_business"),
  setActiveBusiness: (biz) => {
    if (biz) {
      localStorage.setItem("active_business", JSON.stringify(biz));
    } else {
      localStorage.removeItem("active_business");
    }
    set({ activeBusiness: biz });
  },

  // All businesses the owner has (for the topbar switcher)
  businesses: [],
  setBusinesses: (businesses) => set({ businesses }),

  // Language
  lang: localStorage.getItem("lang") || "uz",
  setLang: (lang) => {
    localStorage.setItem("lang", lang);
    set({ lang });
  },
}));

export default useStore;
