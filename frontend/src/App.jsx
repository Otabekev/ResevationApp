import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { getMe, getMyBusinesses } from "./api/client";
import useStore from "./store/useStore";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Bookings from "./pages/Bookings";
import Services from "./pages/Services";
import Staff from "./pages/Staff";
import Schedule from "./pages/Schedule";
import Analytics from "./pages/Analytics";
import BusinessSetup from "./pages/BusinessSetup";
import Settings from "./pages/Settings";
import AdminPanel from "./pages/AdminPanel";
import Login from "./pages/Login";

export default function App() {
  const {
    isAuthenticated, setAuth, user,
    activeBusiness, setActiveBusiness, setBusinesses,
  } = useStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Hydrate from a stored JWT (set by the bot-login flow on /login).
    const init = async () => {
      try {
        if (localStorage.getItem("access_token")) {
          const me = await getMe();
          setAuth(me, localStorage.getItem("access_token"));

          // Load the owner's businesses once, centrally — the topbar switcher
          // and every page read them from the store.
          const bizList = await getMyBusinesses().catch(() => []);
          setBusinesses(bizList);
          const stillValid = activeBusiness && bizList.some((b) => b.id === activeBusiness.id);
          if (stillValid) {
            // refresh the stored copy with current data
            setActiveBusiness(bizList.find((b) => b.id === activeBusiness.id));
          } else {
            setActiveBusiness(bizList[0] || null);
          }
        }
      } catch {
        // Not authenticated — Login screen will render.
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <div className="skeleton" style={{ width: 160, height: 24, borderRadius: "var(--radius-sm)" }} />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    );
  }

  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/services" element={<Services />} />
          <Route path="/staff" element={<Staff />} />
          <Route path="/schedule" element={<Schedule />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/setup" element={<BusinessSetup />} />
          <Route path="/settings" element={<Settings />} />
          {user?.role === "super_admin" && <Route path="/admin" element={<AdminPanel />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
