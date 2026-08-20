import { createContext, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";

const LOG = "[AuthContext]";
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const storedToken = localStorage.getItem("token");
  let initialToken = null;
  if (storedToken) {
    try {
      const payload = JSON.parse(atob(storedToken.split(".")[1]));
      if (payload.exp * 1000 > Date.now()) {
        initialToken = storedToken;
      } else {
        localStorage.removeItem("token");
      }
    } catch {
      localStorage.removeItem("token");
    }
  }
  const [token, setToken] = useState(initialToken);
  const [user, setUser]   = useState(null);
  const navigate = useNavigate();

  // Listen for session:expired events dispatched by the API client on 401
  useEffect(() => {
    const handleExpiry = () => {
      setToken(null);
      setUser(null);
      navigate("/auth", { replace: true });
    };
    window.addEventListener("session:expired", handleExpiry);
    return () => window.removeEventListener("session:expired", handleExpiry);
  }, [navigate]);

  const fetchMe = async () => {
    try {
      const res = await api.get("/me");
      setUser(res.data);
    } catch (err) {
      console.warn(`${LOG} fetchMe failed:`, err.message);
    }
  };

  const requestOtp = async (email) => {
    const res = await api.post("/otp/request", { email });
    return res.data.otp ?? null;
  };

  const verifyOtp = async (email, otp) => {
    const res = await api.post("/otp/verify", { email, otp });
    localStorage.setItem("token", res.data.access_token);
    setToken(res.data.access_token);
    await fetchMe();
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, requestOtp, verifyOtp, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);