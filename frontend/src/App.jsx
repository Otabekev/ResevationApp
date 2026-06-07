import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { authTelegram, getMe } from "./api/client";
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

const DEV_BYPASS = import.meta.env.VITE_DEV_BYPASS_TELEGRAM === "true";

export default function App() {
  const { isAuthenticated, setAuth, user } = useStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const init = async () => {
      try {
        // Telegram Mini App auth
        const tg = window.Telegram?.WebApp;
        if (tg?.initData && !DEV_BYPASS) {
          const data = await authTelegram(tg.initData);
          setAuth({ id: data.user_id, name: data.name, role: data.role, language: data.language }, data.access_token);
          tg.ready();
          tg.expand();
        } else if (localStorage.getItem("access_token")) {
          const me = await getMe();
          setAuth(me, localStorage.getItem("access_token"));
        }
      } catch {
        // Not authenticated
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <div style={{ fontSize: 32 }}>⏳</div>
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
