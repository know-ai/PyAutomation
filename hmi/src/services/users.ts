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

/**
 * Obtiene la lista de todos los usuarios
 */
export const getUsers = async (): Promise<User[]> => {
  const { data } = await api.get("/users/");
  return data || [];
};

