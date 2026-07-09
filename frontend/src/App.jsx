import { lazy, Suspense, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { getMe, getMyBusinesses } from "./api/client";
import useStore from "./store/useStore";
import Layout from "./components/Layout";
import Login from "./pages/Login";

// Route components are code-split: the initial load only ships the app shell +
// the landing route, and the rest stream in on navigation (and are precached by
// the service worker, so repeat navigations are instant). Keeps the first paint
// small on mid-range Androids. Login stays eager — it's the auth gate.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Bookings = lazy(() => import("./pages/Bookings"));
const Services = lazy(() => import("./pages/Services"));
const Staff = lazy(() => import("./pages/Staff"));
const Schedule = lazy(() => import("./pages/Schedule"));
const Analytics = lazy(() => import("./pages/Analytics"));
const BusinessSetup = lazy(() => import("./pages/BusinessSetup"));
const Settings = lazy(() => import("./pages/Settings"));
const AdminOverview = lazy(() => import("./pages/AdminOverview"));
const AdminBusinesses = lazy(() => import("./pages/AdminBusinesses"));
const AdminBusinessDetail = lazy(() => import("./pages/AdminBusinessDetail"));
const AdminUsers = lazy(() => import("./pages/AdminUsers"));
const AdminBookings = lazy(() => import("./pages/AdminBookings"));
const AdminBroadcast = lazy(() => import("./pages/AdminBroadcast"));

function PageFallback() {
  return (
    <div style={{ padding: "var(--space-6)" }}>
      <div className="skeleton" style={{ height: 120, borderRadius: "var(--radius-md)" }} />
    </div>
  );
}

export default function App() {
  const {
    isAuthenticated, setAuth, user,
    activeBusiness, setActiveBusiness, setBusinesses,
  } = useStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Hydrate from a stored JWT (set by the bot-login flow on /login).
    const init = async () => {
      const token = localStorage.getItem("access_token");
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        // Fire both calls in parallel. getMyBusinesses only needs the stored
        // token (the axios interceptor attaches it), so there's no reason to
        // wait for getMe first — that serial chain cost a full extra backend
        // round-trip on every cold open. A super_admin owns no businesses, so
        // that call 403s → caught as [] and ignored in the role branch below.
        const [me, bizList] = await Promise.all([
          getMe(),
          getMyBusinesses().catch(() => []),
        ]);
        setAuth(me, token);

        if (me.role !== "super_admin") {
          setBusinesses(bizList);
          const stillValid = activeBusiness && bizList.some((b) => b.id === activeBusiness.id);
          setActiveBusiness(stillValid ? bizList.find((b) => b.id === activeBusiness.id) : (bizList[0] || null));
        } else {
          setBusinesses([]);
          setActiveBusiness(null);
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

  const isAdmin = user?.role === "super_admin";

  return (
    <BrowserRouter>
      <Layout>
        <Suspense fallback={<PageFallback />}>
          {isAdmin ? (
            // Super_admin world: only platform-management routes. Owner pages
            // would render empty (no business), so we hide them entirely.
            <Routes>
              <Route path="/" element={<AdminOverview />} />
              <Route path="/admin/businesses" element={<AdminBusinesses />} />
              <Route path="/admin/businesses/:id" element={<AdminBusinessDetail />} />
              <Route path="/admin/users" element={<AdminUsers />} />
              <Route path="/admin/bookings" element={<AdminBookings />} />
              <Route path="/admin/broadcast" element={<AdminBroadcast />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          ) : (
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/bookings" element={<Bookings />} />
              <Route path="/services" element={<Services />} />
              <Route path="/staff" element={<Staff />} />
              <Route path="/schedule" element={<Schedule />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/setup" element={<BusinessSetup />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          )}
        </Suspense>
      </Layout>
    </BrowserRouter>
  );
}
