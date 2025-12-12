import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getTags, createTag, type Tag, type TagsResponse } from "../services/tags";

export function Tags() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });
  
  // Form state
  const [formData, setFormData] = useState({
    name: "",
    unit: "",
    variable: "",
    display_unit: "",
    data_type: "float",
    description: "",
    display_name: "",
    opcua_address: "",
    node_namespace: "",
    scan_time: "",
    dead_band: "",
    process_filter: false,
    gaussian_filter: false,
    gaussian_filter_threshold: "1.0",
    gaussian_filter_r_value: "0.0",
    outlier_detection: false,
    out_of_range_detection: false,
    frozen_data_detection: false,
    segment: "",
    manufacturer: "",
  });

  const loadTags = async (page: number = pagination.page, limit: number = pagination.limit) => {
    setLoading(true);
    setError(null);
    try {
      const response: TagsResponse = await getTags(page, limit);
      setTags(response.data || []);
      setPagination(response.pagination || {
        page: page,
        limit: limit,
        total: 0,
        pages: 0,
      });
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar tags";
      setError(errorMsg);
      setTags([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTags(1, 20);
  }, []);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      loadTags(newPage, pagination.limit);
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      loadTags(1, newLimit);
    }
  };

  const handleCreateTag = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    
    try {
      // Validar campos requeridos
      if (!formData.name || !formData.unit || !formData.variable) {
        setError("Los campos Nombre, Unit y Variable son requeridos");
        setCreating(false);
        return;
      }

      // Preparar payload
      const payload: any = {
        name: formData.name,
        unit: formData.unit,
        variable: formData.variable,
      };

      // Agregar campos opcionales solo si tienen valor
      if (formData.display_unit) payload.display_unit = formData.display_unit;
      if (formData.data_type) payload.data_type = formData.data_type;
      if (formData.description) payload.description = formData.description;
      if (formData.display_name) payload.display_name = formData.display_name;
      if (formData.opcua_address) payload.opcua_address = formData.opcua_address;
      if (formData.node_namespace) payload.node_namespace = formData.node_namespace;
      if (formData.scan_time) payload.scan_time = parseInt(formData.scan_time);
      if (formData.dead_band) payload.dead_band = parseFloat(formData.dead_band);
      if (formData.segment) payload.segment = formData.segment;
      if (formData.manufacturer) payload.manufacturer = formData.manufacturer;

      // Booleanos
      payload.process_filter = formData.process_filter;
      payload.gaussian_filter = formData.gaussian_filter;
      payload.outlier_detection = formData.outlier_detection;
      payload.out_of_range_detection = formData.out_of_range_detection;
      payload.frozen_data_detection = formData.frozen_data_detection;

      // Valores de filtro gaussiano
      if (formData.gaussian_filter_threshold) {
        payload.gaussian_filter_threshold = parseFloat(formData.gaussian_filter_threshold);
      }
      if (formData.gaussian_filter_r_value) {
        payload.gaussian_filter_r_value = parseFloat(formData.gaussian_filter_r_value);
      }

      await createTag(payload);
      
      // Cerrar modal y resetear formulario
      setShowCreateModal(false);
      setFormData({
        name: "",
        unit: "",
        variable: "",
        display_unit: "",
        data_type: "float",
        description: "",
        display_name: "",
        opcua_address: "",
        node_namespace: "",
        scan_time: "",
        dead_band: "",
        process_filter: false,
        gaussian_filter: false,
        gaussian_filter_threshold: "1.0",
        gaussian_filter_r_value: "0.0",
        outlier_detection: false,
        out_of_range_detection: false,
        frozen_data_detection: false,
        segment: "",
        manufacturer: "",
      });
      
      // Recargar tags
      loadTags(pagination.page, pagination.limit);
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al crear el tag";
      setError(errorMsg);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex justify-content-between align-items-center w-100">
              <span>Tags</span>
              <Button
                variant="success"
                className="btn-sm"
                onClick={() => setShowCreateModal(true)}
              >
                <i className="bi bi-plus-circle me-1"></i>
                Crear Tag
              </Button>
            </div>
          }
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <label className="mb-0 small">Items por página:</label>
                <select
                  className="form-select form-select-sm"
                  style={{ width: "auto" }}
                  value={pagination.limit}
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
                  Página {pagination.page} de {pagination.pages} ({pagination.total} total)
                </span>
                <div className="btn-group" role="group">
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(1)}
                    disabled={loading || pagination.page === 1}
                  >
                    «
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.page - 1)}
                    disabled={loading || pagination.page === 1}
                  >
                    ‹
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.page + 1)}
                    disabled={loading || pagination.page >= pagination.pages}
                  >
                    ›
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.pages)}
                    disabled={loading || pagination.page >= pagination.pages}
                  >
                    »
                  </Button>
                </div>
              </div>
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger mb-3" role="alert">
              {error}
            </div>
          )}

          {loading && (
            <div className="text-center py-4">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">Cargando...</span>
              </div>
            </div>
          )}

          {!loading && (
            <div className="table-responsive">
              <table className="table table-striped table-hover table-sm">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Display Name</th>
                    <th>Variable</th>
                    <th>Unit</th>
                    <th>Display Unit</th>
                    <th>Data Type</th>
                    <th>OPC UA Address</th>
                    <th>Node Namespace</th>
                    <th>Scan Time (ms)</th>
                    <th>Dead Band</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {tags.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="text-center text-muted py-4">
                        No hay tags disponibles
                      </td>
                    </tr>
                  ) : (
                    tags.map((tag) => (
                      <tr key={tag.id || tag.name}>
                        <td>{tag.id || "-"}</td>
                        <td>
                          <strong>{tag.name || "-"}</strong>
                        </td>
                        <td>{tag.display_name || "-"}</td>
                        <td>{tag.variable || "-"}</td>
                        <td>{tag.unit || "-"}</td>
                        <td>{tag.display_unit || "-"}</td>
                        <td>
                          <span className="badge bg-info">{tag.data_type || "float"}</span>
                        </td>
                        <td>
                          <small className="text-muted" style={{ fontFamily: "monospace" }}>
                            {tag.opcua_address || "-"}
                          </small>
                        </td>
                        <td>
                          <small className="text-muted" style={{ fontFamily: "monospace" }}>
                            {tag.node_namespace || "-"}
                          </small>
                        </td>
                        <td>{tag.scan_time || "-"}</td>
                        <td>{tag.dead_band !== undefined ? tag.dead_band : "-"}</td>
                        <td>
                          <small className="text-muted">
                            {tag.description || "-"}
                          </small>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Modal para crear tag */}
        {showCreateModal && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog modal-lg modal-dialog-scrollable" role="document">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">Crear Nuevo Tag</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowCreateModal(false);
                      setError(null);
                    }}
                    aria-label="Close"
                  ></button>
                </div>
                <form onSubmit={handleCreateTag}>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger" role="alert">
                        {error}
                      </div>
                    )}

                    <div className="row g-3">
                      {/* Campos requeridos */}
                      <div className="col-md-6">
                        <label className="form-label">
                          Nombre <span className="text-danger">*</span>
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          required
                          value={formData.name}
                          onChange={(e) =>
                            setFormData({ ...formData, name: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          Unit <span className="text-danger">*</span>
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          required
                          value={formData.unit}
                          onChange={(e) =>
                            setFormData({ ...formData, unit: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          Variable <span className="text-danger">*</span>
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          required
                          value={formData.variable}
                          onChange={(e) =>
                            setFormData({ ...formData, variable: e.target.value })
                          }
                          placeholder="e.g., Pressure, Temperature"
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Data Type</label>
                        <select
                          className="form-select"
                          value={formData.data_type}
                          onChange={(e) =>
                            setFormData({ ...formData, data_type: e.target.value })
                          }
                        >
                          <option value="float">float</option>
                          <option value="int">int</option>
                          <option value="bool">bool</option>
                          <option value="str">str</option>
                        </select>
                      </div>

                      {/* Campos opcionales básicos */}
                      <div className="col-md-6">
                        <label className="form-label">Display Name</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.display_name}
                          onChange={(e) =>
                            setFormData({ ...formData, display_name: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Display Unit</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.display_unit}
                          onChange={(e) =>
                            setFormData({ ...formData, display_unit: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-12">
                        <label className="form-label">Description</label>
                        <textarea
                          className="form-control"
                          rows={2}
                          value={formData.description}
                          onChange={(e) =>
                            setFormData({ ...formData, description: e.target.value })
                          }
                        />
                      </div>

                      {/* OPC UA */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">OPC UA Configuration</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">OPC UA Address</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.opcua_address}
                          onChange={(e) =>
                            setFormData({ ...formData, opcua_address: e.target.value })
                          }
                          placeholder="opc.tcp://host:port"
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Node Namespace</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.node_namespace}
                          onChange={(e) =>
                            setFormData({ ...formData, node_namespace: e.target.value })
                          }
                          placeholder="ns=2;i=1"
                        />
                      </div>

                      {/* Polling y Deadband */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">Polling Configuration</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Scan Time (ms)</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={formData.scan_time}
                          onChange={(e) =>
                            setFormData({ ...formData, scan_time: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Dead Band</label>
                        <input
                          type="number"
                          className="form-control"
                          step="0.01"
                          value={formData.dead_band}
                          onChange={(e) =>
                            setFormData({ ...formData, dead_band: e.target.value })
                          }
                        />
                      </div>

                      {/* Filtros */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">Filters</h6>
                      </div>
                      <div className="col-md-6">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.process_filter}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                process_filter: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">Process Filter</label>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.gaussian_filter}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                gaussian_filter: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">Gaussian Filter</label>
                        </div>
                      </div>
                      {formData.gaussian_filter && (
                        <>
                          <div className="col-md-6">
                            <label className="form-label">Gaussian Threshold</label>
                            <input
                              type="number"
                              className="form-control"
                              step="0.1"
                              value={formData.gaussian_filter_threshold}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  gaussian_filter_threshold: e.target.value,
                                })
                              }
                            />
                          </div>
                          <div className="col-md-6">
                            <label className="form-label">Gaussian R Value</label>
                            <input
                              type="number"
                              className="form-control"
                              step="0.1"
                              value={formData.gaussian_filter_r_value}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  gaussian_filter_r_value: e.target.value,
                                })
                              }
                            />
                          </div>
                        </>
                      )}

                      {/* Detección */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">Detection</h6>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.outlier_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                outlier_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">Outlier Detection</label>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.out_of_range_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                out_of_range_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">Out of Range Detection</label>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.frozen_data_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                frozen_data_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">Frozen Data Detection</label>
                        </div>
                      </div>

                      {/* Información adicional */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">Additional Information</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Segment</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.segment}
                          onChange={(e) =>
                            setFormData({ ...formData, segment: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">Manufacturer</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.manufacturer}
                          onChange={(e) =>
                            setFormData({ ...formData, manufacturer: e.target.value })
                          }
                        />
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowCreateModal(false);
                        setError(null);
                      }}
                      disabled={creating}
                    >
                      Cancelar
                    </button>
                    <Button type="submit" variant="success" loading={creating}>
                      Crear Tag
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
