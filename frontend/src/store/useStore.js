import { create } from "zustand";

const _loadBusiness = () => {
  try {
    const raw = localStorage.getItem("active_business");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const useStore = create((set, get) => ({
  // Auth
  user: null,
  accessToken: localStorage.getItem("access_token") || null,
  isAuthenticated: !!localStorage.getItem("access_token"),

  setAuth: (user, token) => {
    localStorage.setItem("access_token", token);
    set({ user, accessToken: token, isAuthenticated: true });
  },
  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("active_business");
    set({ user: null, accessToken: null, isAuthenticated: false, activeBusiness: null });
  },

  // Active business (owner context) — persisted across page refreshes
  activeBusiness: _loadBusiness(),
  setActiveBusiness: (biz) => {
    if (biz) {
      localStorage.setItem("active_business", JSON.stringify(biz));
    } else {
      localStorage.removeItem("active_business");
    }
    set({ activeBusiness: biz });
  },

  // Language
  lang: localStorage.getItem("lang") || "uz",
  setLang: (lang) => {
    localStorage.setItem("lang", lang);
    set({ lang });
  },
}));

export default useStore;
