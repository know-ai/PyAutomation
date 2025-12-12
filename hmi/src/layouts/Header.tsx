import { useCallback, useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  getDatabaseConfig,
  isDatabaseConnected,
  connectDatabase,
  disconnectDatabase,
  type DatabaseConfig,
} from "../services/database";
import { useTheme } from "../hooks/useTheme";
import { logout as logoutService } from "../services/auth";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { logout as logoutAction } from "../store/slices/authSlice";

export function Header() {
  const { mode, toggle } = useTheme();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [showLogoutModal, setShowLogoutModal] = useState(false);

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
  const [dbType, setDbType] = useState<"postgres" | "mysql" | "sqlite">("postgres");
  const [dbName, setDbName] = useState("");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState<string>("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [dbConnected, setDbConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

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

  // Cargar configuración de la base de datos al montar
  useEffect(() => {
    const loadDatabaseConfig = async () => {
      try {
        const config = await getDatabaseConfig();
        if (config && !config.message) {
          // Mapear dbtype del backend al formato del frontend
          const dbtype = config.dbtype?.toLowerCase();
          if (dbtype === "postgresql") {
            setDbType("postgres");
          } else if (dbtype === "mysql" || dbtype === "sqlite") {
            setDbType(dbtype as "mysql" | "sqlite");
          }
          
          // Para SQLite, usar dbfile; para otros, usar name
          if (dbtype === "sqlite" && config.dbfile) {
            setDbName(config.dbfile);
          } else if (config.name) {
            setDbName(config.name);
          }
          
          if (config.host) {
            setDbHost(config.host);
          }
          if (config.port) {
            setDbPort(String(config.port));
          }
          if (config.user) {
            setDbUser(config.user);
          }
        }
      } catch (error: any) {
        console.error("Error loading database config:", error);
      }
    };

    loadDatabaseConfig();
  }, []);

  // Verificar estado de conexión periódicamente
  useEffect(() => {
    const checkConnection = async () => {
      try {
        const response = await isDatabaseConnected();
        setDbConnected(response.connected);
        setConnectionError(null);
      } catch (error: any) {
        console.error("Error checking database connection:", error);
        setDbConnected(false);
      }
    };

    // Verificar inmediatamente
    checkConnection();

    // Verificar cada 30 segundos
    intervalRef.current = setInterval(checkConnection, 30000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

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

  const handleConnectDisconnect = useCallback(async () => {
    setIsConnecting(true);
    setConnectionError(null);

    try {
      if (dbConnected) {
        // Desconectar
        await disconnectDatabase();
        setDbConnected(false);
      } else {
        // Conectar
        const dbtype = dbType === "postgres" ? "postgresql" : dbType;
        
        const payload: any = {
          dbtype: dbtype,
        };

        if (dbtype === "sqlite") {
          payload.dbfile = dbName || "app.db";
        } else {
          payload.user = dbUser;
          payload.password = dbPassword;
          payload.host = dbHost || "127.0.0.1";
          payload.port = dbPort ? Number(dbPort) : (dbtype === "mysql" ? 3306 : 5432);
          payload.name = dbName;
        }

        const response = await connectDatabase(payload);
        if (response.connected) {
          setDbConnected(true);
        } else {
          setConnectionError(response.message || "Error al conectar");
        }
      }
    } catch (error: any) {
      const errorMsg = error?.response?.data?.message || error?.message || "Error al conectar/desconectar";
      setConnectionError(errorMsg);
      setDbConnected(false);
    } finally {
      setIsConnecting(false);
    }
  }, [dbConnected, dbType, dbName, dbHost, dbPort, dbUser, dbPassword]);

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
            disabled={dbConnected}
          >
            <option value="postgres">Postgres</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
          </select>
          <input
            className="form-control form-control-sm"
            style={{ width: "120px", flexShrink: 0 }}
            placeholder={dbType === "sqlite" ? "dbFile" : "dbName"}
            value={dbName}
            onChange={(e) => setDbName(e.target.value)}
            disabled={dbConnected}
          />
          {dbType !== "sqlite" && (
            <>
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
                disabled={dbConnected}
              />
              <input
                className="form-control form-control-sm"
                style={{ width: "80px", flexShrink: 0 }}
                placeholder="dbPort"
                inputMode="numeric"
                value={dbPort}
                onChange={(e) => setDbPort(e.target.value)}
                disabled={dbConnected}
              />
              <input
                className="form-control form-control-sm"
                style={{ width: "120px", flexShrink: 0 }}
                placeholder="dbUser"
                value={dbUser}
                onChange={(e) => setDbUser(e.target.value)}
                disabled={dbConnected}
              />
              <input
                className="form-control form-control-sm"
                style={{ width: "120px", flexShrink: 0 }}
                placeholder="dbPassword"
                type="password"
                value={dbPassword}
                onChange={(e) => setDbPassword(e.target.value)}
                disabled={dbConnected}
              />
            </>
          )}
          <button
            type="button"
            className={`btn btn-sm ${dbConnected ? "btn-danger" : "btn-success"}`}
            onClick={handleConnectDisconnect}
            title={dbConnected ? "Desconectar de la base de datos" : "Conectar a la base de datos"}
            style={{ flexShrink: 0 }}
            disabled={isConnecting}
          >
            {isConnecting ? (
              <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
            ) : dbConnected ? (
              <i className="bi bi-plug-fill" />
            ) : (
              <i className="bi bi-plug" />
            )}
          </button>
          {connectionError && (
            <span className="text-danger small" style={{ flexShrink: 0, whiteSpace: "nowrap" }}>
              {connectionError}
            </span>
          )}
        </form>

        <ul className="navbar-nav ms-auto">
          <li className="nav-item">
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={(e) => {
                e.preventDefault();
                toggle();
              }}
              title={mode === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
            >
              {mode === "dark" ? (
                <i className="bi bi-sun-fill" />
              ) : (
                <i className="bi bi-moon-fill" />
              )}
            </a>
          </li>
          <li className="nav-item">
            <a className="nav-link" href="#" role="button" onClick={toggleFullscreen}>
              {isFullscreen ? (
                <i className="bi bi-fullscreen-exit" />
              ) : (
                <i className="bi bi-arrows-fullscreen" />
              )}
            </a>
          </li>
          <li className="nav-item">
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={handleLogoutClick}
              title="Cerrar sesión"
              style={{ cursor: isLoggingOut ? "wait" : "pointer" }}
            >
              {isLoggingOut ? (
                <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
              ) : (
                <i className="bi bi-box-arrow-right" />
              )}
            </a>
          </li>
        </ul>
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
                <h5 className="modal-title">Confirmar cierre de sesión</h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={() => setShowLogoutModal(false)}
                  aria-label="Close"
                  disabled={isLoggingOut}
                ></button>
              </div>
              <div className="modal-body">
                <p>¿Está seguro de que desea cerrar sesión?</p>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowLogoutModal(false)}
                  disabled={isLoggingOut}
                >
                  Cancelar
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
                      Cerrando...
                    </>
                  ) : (
                    "Cerrar sesión"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}


