import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { setToken } from "../api";
import BrandLogo from "../components/BrandLogo";

export default function Login() {
  const nav = useNavigate();
  const [email, setEmail] = useState("admin@inseg.local");
  const [password, setPassword] = useState("inseg123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const body = new URLSearchParams();
      body.set("username", email);
      body.set("password", password);
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Falha no login");
      setToken(data.access_token);
      nav("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-box inseg-login-box">
        <div className="login-logo inseg-login-logo">
          <BrandLogo />
          <p className="inseg-login-tagline mb-0">Psicossocial · NR-01</p>
        </div>

        <div className="card card-outline card-primary inseg-login-card">
          <div className="card-body login-card-body">
            <p className="login-box-msg">
              Campanha CST → revisão técnica → PGR Inseg atualizado.
            </p>

            <form onSubmit={onSubmit}>
              <div className="input-group mb-3">
                <input
                  type="email"
                  className="form-control"
                  placeholder="E-mail"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                />
                <div className="input-group-append">
                  <div className="input-group-text">
                    <span className="fas fa-envelope" />
                  </div>
                </div>
              </div>

              <div className="input-group mb-3">
                <input
                  type="password"
                  className="form-control"
                  placeholder="Senha"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
                <div className="input-group-append">
                  <div className="input-group-text">
                    <span className="fas fa-lock" />
                  </div>
                </div>
              </div>

              {error && (
                <div className="alert alert-danger py-2" role="alert">
                  {error}
                </div>
              )}

              <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
                {loading ? (
                  <>
                    <i className="fas fa-spinner fa-spin mr-1" />
                    Entrando…
                  </>
                ) : (
                  "Entrar"
                )}
              </button>
            </form>
          </div>
        </div>

        <p className="text-center inseg-login-footer mt-3 mb-0 small">
          Consultoria em Segurança do Trabalho
        </p>
      </div>
    </div>
  );
}
