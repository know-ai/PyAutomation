import { useEffect, useState, useMemo } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getOpcUaServerAttributes, updateOpcUaServerAccessType, type OpcUaServerAttribute } from "../services/opcua";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

const ITEMS_PER_PAGE = 10;
const ACCESS_TYPE_OPTIONS: ("Read" | "Write" | "ReadWrite")[] = ["Read", "Write", "ReadWrite"];

export function OpcUaServer() {
  const { t } = useTranslation();
  const [attributes, setAttributes] = useState<OpcUaServerAttribute[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [updatingNamespace, setUpdatingNamespace] = useState<string | null>(null);
  
  // Estado para el modal de confirmación
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingUpdate, setPendingUpdate] = useState<{
    namespace: string;
    oldAccessType: string;
    newAccessType: string;
    name?: string;
  } | null>(null);

  // Cargar atributos
  const loadAttributes = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOpcUaServerAttributes();
      setAttributes(data);
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || t("opcuaServer.loadError");
      setError(errorMessage);
      console.error("Error loading OPC UA Server attributes:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAttributes();
  }, []);

  // Paginación
  const totalPages = Math.ceil(attributes.length / ITEMS_PER_PAGE);
  const paginatedAttributes = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    return attributes.slice(startIndex, endIndex);
  }, [attributes, currentPage]);

  // Manejar cambio de Access Type
  const handleAccessTypeChange = (attribute: OpcUaServerAttribute, newAccessType: "Read" | "Write" | "ReadWrite") => {
    if (newAccessType === attribute.access_type) {
      return; // No hay cambio
    }

    // Mostrar modal de confirmación
    setPendingUpdate({
      namespace: attribute.namespace,
      oldAccessType: attribute.access_type,
      newAccessType,
      name: attribute.name,
    });
    setShowConfirmModal(true);
  };

  // Confirmar actualización
  const handleConfirmUpdate = async () => {
    if (!pendingUpdate) return;

    setUpdatingNamespace(pendingUpdate.namespace);
    try {
      await updateOpcUaServerAccessType(
        pendingUpdate.namespace,
        pendingUpdate.newAccessType as "Read" | "Write" | "ReadWrite",
        pendingUpdate.name
      );

      // Actualizar el atributo en el estado local
      setAttributes((prev) =>
        prev.map((attr) =>
          attr.namespace === pendingUpdate.namespace
            ? { ...attr, access_type: pendingUpdate.newAccessType as "Read" | "Write" | "ReadWrite" }
            : attr
        )
      );

      showToast(t("opcuaServer.accessTypeUpdated"), "success");
      setShowConfirmModal(false);
      setPendingUpdate(null);
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || t("opcuaServer.updateError");
      showToast(errorMessage, "error");
      console.error("Error updating access type:", err);
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
    if (!attributes || attributes.length === 0) {
      showToast(t("opcuaServer.noDataToExport"), "error");
      return;
    }

    try {
      // Preparar los datos para CSV
      const headers = [
        t("tables.name"),
        t("tables.nodeNamespace"),
        t("tables.accessType"),
      ];

      // Convertir atributos a filas CSV
      const rows = attributes.map((attribute) => {
        return [
          attribute.name || "",
          attribute.namespace || "",
          attribute.access_type || "",
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
    </div>
  );

  return (
    <div className="row">
      <div className="col-12">
        <Card title={cardTitle}>
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-5">
              <div className="spinner-border" role="status">
                <span className="visually-hidden">{t("common.loading")}</span>
              </div>
            </div>
          ) : attributes.length === 0 ? (
            <div className="text-center py-5">
              <i className="bi bi-server" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
              <h4 className="mt-3 text-muted">{t("communications.opcuaServer")}</h4>
              <p className="text-muted">{t("opcuaServer.noAttributesAvailable")}</p>
            </div>
          ) : (
            <>
              <div className="table-responsive">
                <table className="table table-striped table-hover" style={{ fontSize: "0.875rem" }}>
                  <thead>
                    <tr>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.name")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.nodeNamespace")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.accessType")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedAttributes.map((attribute) => (
                      <tr key={attribute.namespace} style={{ height: "auto" }}>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>{attribute.name}</td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          <code style={{ fontSize: "0.8rem" }}>{attribute.namespace}</code>
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          <select
                            className="form-select form-select-sm"
                            value={attribute.access_type}
                            onChange={(e) =>
                              handleAccessTypeChange(
                                attribute,
                                e.target.value as "Read" | "Write" | "ReadWrite"
                              )
                            }
                            disabled={updatingNamespace === attribute.namespace}
                            style={{ minWidth: "120px", padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                          >
                            {ACCESS_TYPE_OPTIONS.map((option) => (
                              <option key={option} value={option}>
                                {t(`opcuaServer.accessType.${option}`)}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {totalPages > 1 && (
                <div className="d-flex justify-content-between align-items-center mt-3">
                  <div>
                    <span className="text-muted">
                      {t("pagination.showing", {
                        start: (currentPage - 1) * ITEMS_PER_PAGE + 1,
                        end: Math.min(currentPage * ITEMS_PER_PAGE, attributes.length),
                        total: attributes.length,
                        item: t("pagination.items.attributes"),
                      })}
                    </span>
                  </div>
                  <nav>
                    <ul className="pagination mb-0">
                      <li className={`page-item ${currentPage === 1 ? "disabled" : ""}`}>
                        <button
                          className="page-link"
                          onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                          disabled={currentPage === 1}
                        >
                          {t("pagination.previous")}
                        </button>
                      </li>
                      {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                        <li key={page} className={`page-item ${currentPage === page ? "active" : ""}`}>
                          <button className="page-link" onClick={() => setCurrentPage(page)}>
                            {page}
                          </button>
                        </li>
                      ))}
                      <li className={`page-item ${currentPage === totalPages ? "disabled" : ""}`}>
                        <button
                          className="page-link"
                          onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                          disabled={currentPage === totalPages}
                        >
                          {t("pagination.next")}
                        </button>
                      </li>
                    </ul>
                  </nav>
                </div>
              )}
            </>
          )}
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
                  <strong>{t("opcuaServer.currentAccessType")}:</strong>{" "}
                  <span className="badge bg-secondary">{t(`opcuaServer.accessType.${pendingUpdate.oldAccessType}`)}</span>
                </div>
                <div>
                  <strong>{t("opcuaServer.newAccessType")}:</strong>{" "}
                  <span className="badge bg-primary">{t(`opcuaServer.accessType.${pendingUpdate.newAccessType}`)}</span>
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
