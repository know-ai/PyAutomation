import { useAppSelector } from "./useAppSelector";

export const useAuth = () => {
  const { token, user, status } = useAppSelector((s) => s.auth);
  return { token, user, status, isAuthenticated: !!token };
};


