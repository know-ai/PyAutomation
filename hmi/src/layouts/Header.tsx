import { useCallback, useEffect, useState, useRef } from "react";
import {
  getDatabaseConfig,
  isDatabaseConnected,
  connectDatabase,
  disconnectDatabase,
  type DatabaseConfig,
} from "../services/database";
import { useTheme } from "../hooks/useTheme";
import { useTranslation } from "../hooks/useTranslation";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { setLocale } from "../store/slices/localeSlice";
import { showToast } from "../utils/toast";

export function Header() {
  const { mode, toggle } = useTheme();
  const { t, locale } = useTranslation();
  const dispatch = useAppDispatch();
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showLanguageDropdown, setShowLanguageDropdown] = useState(false);

  // Cerrar dropdown de idioma al hacer clic fuera
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (showLanguageDropdown) {
        const target = e.target as HTMLElement;
        if (!target.closest(".nav-item[style*='position: relative']")) {
          setShowLanguageDropdown(false);
        }
      }
    };
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [showLanguageDropdown]);
  const [dbType, setDbType] = useState<"postgres" | "mysql" | "sqlite">("postgres");
  const [dbName, setDbName] = useState("");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState<string>("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [dbConnected, setDbConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasCheckedInitialState = useRef(false);

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

  // Verificación inicial del estado de conexión al montar
  useEffect(() => {
    if (hasCheckedInitialState.current) return;
    
    const checkInitialConnection = async () => {
      try {
        const response = await isDatabaseConnected();
        if (response != null && typeof response === "object" && typeof response.connected === "boolean") {
          setDbConnected(response.connected);
          setConnectionError(null);
        } else {
          setDbConnected(false);
          setConnectionError(null);
        }
      } catch (error: any) {
        console.error("Error checking initial database connection:", error);
        setDbConnected(false);
        setConnectionError(null);
      }
      hasCheckedInitialState.current = true;
    };

    checkInitialConnection();
  }, []);

  // Verificar estado de conexión periódicamente solo cuando está conectado
  useEffect(() => {
    // Si no está conectado, no hacer verificación periódica
    if (!dbConnected) {
      // Limpiar intervalo si existe
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    const checkConnection = async () => {
      try {
        const response = await isDatabaseConnected();
        if (response != null && typeof response === "object" && typeof response.connected === "boolean") {
          setDbConnected(response.connected);
          setConnectionError(null);
        } else {
          // Si la respuesta no es válida, asumimos desconectado
          setDbConnected(false);
          setConnectionError(null);
        }
      } catch (error: any) {
        console.error("Error checking database connection:", error);
        setDbConnected(false);
        setConnectionError(null);
      }
    };

    // Verificar inmediatamente
    checkConnection();

    // Verificar cada 30 segundos
    intervalRef.current = setInterval(checkConnection, 30000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [dbConnected]);

  const handleConnectDisconnect = useCallback(async () => {
    setIsConnecting(true);
    setConnectionError(null);

    try {
      if (dbConnected) {
        // Desconectar manualmente - detener verificación periódica inmediatamente
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        
        const response = await disconnectDatabase();
        setDbConnected(false);
        // Mostrar toast de éxito con el mensaje del backend
        if (response != null && typeof response === "object" && response.message) {
          showToast(response.message, "success");
        } else {
          showToast(t("database.disconnected"), "success");
        }
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
        // Solo considerar la conexión exitosa si response.connected es explícitamente true
        const isConnectionSuccessful = response != null && 
                                      typeof response === "object" && 
                                      response.connected === true;
        
        if (isConnectionSuccessful) {
          // Solo establecer como conectado si la conexión fue realmente exitosa
          // Esto activará automáticamente la verificación periódica por el useEffect
          setDbConnected(true);
          setConnectionError(null);
          // Mostrar toast de éxito con el mensaje del backend
          showToast(
            response.message || t("database.connected"),
            "success"
          );
        } else {
          // Si la conexión no fue exitosa, asegurarse de que esté desconectado
          // y que la verificación periódica NO se active
          setDbConnected(false);
          const errorMsg = (response != null && typeof response === "object" && response.message) 
            ? response.message 
            : t("database.connect");
          setConnectionError(errorMsg);
          // Asegurarse de que la verificación periódica esté detenida
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          // Mostrar toast de warning con la razón del fallo
          showToast(
            errorMsg,
            "warning"
          );
        }
      }
    } catch (error: any) {
      const errorMsg = error?.response?.data?.message || error?.message || t("database.connect");
      setConnectionError(errorMsg);
      // Asegurarse de que esté desconectado y la verificación periódica NO se active
      setDbConnected(false);
      // Asegurarse de que la verificación periódica esté detenida
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      // Mostrar toast de warning con la razón del fallo
      showToast(
        errorMsg,
        "warning"
      );
    } finally {
      setIsConnecting(false);
    }
  }, [dbConnected, dbType, dbName, dbHost, dbPort, dbUser, dbPassword, t]);

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
            placeholder={dbType === "sqlite" ? t("communications.dbFile") : t("communications.dbName")}
            value={dbName}
            onChange={(e) => setDbName(e.target.value)}
            disabled={dbConnected}
          />
          {dbType !== "sqlite" && (
            <>
              <input
                className="form-control form-control-sm"
                style={{ width: "140px", flexShrink: 0 }}
                placeholder={t("communications.dbHostName")}
                type="text"
                inputMode="decimal"
                pattern="^[0-9]{1,3}(\\.[0-9]{1,3}){3}$"
                maxLength={15}
                value={dbHost}
                onChange={(e) => setDbHost(formatIp(e.target.value))}
                title={t("communications.enterValidIP")}
                disabled={dbConnected}
              />
              <input
                className="form-control form-control-sm"
                style={{ width: "80px", flexShrink: 0 }}
                placeholder={t("communications.dbPort")}
                inputMode="numeric"
                value={dbPort}
                onChange={(e) => setDbPort(e.target.value)}
                disabled={dbConnected}
              />
              <input
                className="form-control form-control-sm"
                style={{ width: "120px", flexShrink: 0 }}
                placeholder={t("communications.dbUser")}
                value={dbUser}
                onChange={(e) => setDbUser(e.target.value)}
                disabled={dbConnected}
              />
              <input
                className="form-control form-control-sm"
                style={{ width: "120px", flexShrink: 0 }}
                placeholder={t("communications.dbPassword")}
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
            title={dbConnected ? t("communications.disconnectFromDatabase") : t("communications.connectToDatabase")}
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
          <li className="nav-item" style={{ position: "relative" }}>
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={(e) => {
                e.preventDefault();
                setShowLanguageDropdown(!showLanguageDropdown);
              }}
              title={locale === "en" ? "English" : "Español"}
            >
              {locale === "en" ? "🇺🇸" : "🇪🇸"}
            </a>
            {showLanguageDropdown && (
              <div
                className="dropdown-menu dropdown-menu-end show"
                style={{
                  position: "absolute",
                  right: 0,
                  top: "100%",
                  zIndex: 1000,
                  minWidth: "150px",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <a
                  className={`dropdown-item ${locale === "en" ? "active" : ""}`}
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    dispatch(setLocale("en"));
                    setShowLanguageDropdown(false);
                  }}
                >
                  🇺🇸 English
                </a>
                <a
                  className={`dropdown-item ${locale === "es" ? "active" : ""}`}
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    dispatch(setLocale("es"));
                    setShowLanguageDropdown(false);
                  }}
                >
                  🇪🇸 Español
                </a>
              </div>
            )}
          </li>
          <li className="nav-item">
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={(e) => {
                e.preventDefault();
                toggle();
              }}
              title={mode === "dark" ? t("header.switchToLight") : t("header.switchToDark")}
            >
              {mode === "dark" ? (
                <i className="bi bi-sun-fill" />
              ) : (
                <i className="bi bi-moon-fill" />
              )}
            </a>
          </li>
          <li className="nav-item">
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={toggleFullscreen}
              title={isFullscreen ? t("header.exitFullscreen") : t("header.fullscreen")}
            >
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


