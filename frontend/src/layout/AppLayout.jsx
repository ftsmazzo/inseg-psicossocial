import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api, clearToken } from "../api";
import BrandLogo from "../components/BrandLogo";

export default function AppLayout() {
  const nav = useNavigate();
  const location = useLocation();
  const [me, setMe] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    api("/api/auth/me")
      .then(setMe)
      .catch(() => {
        clearToken();
        nav("/login", { replace: true });
      });
  }, [nav]);

  function logout() {
    clearToken();
    nav("/login");
  }

  const onJobs = location.pathname === "/";
  const onWorkspace = location.pathname.startsWith("/jobs/");

  return (
    <div
      className={`hold-transition sidebar-mini layout-fixed ${
        sidebarOpen ? "" : "sidebar-collapse"
      }`.trim()}
    >
      <div className="wrapper">
        <nav className="main-header navbar navbar-expand navbar-white navbar-light border-bottom-0 inseg-navbar">
          <ul className="navbar-nav">
            <li className="nav-item">
              <button
                type="button"
                className="nav-link btn btn-link"
                onClick={() => setSidebarOpen((v) => !v)}
                aria-label="Alternar menu"
              >
                <i className="fas fa-bars" />
              </button>
            </li>
            <li className="nav-item d-none d-sm-inline-block">
              <Link to="/" className="nav-link">
                Jobs
              </Link>
            </li>
          </ul>

          <ul className="navbar-nav ml-auto align-items-center">
            {me && (
              <li className="nav-item d-none d-md-inline-block mr-2">
                <span className="nav-link text-muted py-0">
                  <i className="far fa-user mr-1" />
                  {me.name}
                </span>
              </li>
            )}
            <li className="nav-item">
              <button type="button" className="btn btn-inseg-outline btn-sm" onClick={logout}>
                <i className="fas fa-sign-out-alt mr-1" />
                Sair
              </button>
            </li>
          </ul>
        </nav>

        <aside className="main-sidebar sidebar-dark-primary elevation-4 inseg-sidebar">
          <Link to="/" className="brand-link inseg-brand-link border-bottom-0">
            <span className="inseg-brand-logo-box" aria-hidden="true">
              <img src="/img/inseg-logo.png" alt="" className="inseg-brand-logo-img" />
            </span>
            <span className="brand-text inseg-brand-text">Psicossocial</span>
          </Link>

          <div className="sidebar">
            <nav className="mt-2">
              <ul className="nav nav-pills nav-sidebar flex-column" role="menu">
                <li className="nav-item">
                  <Link to="/" className={`nav-link ${onJobs ? "active" : ""}`}>
                    <i className="nav-icon fas fa-folder-open" />
                    <p>Jobs</p>
                  </Link>
                </li>
                {onWorkspace && (
                  <li className="nav-item">
                    <span className="nav-link active">
                      <i className="nav-icon fas fa-file-medical-alt" />
                      <p>Revisão do job</p>
                    </span>
                  </li>
                )}
              </ul>
            </nav>
          </div>
        </aside>

        <div className="content-wrapper">
          <Outlet context={{ me }} />
        </div>

        <footer className="main-footer text-sm inseg-footer">
          <BrandLogo compact className="inseg-footer-logo" />
          <span className="ml-2">Psicossocial · Campanha CST → PGR Inseg</span>
        </footer>
      </div>
    </div>
  );
}
