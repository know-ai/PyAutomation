import type { AxiosRequestConfig } from "axios";
import api from "./api";

export type OperatorConfirmationPolicy = {
  enabled: boolean;
  updatedAt?: string | null;
};

export type ConfirmActionRequest = {
  username: string;
  password: string;
  method: "POST" | "PUT";
  path: string;
  to?: string;
};

export function confirmationHeaders(token?: string | null): AxiosRequestConfig | undefined {
  if (!token) return undefined;
  return { headers: { "X-Operator-Confirmation": token } };
}

export async function getOperatorConfirmation(): Promise<OperatorConfirmationPolicy> {
  const { data } = await api.get("/settings/operator-confirmation");
  return { enabled: Boolean(data?.enabled), updatedAt: data?.updatedAt ?? null };
}

export async function putOperatorConfirmation(enabled: boolean): Promise<OperatorConfirmationPolicy> {
  const { data } = await api.put("/settings/operator-confirmation", { enabled });
  return { enabled: Boolean(data?.enabled), updatedAt: data?.updatedAt ?? null };
}

export async function confirmOperatorAction(
  body: ConfirmActionRequest
): Promise<{ token: string; username: string }> {
  const { data } = await api.post("/users/confirm-action", body);
  return data;
}
