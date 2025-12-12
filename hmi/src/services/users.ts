import api from "./api";

export type User = {
  identifier?: string;
  username: string;
  email?: string;
  name?: string;
  lastname?: string;
  role?: {
    name: string;
    level: number;
  };
  [key: string]: any;
};

export type UsersResponse = {
  data: User[];
  pagination: {
    page: number;
    limit: number;
    total_records: number;
    total_pages: number;
  };
};

export type ChangePasswordPayload = {
  target_username: string;
  new_password: string;
  current_password?: string;
};

export type ResetPasswordPayload = {
  target_username: string;
  new_password: string;
};

export type UpdateRolePayload = {
  target_username: string;
  new_role_name: string;
};

export type Role = {
  identifier?: string;
  name: string;
  level: number;
};

/**
 * Obtiene la lista de todos los roles disponibles (incluyendo sudo).
 */
export const getAllRoles = async (): Promise<Role[]> => {
  const { data } = await api.get("/users/roles/");
  return Array.isArray(data) ? data : [];
};

/**
 * Obtiene la lista de todos los roles disponibles (excluyendo sudo).
 */
export const getRoles = async (): Promise<Role[]> => {
  const roles = await getAllRoles();
  // Filtrar el rol sudo
  return roles.filter((role: Role) => role.name?.toLowerCase() !== "sudo");
};

export type CreateRolePayload = {
  name: string;
  level: number;
};

/**
 * Crea un nuevo rol
 */
export const createRole = async (payload: CreateRolePayload): Promise<Role> => {
  const { data } = await api.post("/users/roles/add", {
    name: payload.name.toUpperCase(), // Enviar en mayúsculas
    level: payload.level,
  });
  return data;
};

/**
 * Obtiene la lista de todos los usuarios con paginación.
 */
export const getUsers = async (page: number = 1, limit: number = 20): Promise<UsersResponse> => {
  const { data } = await api.get("/users/", {
    params: { page, limit },
  });
  return data;
};

/**
 * Obtiene todos los usuarios sin paginación (para compatibilidad hacia atrás).
 * Nota: Esta función puede ser lenta si hay muchos usuarios.
 */
export const getAllUsers = async (): Promise<User[]> => {
  const response = await getUsers(1, 10000);
  return response.data || [];
};

/**
 * Cambia la contraseña de un usuario
 */
export const changePassword = async (payload: ChangePasswordPayload): Promise<{ message: string }> => {
  const { data } = await api.post("/users/change_password", payload);
  return data;
};

/**
 * Resetea la contraseña de un usuario
 */
export const resetPassword = async (payload: ResetPasswordPayload): Promise<{ message: string }> => {
  const { data } = await api.post("/users/reset_password", payload);
  return data;
};

/**
 * Actualiza el rol de un usuario
 */
export const updateUserRole = async (payload: UpdateRolePayload): Promise<{ message: string }> => {
  const { data } = await api.post("/users/update_role", payload);
  return data;
};
