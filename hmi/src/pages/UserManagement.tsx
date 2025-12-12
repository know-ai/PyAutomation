import { useEffect, useState, useCallback } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getUsers, changePassword, resetPassword, updateUserRole, getRoles, getAllRoles, createRole, type User, type UsersResponse, type Role, type CreateRolePayload } from "../services/users";
import { useTranslation } from "../hooks/useTranslation";

export function UserManagement() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });

  // Estado para los modales
  const [showChangePasswordModal, setShowChangePasswordModal] = useState(false);
  const [showResetPasswordModal, setShowResetPasswordModal] = useState(false);
  const [showUpdateRoleModal, setShowUpdateRoleModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [selectedRole, setSelectedRole] = useState("");
  const [availableRoles, setAvailableRoles] = useState<Role[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  
  // Estado para gestión de roles
  const [showRolesModal, setShowRolesModal] = useState(false);
  const [allRoles, setAllRoles] = useState<Role[]>([]);
  const [loadingRoles, setLoadingRoles] = useState(false);
  const [newRoleName, setNewRoleName] = useState("");
  const [newRoleLevel, setNewRoleLevel] = useState<number>(2);
  const [roleError, setRoleError] = useState<string | null>(null);
  const [isCreatingRole, setIsCreatingRole] = useState(false);
  const [rolesPage, setRolesPage] = useState(1);
  const rolesPerPage = 5;

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response: UsersResponse = await getUsers(pagination.page, pagination.limit);
      setUsers(response.data || []);
      setPagination((prev) => ({
        ...prev,
        page: response.pagination.page || 1,
        limit: response.pagination.limit || 20,
        total: response.pagination.total_records || 0,
        pages: response.pagination.total_pages || 0,
      }));
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los usuarios";
      setError(errorMsg);
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [pagination.page, pagination.limit]);

  // Cargar usuarios al montar y cuando cambia la paginación
  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  // Cargar roles disponibles al montar
  useEffect(() => {
    const loadRoles = async () => {
      try {
        const roles = await getRoles();
        setAvailableRoles(roles);
      } catch (e: any) {
        console.error("Error al cargar roles:", e);
      }
    };
    loadRoles();
  }, []);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setPagination({ ...pagination, page: newPage });
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setPagination({ ...pagination, page: 1, limit: newLimit });
    }
  };

  const handleOpenChangePassword = (user: User) => {
    setSelectedUser(user);
    setNewPassword("");
    setCurrentPassword("");
    setConfirmPassword("");
    setError(null);
    setShowChangePasswordModal(true);
  };

  const handleOpenResetPassword = (user: User) => {
    setSelectedUser(user);
    setNewPassword("");
    setConfirmPassword("");
    setError(null);
    setShowResetPasswordModal(true);
  };

  const handleOpenUpdateRole = (user: User) => {
    setSelectedUser(user);
    setSelectedRole(user.role?.name || "");
    setError(null);
    setShowUpdateRoleModal(true);
  };

  const handleChangePassword = async () => {
    if (!selectedUser) return;

    if (!newPassword || !confirmPassword) {
      setError("Todos los campos son requeridos");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }

    setIsProcessing(true);
    setError(null);
    try {
      await changePassword({
        target_username: selectedUser.username,
        new_password: newPassword,
        current_password: currentPassword || undefined,
      });
      setShowChangePasswordModal(false);
      setSelectedUser(null);
      setNewPassword("");
      setCurrentPassword("");
      setConfirmPassword("");
      // Recargar usuarios
      loadUsers();
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cambiar la contraseña";
      setError(errorMsg);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleResetPassword = async () => {
    if (!selectedUser) return;

    if (!newPassword || !confirmPassword) {
      setError("Todos los campos son requeridos");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }

    setIsProcessing(true);
    setError(null);
    try {
      await resetPassword({
        target_username: selectedUser.username,
        new_password: newPassword,
      });
      setShowResetPasswordModal(false);
      setSelectedUser(null);
      setNewPassword("");
      setConfirmPassword("");
      // Recargar usuarios
      loadUsers();
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al resetear la contraseña";
      setError(errorMsg);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleUpdateRole = async () => {
    if (!selectedUser || !selectedRole) return;

    setIsProcessing(true);
    setError(null);
    try {
      await updateUserRole({
        target_username: selectedUser.username,
        new_role_name: selectedRole,
      });
      setShowUpdateRoleModal(false);
      setSelectedUser(null);
      setSelectedRole("");
      // Recargar usuarios
      loadUsers();
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al actualizar el rol";
      setError(errorMsg);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleOpenRolesManagement = async () => {
    setShowRolesModal(true);
    setRoleError(null);
    setNewRoleName("");
    setNewRoleLevel(2);
    await loadAllRoles();
  };

  const loadAllRoles = async () => {
    setLoadingRoles(true);
    try {
      const roles = await getAllRoles();
      setAllRoles(roles);
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los roles";
      setRoleError(errorMsg);
    } finally {
      setLoadingRoles(false);
    }
  };

  const handleCreateRole = async () => {
    if (!newRoleName.trim()) {
      setRoleError("El nombre del rol es requerido");
      return;
    }

    if (newRoleLevel < 2) {
      setRoleError("El nivel del rol debe ser 2 o mayor");
      return;
    }

    setIsCreatingRole(true);
    setRoleError(null);
    try {
      await createRole({
        name: newRoleName.trim(),
        level: newRoleLevel,
      });
      setNewRoleName("");
      setNewRoleLevel(2);
      // Recargar roles y también actualizar los roles disponibles para el dropdown
      await loadAllRoles();
      const roles = await getRoles();
      setAvailableRoles(roles);
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al crear el rol";
      setRoleError(errorMsg);
    } finally {
      setIsCreatingRole(false);
    }
  };

  const handleCloseModals = () => {
    setShowChangePasswordModal(false);
    setShowResetPasswordModal(false);
    setShowUpdateRoleModal(false);
    setShowRolesModal(false);
    setSelectedUser(null);
    setNewPassword("");
    setCurrentPassword("");
    setConfirmPassword("");
    setSelectedRole("");
    setError(null);
    setRoleError(null);
    setNewRoleName("");
    setNewRoleLevel(2);
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex justify-content-between align-items-center w-100">
              <h3 className="card-title m-0">Gestión de Usuarios</h3>
              <Button
                variant="info"
                className="btn-sm"
                onClick={handleOpenRolesManagement}
                title="Gestionar roles"
              >
                <i className="bi bi-shield-check me-1"></i>
                Gestionar Roles
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
          {error && !showChangePasswordModal && !showResetPasswordModal && !showUpdateRoleModal && (
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
            <div className="table-responsive" style={{ maxHeight: "70vh", overflowY: "auto" }}>
              <table className="table table-striped table-hover table-sm">
                <thead className="table-light" style={{ position: "sticky", top: 0, zIndex: 10 }}>
                  <tr>
                    <th>{t("tables.username")}</th>
                    <th>{t("tables.email")}</th>
                    <th>{t("tables.name")}</th>
                    <th>{t("tables.lastname")}</th>
                    <th>{t("tables.role")}</th>
                    <th>{t("tables.roleLevel")}</th>
                    <th>{t("tables.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center text-muted py-4">
                        No hay usuarios disponibles
                      </td>
                    </tr>
                  ) : (
                    users.map((user) => (
                      <tr key={user.username}>
                        <td>
                          <strong>{user.username || "-"}</strong>
                        </td>
                        <td>{user.email || "-"}</td>
                        <td>{user.name || "-"}</td>
                        <td>{user.lastname || "-"}</td>
                        <td>
                          <span className="badge bg-info">{user.role?.name || "-"}</span>
                        </td>
                        <td>{user.role?.level !== undefined ? user.role.level : "-"}</td>
                        <td>
                          <div className="btn-group" role="group">
                            <Button
                              variant="primary"
                              className="btn-sm"
                              onClick={() => handleOpenChangePassword(user)}
                              title="Cambiar contraseña"
                            >
                              <i className="bi bi-key"></i>
                            </Button>
                            <Button
                              variant="danger"
                              className="btn-sm"
                              onClick={() => handleOpenResetPassword(user)}
                              title="Resetear contraseña"
                            >
                              <i className="bi bi-arrow-clockwise"></i>
                            </Button>
                            <Button
                              variant="success"
                              className="btn-sm"
                              onClick={() => handleOpenUpdateRole(user)}
                              title="Actualizar rol"
                            >
                              <i className="bi bi-person-badge"></i>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Modal para cambiar contraseña */}
          {showChangePasswordModal && selectedUser && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={handleCloseModals}
            >
              <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">Cambiar Contraseña - {selectedUser.username}</h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCloseModals}
                    ></button>
                  </div>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger mb-3" role="alert">
                        {error}
                      </div>
                    )}
                    <div className="mb-3">
                      <label className="form-label">Contraseña Actual (opcional)</label>
                      <input
                        type="password"
                        className="form-control"
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="Ingrese la contraseña actual (requerida si cambia su propia contraseña)"
                      />
                    </div>
                    <div className="mb-3">
                      <label className="form-label">Nueva Contraseña *</label>
                      <input
                        type="password"
                        className="form-control"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Ingrese la nueva contraseña"
                      />
                    </div>
                    <div className="mb-3">
                      <label className="form-label">Confirmar Nueva Contraseña *</label>
                      <input
                        type="password"
                        className="form-control"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Confirme la nueva contraseña"
                      />
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={handleCloseModals}
                      disabled={isProcessing}
                    >
                      Cancelar
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleChangePassword}
                      disabled={isProcessing || !newPassword || !confirmPassword}
                      loading={isProcessing}
                    >
                      Cambiar Contraseña
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Modal para resetear contraseña */}
          {showResetPasswordModal && selectedUser && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={handleCloseModals}
            >
              <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">Resetear Contraseña - {selectedUser.username}</h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCloseModals}
                    ></button>
                  </div>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger mb-3" role="alert">
                        {error}
                      </div>
                    )}
                    <div className="alert alert-warning mb-3" role="alert">
                      <i className="bi bi-exclamation-triangle me-2"></i>
                      Esta acción reseteará la contraseña sin requerir la contraseña actual.
                    </div>
                    <div className="mb-3">
                      <label className="form-label">Nueva Contraseña *</label>
                      <input
                        type="password"
                        className="form-control"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="Ingrese la nueva contraseña"
                      />
                    </div>
                    <div className="mb-3">
                      <label className="form-label">Confirmar Nueva Contraseña *</label>
                      <input
                        type="password"
                        className="form-control"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Confirme la nueva contraseña"
                      />
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={handleCloseModals}
                      disabled={isProcessing}
                    >
                      Cancelar
                    </Button>
                    <Button
                      variant="danger"
                      onClick={handleResetPassword}
                      disabled={isProcessing || !newPassword || !confirmPassword}
                      loading={isProcessing}
                    >
                      Resetear Contraseña
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Modal para actualizar rol */}
          {showUpdateRoleModal && selectedUser && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={handleCloseModals}
            >
              <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">Actualizar Rol - {selectedUser.username}</h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCloseModals}
                    ></button>
                  </div>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger mb-3" role="alert">
                        {error}
                      </div>
                    )}
                    <div className="mb-3">
                      <label className="form-label">Rol Actual</label>
                      <input
                        type="text"
                        className="form-control"
                        value={selectedUser.role?.name || "-"}
                        disabled
                      />
                    </div>
                    <div className="mb-3">
                      <label className="form-label">Nuevo Rol *</label>
                      <select
                        className="form-select"
                        value={selectedRole}
                        onChange={(e) => setSelectedRole(e.target.value)}
                      >
                        <option value="">Seleccione un rol</option>
                        {availableRoles.map((role) => (
                          <option key={role.name} value={role.name}>
                            {role.name} (Nivel: {role.level})
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={handleCloseModals}
                      disabled={isProcessing}
                    >
                      Cancelar
                    </Button>
                    <Button
                      variant="success"
                      onClick={handleUpdateRole}
                      disabled={isProcessing || !selectedRole}
                      loading={isProcessing}
                    >
                      Actualizar Rol
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Modal para gestionar roles */}
          {showRolesModal && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={handleCloseModals}
            >
              <div className="modal-dialog modal-lg" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">Gestión de Roles</h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCloseModals}
                    ></button>
                  </div>
                  <div className="modal-body">
                    {roleError && (
                      <div className="alert alert-danger mb-3" role="alert">
                        {roleError}
                      </div>
                    )}

                    {/* Formulario para agregar nuevo rol */}
                    <div className="card mb-4">
                      <div className="card-header">
                        <h6 className="mb-0">Agregar Nuevo Rol</h6>
                      </div>
                      <div className="card-body">
                        <div className="row">
                          <div className="col-md-6 mb-3">
                            <label className="form-label">Nombre del Rol *</label>
                            <input
                              type="text"
                              className="form-control"
                              value={newRoleName}
                              onChange={(e) => setNewRoleName(e.target.value)}
                              placeholder="Ej: OPERATOR"
                              disabled={isCreatingRole}
                            />
                          </div>
                          <div className="col-md-4 mb-3">
                            <label className="form-label">Nivel del Rol *</label>
                            <input
                              type="number"
                              className="form-control"
                              value={newRoleLevel}
                              onChange={(e) => {
                                const level = parseInt(e.target.value) || 2;
                                if (level >= 2) {
                                  setNewRoleLevel(level);
                                }
                              }}
                              min={2}
                              disabled={isCreatingRole}
                            />
                          </div>
                          <div className="col-md-2 mb-3 d-flex align-items-end">
                            <Button
                              variant="success"
                              onClick={handleCreateRole}
                              disabled={isCreatingRole || !newRoleName.trim() || newRoleLevel < 2}
                              loading={isCreatingRole}
                              className="w-100"
                            >
                              Agregar
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Lista de roles existentes */}
                    <div className="card">
                      <div className="card-header">
                        <h6 className="mb-0">Roles Disponibles</h6>
                      </div>
                      <div className="card-body">
                        {loadingRoles ? (
                          <div className="text-center py-4">
                            <div className="spinner-border text-primary" role="status">
                              <span className="visually-hidden">Cargando...</span>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="table-responsive">
                              <table className="table table-striped table-hover table-sm">
                                <thead className="table-light">
                                  <tr>
                                    <th>{t("tables.name")}</th>
                                    <th>{t("tables.level")}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {allRoles.length === 0 ? (
                                    <tr>
                                      <td colSpan={2} className="text-center text-muted py-4">
                                        No hay roles disponibles
                                      </td>
                                    </tr>
                                  ) : (
                                    (() => {
                                      const startIndex = (rolesPage - 1) * rolesPerPage;
                                      const endIndex = startIndex + rolesPerPage;
                                      const paginatedRoles = allRoles.slice(startIndex, endIndex);

                                      return paginatedRoles.map((role) => (
                                        <tr key={role.name}>
                                          <td>
                                            <span className="badge bg-info">{role.name || "-"}</span>
                                          </td>
                                          <td>{role.level !== undefined ? role.level : "-"}</td>
                                        </tr>
                                      ));
                                    })()
                                  )}
                                </tbody>
                              </table>
                            </div>
                            {allRoles.length > rolesPerPage && (
                              <div className="d-flex justify-content-between align-items-center mt-3">
                                <span className="small text-muted">
                                  Página {rolesPage} de {Math.ceil(allRoles.length / rolesPerPage)} ({allRoles.length} total)
                                </span>
                                <div className="btn-group" role="group">
                                  <Button
                                    variant="secondary"
                                    className="btn-sm"
                                    onClick={() => setRolesPage(1)}
                                    disabled={rolesPage === 1}
                                  >
                                    «
                                  </Button>
                                  <Button
                                    variant="secondary"
                                    className="btn-sm"
                                    onClick={() => setRolesPage((prev) => Math.max(1, prev - 1))}
                                    disabled={rolesPage === 1}
                                  >
                                    ‹
                                  </Button>
                                  <Button
                                    variant="secondary"
                                    className="btn-sm"
                                    onClick={() => setRolesPage((prev) => Math.min(Math.ceil(allRoles.length / rolesPerPage), prev + 1))}
                                    disabled={rolesPage >= Math.ceil(allRoles.length / rolesPerPage)}
                                  >
                                    ›
                                  </Button>
                                  <Button
                                    variant="secondary"
                                    className="btn-sm"
                                    onClick={() => setRolesPage(Math.ceil(allRoles.length / rolesPerPage))}
                                    disabled={rolesPage >= Math.ceil(allRoles.length / rolesPerPage)}
                                  >
                                    »
                                  </Button>
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={handleCloseModals}
                      disabled={isCreatingRole}
                    >
                      Cerrar
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
