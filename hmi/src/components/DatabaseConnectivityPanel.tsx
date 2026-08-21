import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import {
  getDatabaseConfig,
  isDatabaseConnected,
  connectDatabase,
  disconnectDatabase,
  type DatabaseConnectPayload,
} from "../services/database";
import { emitDatabaseHealth } from "../services/health";
import { useDatabaseConnected, useDatabaseStatus } from "../hooks/useDatabaseStatus";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

type Engine = "postgres" | "mysql";

const DEFAULT_PORTS: Record<Engine, string> = {
  postgres: "5432",
  mysql: "3306",
};

function mapEngine(dbtype?: string): Engine {
  const value = dbtype?.toLowerCase();
  if (value === "postgresql" || value === "postgres") return "postgres";
  if (value === "mysql") return "mysql";
  return "postgres";
}

function engineLabel(engine: Engine): string {
  if (engine === "postgres") return "PostgreSQL";
  return "MySQL";
}

export function DatabaseConnectivityPanel({ showHead = true }: { showHead?: boolean }) {
  const { t } = useTranslation();
  const { connected: healthConnected } = useDatabaseConnected();
  const { latencyMs, lastCheckedAt } = useDatabaseStatus();
  const [dbType, setDbType] = useState<Engine>("postgres");
  const [dbName, setDbName] = useState("");
  const [dbHost, setDbHost] = useState("");
  const [dbPort, setDbPort] = useState("");
  const [dbUser, setDbUser] = useState("");
  const [dbPassword, setDbPassword] = useState("");
  const [dbConnected, setDbConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const hasCheckedInitialState = useRef(false);

  useEffect(() => {
    const loadDatabaseConfig = async () => {
      try {
        const config = await getDatabaseConfig();
        if (!config || config.message) return;
        const engine = mapEngine(config.dbtype);
        setDbType(engine);
        if (config.name) {
          setDbName(config.name);
        }
        if (config.host) setDbHost(config.host);
        if (config.port) setDbPort(String(config.port));
        if (config.user) setDbUser(config.user);
      } catch (error) {
        console.error("Error loading database config:", error);
      }
    };
    void loadDatabaseConfig();
  }, []);

  useEffect(() => {
    if (hasCheckedInitialState.current) return;
    const checkInitialConnection = async () => {
      try {
        const response = await isDatabaseConnected();
        setDbConnected(Boolean(response?.connected));
        setConnectionError(null);
      } catch (error) {
        console.error("Error checking initial database connection:", error);
        setDbConnected(false);
      }
      hasCheckedInitialState.current = true;
    };
    void checkInitialConnection();
  }, []);

  useEffect(() => {
    if (healthConnected !== null) {
      setDbConnected(healthConnected);
    }
  }, [healthConnected]);

  const fieldsLocked = dbConnected || isConnecting;
  const canConnect = Boolean(dbName.trim() && dbHost.trim() && dbUser.trim() && dbPassword);

  const endpoint = useMemo(() => {
    const host = dbHost.trim() || "—";
    const port = dbPort.trim() || DEFAULT_PORTS[dbType];
    return `${host}:${port}`;
  }, [dbHost, dbPort, dbType]);

  const tone = dbConnected ? "ok" : healthConnected === null ? "unknown" : "error";
  const statusLabel = dbConnected
    ? t("database.statusActive")
    : healthConnected === null
      ? t("database.statusChecking")
      : t("database.statusIdle");

  const handleEngineChange = (next: Engine) => {
    if (fieldsLocked) return;
    const prevDefault = DEFAULT_PORTS[dbType];
    if (!dbPort || dbPort === prevDefault) {
      setDbPort(DEFAULT_PORTS[next]);
    }
    setDbType(next);
  };

  const handleConnectDisconnect = useCallback(async () => {
    setIsConnecting(true);
    setConnectionError(null);

    try {
      if (dbConnected) {
        const response = await disconnectDatabase();
        setDbConnected(false);
        emitDatabaseHealth(false);
        showToast(response?.message || t("database.disconnected"), "success");
        return;
      }

      const dbtype = dbType === "postgres" ? "postgresql" : dbType;
      const payload: DatabaseConnectPayload = {
        dbtype,
        user: dbUser.trim(),
        password: dbPassword,
        host: dbHost.trim() || "127.0.0.1",
        port: dbPort
          ? Number(dbPort)
          : Number(dbType === "mysql" ? DEFAULT_PORTS.mysql : DEFAULT_PORTS.postgres),
        name: dbName.trim(),
      };

      const response = await connectDatabase(payload);
      const isConnectionSuccessful = response?.connected === true;

      if (isConnectionSuccessful) {
        setDbConnected(true);
        emitDatabaseHealth(true);
        setConnectionError(null);
        showToast(response.message || t("database.connected"), "success");
      } else {
        setDbConnected(false);
        const errorMsg = response?.message || t("database.connect");
        setConnectionError(errorMsg);
        showToast(errorMsg, "warning");
      }
    } catch (error: any) {
      const errorMsg = error?.response?.data?.message || error?.message || t("database.connect");
      setConnectionError(errorMsg);
      setDbConnected(false);
      emitDatabaseHealth(false);
      showToast(errorMsg, "warning");
    } finally {
      setIsConnecting(false);
    }
  }, [dbConnected, dbType, dbName, dbHost, dbPort, dbUser, dbPassword, t]);

  const engines: Array<{ id: Engine; icon: string; nameKey: string; hintKey: string }> = [
    { id: "postgres", icon: "bi-database", nameKey: "database.enginePostgres", hintKey: "database.enginePostgresHint" },
    { id: "mysql", icon: "bi-hdd-network", nameKey: "database.engineMysql", hintKey: "database.engineMysqlHint" },
  ];

  return (
    <section
      className="settings-panel settings-panel--historian"
      aria-labelledby={showHead ? "settings-database-title" : undefined}
      aria-label={showHead ? undefined : t("database.panelTitle")}
    >
      {showHead ? (
        <div className="settings-panel__head">
          <p className="settings-kicker">{t("database.kicker")}</p>
          <h3 id="settings-database-title" className="settings-panel__title">
            {t("database.panelTitle")}
          </h3>
          <p className="settings-panel__lede">{t("database.panelLede")}</p>
        </div>
      ) : null}

      <div className={clsx("db-connect-status", `db-connect-status--${tone}`)} role="status">
        <span className={`db-health__led db-health__led--${tone}`} aria-hidden="true" />
        <div className="db-connect-status__copy">
          <span className="db-connect-status__label">{statusLabel}</span>
          <span className="db-connect-status__meta">
            {engineLabel(dbType)} · {endpoint}
            {dbConnected && latencyMs != null ? ` · ${Math.round(latencyMs)} ms` : ""}
          </span>
        </div>
        {lastCheckedAt && dbConnected ? (
          <span className="db-connect-status__check">
            {t("dbHealth.lastCheck")}: {new Date(lastCheckedAt).toLocaleTimeString()}
          </span>
        ) : null}
      </div>

      <div className="settings-field">
        <div className="settings-field__label">{t("database.engine")}</div>
        <div className="db-engine-choice" role="radiogroup" aria-label={t("database.engine")}>
          {engines.map((engine) => {
            const selected = dbType === engine.id;
            return (
              <button
                key={engine.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={clsx("settings-choice__card", selected && "is-selected")}
                onClick={() => handleEngineChange(engine.id)}
                disabled={fieldsLocked}
              >
                <i className={clsx("bi", engine.icon, "settings-choice__icon")} aria-hidden="true" />
                <span className="settings-choice__copy">
                  <span className="settings-choice__name">{t(engine.nameKey)}</span>
                  <span className="settings-choice__hint">{t(engine.hintKey)}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="settings-form-grid">
          <div className="settings-form-field">
            <label htmlFor="db-host" className="form-label">
              {t("database.host")}
            </label>
            <input
              id="db-host"
              className="form-control"
              value={dbHost}
              onChange={(e) => setDbHost(e.target.value.trimStart())}
              disabled={fieldsLocked}
              autoComplete="off"
              placeholder="db.plant.local"
            />
            <small className="form-text text-muted">{t("database.hostHint")}</small>
          </div>
          <div className="settings-form-field">
            <label htmlFor="db-port" className="form-label">
              {t("database.port")}
            </label>
            <input
              id="db-port"
              className="form-control"
              inputMode="numeric"
              value={dbPort}
              onChange={(e) => setDbPort(e.target.value.replace(/[^\d]/g, "").slice(0, 5))}
              disabled={fieldsLocked}
              autoComplete="off"
              placeholder={DEFAULT_PORTS[dbType]}
            />
          </div>
          <div className="settings-form-field">
            <label htmlFor="db-name" className="form-label">
              {t("database.name")}
            </label>
            <input
              id="db-name"
              className="form-control"
              value={dbName}
              onChange={(e) => setDbName(e.target.value)}
              disabled={fieldsLocked}
              autoComplete="off"
            />
          </div>
          <div className="settings-form-field">
            <label htmlFor="db-user" className="form-label">
              {t("database.user")}
            </label>
            <input
              id="db-user"
              className="form-control"
              value={dbUser}
              onChange={(e) => setDbUser(e.target.value)}
              disabled={fieldsLocked}
              autoComplete="username"
            />
          </div>
          <div className="settings-form-field settings-form-field--span">
            <label htmlFor="db-password" className="form-label">
              {t("database.password")}
            </label>
            <input
              id="db-password"
              className="form-control"
              type="password"
              value={dbPassword}
              onChange={(e) => setDbPassword(e.target.value)}
              disabled={fieldsLocked}
              autoComplete="current-password"
              placeholder={dbConnected ? "••••••••" : undefined}
            />
          </div>
        </div>

      {dbConnected ? (
        <p className="db-connect-lock">{t("database.lockedHint")}</p>
      ) : null}

      {connectionError ? (
        <div className="alert alert-danger py-2 mt-3 mb-0" role="alert">
          {connectionError}
        </div>
      ) : null}

      <div className="settings-panel__actions">
        <button
          type="button"
          className={clsx("btn", dbConnected ? "btn-outline-danger" : "btn-primary")}
          onClick={() => void handleConnectDisconnect()}
          disabled={isConnecting || (!dbConnected && !canConnect)}
        >
          {isConnecting ? (
            <>
              <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true" />
              {dbConnected ? t("database.disconnecting") : t("database.connecting")}
            </>
          ) : dbConnected ? (
            <>
              <i className="bi bi-plug me-2" aria-hidden="true" />
              {t("database.disconnect")}
            </>
          ) : (
            <>
              <i className="bi bi-plug-fill me-2" aria-hidden="true" />
              {t("database.connect")}
            </>
          )}
        </button>
      </div>
    </section>
  );
}
