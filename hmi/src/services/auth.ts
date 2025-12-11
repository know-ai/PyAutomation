import api from "./api";

export type LoginPayload = { username: string; password: string };
export type SignupPayload = {
  username: string;
  email: string;
  password: string;
  role_name?: string;
  name?: string;
  lastname?: string;
};

export const login = async (payload: LoginPayload) => {
  const { data } = await api.post("/users/login", payload);
  return data;
};

export const signup = async (payload: SignupPayload) => {
  const { data } = await api.post("/users/signup", payload);
  return data;
};

export const forgotPassword = async (username: string, new_password: string) => {
  // Uses reset_password endpoint (no current password required)
  const { data } = await api.post("/users/reset_password", {
    target_username: username,
    new_password,
  });
  return data;
};


