import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";

const navItems = [
  { to: "/communications", icon: "bi bi-hdd-network", label: "Communications" },
  // { to: "/machines", icon: "bi bi-cpu", label: "Machines" },
  { to: "/events", icon: "bi bi-calendar-event", label: "Events" },
  { to: "/operational-logs", icon: "bi bi-journal-text", label: "Operational Logs" },
  // { to: "/performance", icon: "bi bi-speedometer2", label: "Performance" },
  { to: "/user-management", icon: "bi bi-people", label: "User Management" },
  { to: "/settings", icon: "bi bi-gear", label: "Settings" },
];

const tagsSubItems = [
  { to: "/tags/definitions", label: "Definitions" },
  { to: "/tags/datalogger", label: "DataLogger" },
  { to: "/tags/trends", label: "Trends" },
];

const alarmsSubItems = [
  { to: "/alarms/definitions", label: "Definitions" },
  { to: "/alarms/summary", label: "Summary" },
];

export function Sidebar() {
  const location = useLocation();
  const [tagsExpanded, setTagsExpanded] = useState(
    location.pathname.startsWith("/tags")
  );
  const [alarmsExpanded, setAlarmsExpanded] = useState(
    location.pathname.startsWith("/alarms")
  );

  const isTagsActive = location.pathname.startsWith("/tags");
  const isAlarmsActive = location.pathname.startsWith("/alarms");

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

  return (
    <aside className="app-sidebar bg-body-secondary shadow" data-bs-theme="dark">
      <div className="sidebar-brand">
        <NavLink to="/dashboard" className="brand-link d-flex align-items-center justify-content-center">
          <span className="brand-text fw-light">PyAutomation</span>
        </NavLink>
      </div>
      <div className="sidebar-wrapper">
        <nav className="mt-2">
          <ul className="nav sidebar-menu flex-column" role="menu" data-lte-toggle="treeview" aria-label="Main navigation">
            {/* Communications */}
            <li className="nav-item">
              <NavLink to="/communications" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                <i className="nav-icon bi bi-hdd-network" />
                <p>Communications</p>
              </NavLink>
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
                  <p className="mb-0">Tags</p>
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
                      <i className="nav-icon bi bi-circle" style={{ fontSize: "0.5rem" }} />
                      <p>{subItem.label}</p>
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
                  <p className="mb-0">Alarms</p>
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
                      <i className="nav-icon bi bi-circle" style={{ fontSize: "0.5rem" }} />
                      <p>{subItem.label}</p>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </li>
            
            {/* Otros items del menú */}
            {navItems.slice(1).map((item) => (
              <li className="nav-item" key={item.to}>
                <NavLink to={item.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                  <i className={`nav-icon ${item.icon}`} />
                  <p>{item.label}</p>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </aside>
  );
}


