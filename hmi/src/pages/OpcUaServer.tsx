import { useEffect, useState, useMemo, useCallback } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getOpcUaServerAttributes, updateOpcUaServerAccessLevel, type OpcUaServerAttribute } from "../services/opcua";
import { socketService } from "../services/socket";
import { useTranslation } from "../hooks/useTranslation";
import { useDebounce } from "../hooks/useDebounce";
import { showToast } from "../utils/toast";
import { useAuthz } from "../hooks/useAuthz";

const LEVEL_OPTIONS = [
  { value: 1, labelKey: "Read" },
  { value: 2, labelKey: "Write" },
  { value: 3, labelKey: "ReadWrite" },
] as const;

const ACCESS_BITS = [
  { mask: 0x01, key: "currentRead" },
  { mask: 0x02, key: "currentWrite" },
  { mask: 0x04, key: "historyRead" },
  { mask: 0x08, key: "historyWrite" },
  { mask: 0x10, key: "semanticChange" },
  { mask: 0x20, key: "statusWrite" },
  { mask: 0x40, key: "timestampWrite" },
] as const;

export function OpcUaServer() {
  const { t } = useTranslation();
  const { canExportCsv } = useAuthz();
  const [attributes, setAttributes] = useState<OpcUaServerAttribute[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageLimit, setPageLimit] = useState(20);
  const [updatingNamespace, setUpdatingNamespace] = useState<string | null>(null);
  const [nameFilter, setNameFilter] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const debouncedNameFilter = useDebounce(nameFilter, 300);
  
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingUpdate, setPendingUpdate] = useState<{
    namespace: string;
    oldLevel: number;
    newLevel: number;
    name?: string;
  } | null>(null);

  // Cargar atributos
  const loadAttributes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOpcUaServerAttributes({ name: debouncedNameFilter });
      setAttributes(data);
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || t("opcuaServer.loadError");
      setError(errorMessage);
      console.error("Error loading OPC UA Server attributes:", err);
    } finally {
      setLoading(false);
    }
  }, [debouncedNameFilter, t]);

  useEffect(() => {
    loadAttributes();
  }, [loadAttributes]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void loadAttributes();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [loadAttributes]);

  useEffect(() => {
    const offAdded = socketService.onOpcUaServerNodeAdded(() => {
      void loadAttributes();
    });
    const offRemoved = socketService.onOpcUaServerNodeRemoved(() => {
      void loadAttributes();
    });
    return () => {
      offAdded();
      offRemoved();
    };
  }, [loadAttributes]);

  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedNameFilter]);

  // Paginación
  const totalPages = Math.max(1, Math.ceil(attributes.length / pageLimit) || 1);
  const paginatedAttributes = useMemo(() => {
    const startIndex = (currentPage - 1) * pageLimit;
    return attributes.slice(startIndex, startIndex + pageLimit);
  }, [attributes, currentPage, pageLimit]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setPageLimit(newLimit);
      setCurrentPage(1);
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
    }
  };

  const requestLevel = (attribute: OpcUaServerAttribute, newLevel: number) => {
    if (newLevel === attribute.access_level) {
      return;
    }
    setPendingUpdate({
      namespace: attribute.namespace,
      oldLevel: attribute.access_level,
      newLevel,
      name: attribute.name,
    });
    setShowConfirmModal(true);
  };

  const handleConfirmUpdate = async () => {
    if (!pendingUpdate) return;

    setUpdatingNamespace(pendingUpdate.namespace);
    try {
      const updated = await updateOpcUaServerAccessLevel(
        pendingUpdate.namespace,
        pendingUpdate.newLevel,
        pendingUpdate.name
      );

      setAttributes((prev) =>
        prev.map((attr) =>
          attr.namespace === pendingUpdate.namespace
            ? {
                ...attr,
                access_level: updated.access_level,
                access_level_label: updated.access_level_label,
                user_access_level: updated.user_access_level,
                access_restrictions: updated.access_restrictions,
              }
            : attr
        )
      );

      showToast(t("opcuaServer.accessLevelUpdated"), "success");
      setShowConfirmModal(false);
      setPendingUpdate(null);
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || t("opcuaServer.updateError");
      showToast(errorMessage, "error");
      console.error("Error updating access level:", err);
    } finally {
      setUpdatingNamespace(null);
    }
  };

  // Cancelar actualización
  const handleCancelUpdate = () => {
    setShowConfirmModal(false);
    setPendingUpdate(null);
  };

  // Exportar a CSV
  const handleExportCSV = () => {
    if (!canExportCsv()) return;
    if (!attributes || attributes.length === 0) {
      showToast(t("opcuaServer.noDataToExport"), "error");
      return;
    }

    try {
      // Preparar los datos para CSV
      const headers = [
        t("tables.name"),
        t("tables.nodeNamespace"),
        t("tables.accessLevel"),
      ];

      const rows = attributes.map((attribute) => {
        return [
          attribute.name || "",
          attribute.namespace || "",
          String(attribute.access_level ?? ""),
        ];
      });

      // Crear contenido CSV
      const csvContent = [
        headers.join(","),
        ...rows.map((row) =>
          row
            .map((cell) => {
              const cellStr = String(cell);
              if (cellStr.includes(",") || cellStr.includes('"') || cellStr.includes("\n")) {
                return `"${cellStr.replace(/"/g, '""')}"`;
              }
              return cellStr;
            })
            .join(",")
        ),
      ].join("\n");

      // Crear y descargar el archivo
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = `opcua_server_attributes_${new Date().toISOString().split("T")[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      showToast(t("opcuaServer.exportSuccess"), "success");
    } catch (err: any) {
      const errorMessage = err?.message || t("opcuaServer.exportError");
      showToast(errorMessage, "error");
      console.error("Error exporting CSV:", err);
    }
  };

  // Título del card con botón de exportación
  const cardTitle = (
    <div className="d-flex justify-content-between align-items-center w-100">
      <h3 className="card-title m-0">{t("communications.opcuaServer")}</h3>
      <label className="form-check form-switch mb-0 ms-3">
        <input
          className="form-check-input"
          type="checkbox"
          checked={advanced}
          onChange={(event) => setAdvanced(event.target.checked)}
        />
        <span className="form-check-label">{t("opcuaServer.advanced")}</span>
      </label>
      {canExportCsv() && (
        <Button
          variant="success"
          onClick={handleExportCSV}
          className="btn-sm"
          disabled={loading || attributes.length === 0}
          title={t("opcuaServer.exportCSV")}
        >
          <i className="bi bi-download me-1"></i>
          {t("common.csv")}
        </Button>
      )}
    </div>
  );

  return (
    <div className="row g-0 page-fit-viewport">
      <div className="col-12 h-100">
        <Card
          className="page-fit-card"
          title={cardTitle}
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <label className="mb-0 small">{t("pagination.itemsPerPage")}</label>
                <select
                  className="form-select form-select-sm"
                  style={{ width: "auto" }}
                  value={pageLimit}
                  onChange={(e) => handleLimitChange(Number(e.target.value))}
                  disabled={loading}
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
              <div className="d-flex align-items-center gap-2">
                <span className="small text-muted">
                  {t("pagination.pageOf", {
                    current: currentPage,
                    total: totalPages,
                    count: attributes.length,
                  })}
                </span>
                <div className="btn-group" role="group">
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(1)}
                    disabled={loading || currentPage === 1}
                  >
                    «
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={loading || currentPage === 1}
                  >
                    ‹
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={loading || currentPage >= totalPages}
                  >
                    ›
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(totalPages)}
                    disabled={loading || currentPage >= totalPages}
                  >
                    »
                  </Button>
                </div>
              </div>
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          <div className="table-responsive">
            <table className="table table-striped table-hover" style={{ fontSize: "0.875rem" }}>
              <thead>
                <tr>
                  <th style={{ padding: "0.5rem 0.75rem", maxWidth: "320px" }}>
                    <input
                      type="text"
                      className="form-control form-control-sm"
                      placeholder={t("common.filter")}
                      value={nameFilter}
                      onChange={(e) => setNameFilter(e.target.value)}
                      disabled={loading}
                      aria-label={t("common.filter")}
                    />
                  </th>
                  <th style={{ padding: "0.5rem 0.75rem" }}></th>
                  <th style={{ padding: "0.5rem 0.75rem" }}></th>
                </tr>
                <tr>
                  <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.name")}</th>
                  <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.nodeNamespace")}</th>
                  <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.accessLevel")}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={3} className="text-center py-5">
                      <div className="spinner-border" role="status">
                        <span className="visually-hidden">{t("common.loading")}</span>
                      </div>
                    </td>
                  </tr>
                ) : attributes.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="text-center py-5">
                      <i className="bi bi-server" style={{ fontSize: "3rem", color: "#6c757d" }}></i>
                      <p className="text-muted mb-0 mt-3">
                        {debouncedNameFilter.trim()
                          ? t("opcuaServer.noAttributesMatchFilter")
                          : t("opcuaServer.noAttributesAvailable")}
                      </p>
                    </td>
                  </tr>
                ) : (
                  paginatedAttributes.map((attribute) => (
                    <tr key={attribute.namespace} style={{ height: "auto" }}>
                      <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>{attribute.name}</td>
                      <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                        <code style={{ fontSize: "0.8rem" }}>{attribute.namespace}</code>
                      </td>
                      <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                        {advanced ? (
                          <div className="d-flex flex-wrap gap-2">
                            {ACCESS_BITS.map((bit) => (
                              <label key={bit.key} className="form-check form-check-inline mb-0">
                                <input
                                  className="form-check-input"
                                  type="checkbox"
                                  checked={(attribute.access_level & bit.mask) !== 0}
                                  disabled={updatingNamespace === attribute.namespace}
                                  onChange={(event) => {
                                    const next = event.target.checked
                                      ? attribute.access_level | bit.mask
                                      : attribute.access_level & ~bit.mask;
                                    requestLevel(attribute, next & 0x7f);
                                  }}
                                />
                                <span className="form-check-label">{t(`opcuaServer.bits.${bit.key}`)}</span>
                              </label>
                            ))}
                          </div>
                        ) : (
                          <select
                            className="form-select form-select-sm"
                            value={[1, 2, 3].includes(attribute.access_level) ? String(attribute.access_level) : ""}
                            onChange={(event) => requestLevel(attribute, Number(event.target.value))}
                            disabled={updatingNamespace === attribute.namespace}
                            style={{ minWidth: "120px", padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                          >
                            {![1, 2, 3].includes(attribute.access_level) && (
                              <option value="">{attribute.access_level}</option>
                            )}
                            {LEVEL_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {t(`opcuaServer.accessType.${option.labelKey}`)}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* Modal de confirmación */}
      {showConfirmModal && pendingUpdate && (
        <div
          className="modal fade show"
          style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget && !updatingNamespace) {
              handleCancelUpdate();
            }
          }}
        >
          <div className="modal-dialog modal-dialog-centered" role="document">
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h5 className="modal-title">{t("opcuaServer.confirmChangeTitle")}</h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={handleCancelUpdate}
                  aria-label="Close"
                  disabled={!!updatingNamespace}
                ></button>
              </div>
              <div className="modal-body">
                <p>
                  {t("opcuaServer.confirmChangeMessage")}
                </p>
                <div className="mb-2">
                  <strong>{t("tables.name")}:</strong> {pendingUpdate.name || pendingUpdate.namespace}
                </div>
                <div className="mb-2">
                  <strong>{t("tables.nodeNamespace")}:</strong> <code>{pendingUpdate.namespace}</code>
                </div>
                <div className="mb-2">
                  <strong>{t("opcuaServer.currentAccessLevel")}:</strong>{" "}
                  <span className="badge bg-secondary">{pendingUpdate.oldLevel}</span>
                </div>
                <div>
                  <strong>{t("opcuaServer.newAccessLevel")}:</strong>{" "}
                  <span className="badge bg-primary">{pendingUpdate.newLevel}</span>
                </div>
              </div>
              <div className="modal-footer">
                <Button
                  variant="secondary"
                  onClick={handleCancelUpdate}
                  disabled={!!updatingNamespace}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  variant="primary"
                  onClick={handleConfirmUpdate}
                  disabled={!!updatingNamespace}
                >
                  {updatingNamespace ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      {t("opcuaServer.updating")}
                    </>
                  ) : (
                    t("common.confirm")
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
