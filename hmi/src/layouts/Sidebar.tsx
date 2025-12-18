import { useState, useEffect, useCallback } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "../hooks/useTranslation";
import { logout as logoutService } from "../services/auth";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { logout as logoutAction } from "../store/slices/authSlice";

export function Sidebar() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [communicationsExpanded, setCommunicationsExpanded] = useState(
    location.pathname.startsWith("/communications")
  );
  const [tagsExpanded, setTagsExpanded] = useState(
    location.pathname.startsWith("/tags")
  );
  const [alarmsExpanded, setAlarmsExpanded] = useState(
    location.pathname.startsWith("/alarms")
  );
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [showLogoutModal, setShowLogoutModal] = useState(false);

  const isCommunicationsActive = location.pathname.startsWith("/communications");
  const isTagsActive = location.pathname.startsWith("/tags");
  const isAlarmsActive = location.pathname.startsWith("/alarms");

  const navItems = [
    { to: "/real-time-trends", icon: "bi bi-graph-up-arrow", labelKey: "navigation.realTimeTrends" },
    // { to: "/scada", icon: "bi bi-diagram-3", labelKey: "navigation.scada" },
    { to: "/machines", icon: "bi bi-cpu", labelKey: "navigation.machines" },
    { to: "/events", icon: "bi bi-calendar-event", labelKey: "navigation.events" },
    { to: "/operational-logs", icon: "bi bi-journal-text", labelKey: "navigation.operationalLogs" },
    { to: "/user-management", icon: "bi bi-people", labelKey: "navigation.userManagement" },
    { to: "/settings", icon: "bi bi-gear", labelKey: "navigation.settings" },
  ];

  const tagsSubItems = [
    { to: "/tags/definitions", labelKey: "sidebar.tags.definitions", icon: "bi bi-card-list" },
    { to: "/tags/datalogger", labelKey: "sidebar.tags.dataLogger", icon: "bi bi-database" },
    { to: "/tags/trends", labelKey: "sidebar.tags.trends", icon: "bi bi-graph-up" },
  ];

  const communicationsSubItems = [
    { to: "/communications/clients", labelKey: "sidebar.communications.clients", icon: "bi bi-hdd-network" },
    { to: "/communications/server", labelKey: "sidebar.communications.server", icon: "bi bi-server" },
  ];

  const alarmsSubItems = [
    { to: "/alarms/definitions", labelKey: "sidebar.alarms.definitions", icon: "bi bi-list-check" },
    { to: "/alarms/summary", labelKey: "sidebar.alarms.summary", icon: "bi bi-clipboard-data" },
  ];

  // Expandir automáticamente el menú de Communications cuando se navega a una ruta de communications
  useEffect(() => {
    if (location.pathname.startsWith("/communications")) {
      setCommunicationsExpanded(true);
    }
  }, [location.pathname]);

  // Expandir automáticamente el menú de Tags cuando se navega a una ruta de tags
  useEffect(() => {
    if (location.pathname.startsWith("/tags")) {
      setTagsExpanded(true);
    }
  }, [location.pathname]);

  // Expandir automáticamente el menú de Alarms cuando se navega a una ruta de alarms
  useEffect(() => {
    if (location.pathname.startsWith("/alarms")) {
      setAlarmsExpanded(true);
    }
  }, [location.pathname]);

  // Prevenir scroll del body cuando el modal está abierto
  useEffect(() => {
    if (showLogoutModal) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [showLogoutModal]);

  // Cerrar modal con ESC
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showLogoutModal && !isLoggingOut) {
        setShowLogoutModal(false);
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [showLogoutModal, isLoggingOut]);

  const handleLogoutClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setShowLogoutModal(true);
  }, []);

  const handleLogoutConfirm = useCallback(async () => {
    setShowLogoutModal(false);
    setIsLoggingOut(true);
    try {
      // Llamar al endpoint de logout
      await logoutService();
    } catch (error) {
      // Continuar con el logout incluso si hay error en el endpoint
      console.error("Error al hacer logout:", error);
    } finally {
      // Hacer logout en Redux
      dispatch(logoutAction());
      // Redirigir a login
      navigate("/login");
    }
  }, [dispatch, navigate]);

  return (
    <aside className="app-sidebar bg-body-secondary shadow" data-bs-theme="dark">
      <div className="sidebar-brand">
        <NavLink to="/dashboard" className="brand-link d-flex align-items-center justify-content-center">
          <span className="brand-text fw-light">PyAutomation</span>
        </NavLink>
      </div>
      <div className="sidebar-wrapper" style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 57px)" }}>
        <nav className="mt-2" style={{ flex: 1, overflowY: "auto" }}>
          <ul className="nav sidebar-menu flex-column" role="menu" data-lte-toggle="treeview" aria-label="Main navigation">
            {/* Communications con submenu desplegable */}
            <li className={`nav-item ${communicationsExpanded ? "menu-open" : ""}`}>
              <a
                href="#"
                className={`nav-link ${isCommunicationsActive ? "active" : ""} d-flex align-items-center justify-content-between`}
                onClick={(e) => {
                  e.preventDefault();
                  setCommunicationsExpanded(!communicationsExpanded);
                }}
                style={{ paddingRight: "1rem" }}
              >
                <div className="d-flex align-items-center">
                  <i className="nav-icon bi bi-hdd-network" />
                  <p className="mb-0">{t("sidebar.communications.title")}</p>
                </div>
                <i 
                  className={`bi ${communicationsExpanded ? "bi-chevron-down" : "bi-chevron-right"}`}
                  style={{ 
                    fontSize: "0.875rem",
                    transition: "transform 0.2s ease",
                    marginLeft: "auto"
                  }}
                />
              </a>
              <ul className="nav nav-treeview" style={{ display: communicationsExpanded ? "block" : "none" }}>
                {communicationsSubItems.map((subItem) => (
                  <li className="nav-item" key={subItem.to}>
                    <NavLink
                      to={subItem.to}
                      className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                      style={{ paddingLeft: "2rem" }}
                    >
                      <i className={`nav-icon ${subItem.icon}`} />
                      <p>{t(subItem.labelKey)}</p>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </li>
            
            {/* Tags con submenu desplegable */}
            <li className={`nav-item ${tagsExpanded ? "menu-open" : ""}`}>
              <a
                href="#"
                className={`nav-link ${isTagsActive ? "active" : ""} d-flex align-items-center justify-content-between`}
                onClick={(e) => {
                  e.preventDefault();
                  setTagsExpanded(!tagsExpanded);
                }}
                style={{ paddingRight: "1rem" }}
              >
                <div className="d-flex align-items-center">
                  <i className="nav-icon bi bi-tags" />
                  <p className="mb-0">{t("sidebar.tags.title")}</p>
                </div>
                <i 
                  className={`bi ${tagsExpanded ? "bi-chevron-down" : "bi-chevron-right"}`}
                  style={{ 
                    fontSize: "0.875rem",
                    transition: "transform 0.2s ease",
                    marginLeft: "auto"
                  }}
                />
              </a>
              <ul className="nav nav-treeview" style={{ display: tagsExpanded ? "block" : "none" }}>
                {tagsSubItems.map((subItem) => (
                  <li className="nav-item" key={subItem.to}>
                    <NavLink
                      to={subItem.to}
                      className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                      style={{ paddingLeft: "2rem" }}
                    >
                      <i className={`nav-icon ${subItem.icon}`} />
                      <p>{t(subItem.labelKey)}</p>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </li>
            
            {/* Alarms con submenu desplegable */}
            <li className={`nav-item ${alarmsExpanded ? "menu-open" : ""}`}>
              <a
                href="#"
                className={`nav-link ${isAlarmsActive ? "active" : ""} d-flex align-items-center justify-content-between`}
                onClick={(e) => {
                  e.preventDefault();
                  setAlarmsExpanded(!alarmsExpanded);
                }}
                style={{ paddingRight: "1rem" }}
              >
                <div className="d-flex align-items-center">
                  <i className="nav-icon bi bi-bell-fill" />
                  <p className="mb-0">{t("sidebar.alarms.title")}</p>
                </div>
                <i 
                  className={`bi ${alarmsExpanded ? "bi-chevron-down" : "bi-chevron-right"}`}
                  style={{ 
                    fontSize: "0.875rem",
                    transition: "transform 0.2s ease",
                    marginLeft: "auto"
                  }}
                />
              </a>
              <ul className="nav nav-treeview" style={{ display: alarmsExpanded ? "block" : "none" }}>
                {alarmsSubItems.map((subItem) => (
                  <li className="nav-item" key={subItem.to}>
                    <NavLink
                      to={subItem.to}
                      className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                      style={{ paddingLeft: "2rem" }}
                    >
                      <i className={`nav-icon ${subItem.icon}`} />
                      <p>{t(subItem.labelKey)}</p>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </li>
            
            {/* Otros items del menú */}
            {navItems.map((item) => (
              <li className="nav-item" key={item.to}>
                <NavLink to={item.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                  <i className={`nav-icon ${item.icon}`} />
                  <p>{t(item.labelKey)}</p>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        
        {/* Botón de Logout - Fuera del nav, fijo al final */}
        <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)", padding: "0.5rem 0", marginTop: "auto" }}>
          <ul className="nav sidebar-menu flex-column">
            <li className="nav-item">
              <a
                href="#"
                className="nav-link"
                role="button"
                onClick={handleLogoutClick}
                title={t("auth.logout")}
                style={{ cursor: isLoggingOut ? "wait" : "pointer" }}
              >
                <i className="nav-icon bi bi-box-arrow-right" />
                <p>
                  {isLoggingOut ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      {t("auth.loggingOut")}
                    </>
                  ) : (
                    t("auth.logout")
                  )}
                </p>
              </a>
            </li>
          </ul>
        </div>
      </div>

      {/* Modal de confirmación de logout */}
      {showLogoutModal && (
        <div
          className="modal fade show"
          style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            // Cerrar modal al hacer clic fuera del contenido
            if (e.target === e.currentTarget && !isLoggingOut) {
              setShowLogoutModal(false);
            }
          }}
        >
          <div className="modal-dialog modal-dialog-centered" role="document">
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h5 className="modal-title">{t("auth.logoutConfirm")}</h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={() => setShowLogoutModal(false)}
                  aria-label="Close"
                  disabled={isLoggingOut}
                ></button>
              </div>
              <div className="modal-body">
                <p>{t("auth.logoutConfirmMessage")}</p>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowLogoutModal(false)}
                  disabled={isLoggingOut}
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={handleLogoutConfirm}
                  disabled={isLoggingOut}
                >
                  {isLoggingOut ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      {t("auth.loggingOut")}
                    </>
                  ) : (
                    t("auth.signOut")
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}


