import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/communications", icon: "bi bi-hdd-network", label: "Comunicaciones" },
  { to: "/tags", icon: "bi bi-tags", label: "Tags" },
  { to: "/alarms", icon: "bi bi-bell-fill", label: "Alarmas" },
  { to: "/machines", icon: "bi bi-cpu", label: "Machines" },
];

export function Sidebar() {
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
            {navItems.map((item) => (
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


