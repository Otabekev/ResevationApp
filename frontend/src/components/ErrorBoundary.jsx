import { Component } from "react";

const MESSAGES = {
  uz: { title: "Nimadir xato ketdi", body: "Iltimos, sahifani yangilang.", retry: "Qayta urinish" },
  ru: { title: "Что-то пошло не так", body: "Пожалуйста, обновите страницу.", retry: "Повторить" },
  en: { title: "Something went wrong", body: "Please refresh the page.", retry: "Reload" },
};

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Logged client-side; a real error tracker (Sentry) can hook in here.
    console.error("UI render error:", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    const lang = localStorage.getItem("lang") || "uz";
    const t = MESSAGES[lang] || MESSAGES.uz;
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", padding: 24 }}>
        <div className="card" style={{ maxWidth: 360, textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>{t.title}</h1>
          <p style={{ color: "var(--gray-500)", marginBottom: 20, fontSize: 14 }}>{t.body}</p>
          <button className="btn btn-primary btn-full" onClick={() => window.location.reload()}>
            {t.retry}
          </button>
        </div>
      </div>
    );
  }
}
