import React from "react";
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import AuthPage from "./pages/AuthPage";
import AnalyzePage from "./pages/AnalyzePage";
import ResultsPage from "./pages/ResultsPage";
import TrackerPage from "./pages/TrackerPage";
import "./index.css";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "40px", textAlign: "center" }}>
          <h2>Something went wrong.</h2>
          <button onClick={() => window.location.href = "/"}>Go Home</button>
        </div>
      );
    }
    return this.props.children;
  }
}

function Nav() {
  const { token, user, logout } = useAuth();
  const { pathname } = useLocation();
  if (!token || pathname === "/auth") return null;
  const displayName = user?.first_name || user?.email?.split("@")[0] || "?";
  const initials = displayName.slice(0, 2).toUpperCase();
  return (
    <nav className="navbar">
      <Link to="/tracker" className="brand">HireIQ</Link>
      <div className="nav-links">
        <Link to="/tracker">Tracker</Link>
        <button onClick={logout} className="btn-ghost">Sign Out</button>
        <div className="nav-avatar" title={displayName}>{initials}</div>
      </div>
    </nav>
  );
}

function ProtectedRoute({ children }) {
  const { token } = useAuth();
  return token ? children : <Navigate to="/auth" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Nav />
        <main className="main-content">
          <ErrorBoundary>
            <Routes>
              <Route path="/auth" element={<AuthPage />} />
              <Route path="/tracker" element={<ProtectedRoute><TrackerPage /></ProtectedRoute>} />
              <Route path="/analyze" element={<ProtectedRoute><AnalyzePage /></ProtectedRoute>} />
              <Route path="/results/:id" element={<ProtectedRoute><ResultsPage /></ProtectedRoute>} />
              <Route path="*" element={<Navigate to="/tracker" replace />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </AuthProvider>
    </BrowserRouter>
  );
}