import { useCallback, useEffect, useState } from "react";

export function Header() {
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [dbType, setDbType] = useState<"postgres" | "mysql" | "sqlite">("postgres");
  const [dbName, setDbName] = useState("");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState<string>("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [dbConnected, setDbConnected] = useState(false);

  const toggleSidebar = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const bodyCls = document.body.classList;
    const wrapper = document.querySelector(".app-wrapper");
    const wrapperCls = wrapper?.classList;

    const isOpen = bodyCls.contains("sidebar-open") || wrapperCls?.contains("sidebar-open");

    if (isOpen) {
      bodyCls.remove("sidebar-open");
      bodyCls.add("sidebar-collapse");
      wrapperCls?.remove("sidebar-open");
      wrapperCls?.add("sidebar-collapse");
    } else {
      bodyCls.add("sidebar-open");
      bodyCls.remove("sidebar-collapse");
      wrapperCls?.add("sidebar-open");
      wrapperCls?.remove("sidebar-collapse");
    }
  }, []);

  const formatIp = (val: string) => {
    // Permite que el usuario ponga puntos manualmente; limita cada octeto a 3 dígitos y un máximo de 4 octetos
    const cleaned = val.replace(/[^0-9.]/g, "");
    const parts = cleaned.split(".").slice(0, 4).map((p) => p.slice(0, 3));
    return parts.join(".");
  };

  const toggleFullscreen = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
        setIsFullscreen(true);
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch {
      // ignore fullscreen errors
    }
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  return (
    <nav className="app-header navbar navbar-expand bg-body">
      <div className="container-fluid">
        <ul className="navbar-nav">
          <li className="nav-item">
            <a className="nav-link" href="#" role="button" onClick={toggleSidebar}>
              <i className="bi bi-list" />
            </a>
          </li>
        </ul>

        <form className="d-flex align-items-center gap-2 flex-nowrap flex-grow-1 px-3" style={{ minWidth: 0, overflowX: "auto" }}>
          <select
            className="form-select form-select-sm"
            style={{ width: "120px", flexShrink: 0 }}
            value={dbType}
            onChange={(e) =>
              setDbType((e.target.value as "postgres" | "mysql" | "sqlite") ?? "postgres")
            }
          >
            <option value="postgres">Postgres</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
          </select>
          <input
            className="form-control form-control-sm"
            style={{ width: "120px", flexShrink: 0 }}
            placeholder="dbName"
            value={dbName}
            onChange={(e) => setDbName(e.target.value)}
          />
          <input
            className="form-control form-control-sm"
            style={{ width: "140px", flexShrink: 0 }}
            placeholder="dbHostName (IP)"
            type="text"
            inputMode="decimal"
            pattern="^[0-9]{1,3}(\\.[0-9]{1,3}){3}$"
            maxLength={15}
            value={dbHost}
            onChange={(e) => setDbHost(formatIp(e.target.value))}
            title="Ingrese una IP válida, e.g., 192.168.0.10"
          />
          <input
            className="form-control form-control-sm"
            style={{ width: "80px", flexShrink: 0 }}
            placeholder="dbPort"
            inputMode="numeric"
            value={dbPort}
            onChange={(e) => setDbPort(e.target.value)}
          />
          <input
            className="form-control form-control-sm"
            style={{ width: "120px", flexShrink: 0 }}
            placeholder="dbUser"
            value={dbUser}
            onChange={(e) => setDbUser(e.target.value)}
          />
          <input
            className="form-control form-control-sm"
            style={{ width: "120px", flexShrink: 0 }}
            placeholder="dbPassword"
            type="password"
            value={dbPassword}
            onChange={(e) => setDbPassword(e.target.value)}
          />
          <button
            type="button"
            className={`btn btn-sm ${dbConnected ? "btn-success" : "btn-outline-primary"}`}
            onClick={() => setDbConnected((prev) => !prev)}
            title={dbConnected ? "Desconectar" : "Conectar"}
            style={{ flexShrink: 0 }}
          >
            {dbConnected ? (
              <i className="bi bi-plug-fill" />
            ) : (
              <i className="bi bi-plug" />
            )}
          </button>
        </form>

        <ul className="navbar-nav ms-auto">
          <li className="nav-item">
            <a className="nav-link" href="#" role="button" onClick={toggleFullscreen}>
              {isFullscreen ? (
                <i className="bi bi-fullscreen-exit" />
              ) : (
                <i className="bi bi-arrows-fullscreen" />
              )}
            </a>
          </li>
        </ul>
      </div>
    </nav>
  );
}


