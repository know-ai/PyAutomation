import { useState, useEffect, useCallback } from "react";
import { getDatabaseConfig, connectDatabase, type DatabaseConnectPayload } from "../services/database";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

interface DatabaseConfigFormProps {
  onConnectionSuccess?: () => void;
  onCancel?: () => void;
}

export function DatabaseConfigForm({ onConnectionSuccess, onCancel }: DatabaseConfigFormProps) {
  const { t } = useTranslation();
  const [dbType, setDbType] = useState<"postgres" | "mysql" | "sqlite">("postgres");
  const [dbName, setDbName] = useState("");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState<string>("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const formatIp = (val: string) => {
    // Permite que el usuario ponga puntos manualmente; limita cada octeto a 3 dígitos y un máximo de 4 octetos
    const cleaned = val.replace(/[^0-9.]/g, "");
    const parts = cleaned.split(".").slice(0, 4).map((p) => p.slice(0, 3));
    return parts.join(".");
  };

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

  const handleConnect = useCallback(async () => {
    setIsConnecting(true);
    setConnectionError(null);

    try {
      // Conectar
      const dbtype = dbType === "postgres" ? "postgresql" : dbType;
      
      const payload: DatabaseConnectPayload = {
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
        setConnectionError(null);
        // Mostrar toast de éxito con el mensaje del backend
        showToast(
          response.message || t("database.connected"),
          "success"
        );
        // Llamar al callback de éxito si existe
        if (onConnectionSuccess) {
          onConnectionSuccess();
        }
      } else {
        // Si la conexión no fue exitosa
        const errorMsg = (response != null && typeof response === "object" && response.message) 
          ? response.message 
          : t("database.connect");
        setConnectionError(errorMsg);
        // Mostrar toast de warning con la razón del fallo
        showToast(
          errorMsg,
          "warning"
        );
      }
    } catch (error: any) {
      const errorMsg = error?.response?.data?.message || error?.message || t("database.connect");
      setConnectionError(errorMsg);
      // Mostrar toast de warning con la razón del fallo
      showToast(
        errorMsg,
        "warning"
      );
    } finally {
      setIsConnecting(false);
    }
  }, [dbType, dbName, dbHost, dbPort, dbUser, dbPassword, t, onConnectionSuccess]);

  return (
    <div className="card card-outline card-warning">
      <div className="card-header">
        <h3 className="card-title">
          <i className="fas fa-database me-2"></i>
          {t("database.configureDatabase") || "Configure Database Connection"}
        </h3>
      </div>
      <div className="card-body">
        <p className="text-muted mb-3">
          {t("database.configureDatabaseMessage") || "The database connection is required to continue. Please configure the database connection below."}
        </p>
        
        <div className="mb-3">
          <label className="form-label">{t("communications.dbType") || "Database Type"}</label>
          <select
            className="form-select"
            value={dbType}
            onChange={(e) =>
              setDbType((e.target.value as "postgres" | "mysql" | "sqlite") ?? "postgres")
            }
            disabled={isConnecting}
          >
            <option value="postgres">PostgreSQL</option>
            <option value="mysql">MySQL</option>
            <option value="sqlite">SQLite</option>
          </select>
        </div>

        {dbType === "sqlite" ? (
          <div className="mb-3">
            <label className="form-label">{t("communications.dbFile") || "Database File"}</label>
            <input
              className="form-control"
              placeholder={t("communications.dbFile") || "Database File"}
              value={dbName}
              onChange={(e) => setDbName(e.target.value)}
              disabled={isConnecting}
            />
          </div>
        ) : (
          <>
            <div className="mb-3">
              <label className="form-label">{t("communications.dbName") || "Database Name"}</label>
              <input
                className="form-control"
                placeholder={t("communications.dbName") || "Database Name"}
                value={dbName}
                onChange={(e) => setDbName(e.target.value)}
                disabled={isConnecting}
                required
              />
            </div>
            <div className="mb-3">
              <label className="form-label">{t("communications.dbHostName") || "Host"}</label>
              <input
                className="form-control"
                placeholder={t("communications.dbHostName") || "Host"}
                type="text"
                inputMode="decimal"
                pattern="^[0-9]{1,3}(\\.[0-9]{1,3}){3}$"
                maxLength={15}
                value={dbHost}
                onChange={(e) => setDbHost(formatIp(e.target.value))}
                title={t("communications.enterValidIP") || "Enter a valid IP address"}
                disabled={isConnecting}
                required
              />
            </div>
            <div className="mb-3">
              <label className="form-label">{t("communications.dbPort") || "Port"}</label>
              <input
                className="form-control"
                placeholder={t("communications.dbPort") || "Port"}
                inputMode="numeric"
                value={dbPort}
                onChange={(e) => setDbPort(e.target.value)}
                disabled={isConnecting}
                required
              />
            </div>
            <div className="mb-3">
              <label className="form-label">{t("communications.dbUser") || "User"}</label>
              <input
                className="form-control"
                placeholder={t("communications.dbUser") || "User"}
                value={dbUser}
                onChange={(e) => setDbUser(e.target.value)}
                disabled={isConnecting}
                required
              />
            </div>
            <div className="mb-3">
              <label className="form-label">{t("communications.dbPassword") || "Password"}</label>
              <input
                className="form-control"
                placeholder={t("communications.dbPassword") || "Password"}
                type="password"
                value={dbPassword}
                onChange={(e) => setDbPassword(e.target.value)}
                disabled={isConnecting}
                required
              />
            </div>
          </>
        )}

        {connectionError && (
          <div className="alert alert-danger py-2 mb-3">
            {connectionError}
          </div>
        )}

        <div className="d-flex gap-2">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleConnect}
            disabled={isConnecting || (dbType !== "sqlite" && (!dbName || !dbHost || !dbPort || !dbUser || !dbPassword))}
          >
            {isConnecting ? (
              <>
                <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                {t("database.connecting") || "Connecting..."}
              </>
            ) : (
              <>
                <i className="bi bi-plug-fill me-2"></i>
                {t("database.connect") || "Connect"}
              </>
            )}
          </button>
          {onCancel && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onCancel}
              disabled={isConnecting}
            >
              {t("common.cancel") || "Cancel"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

