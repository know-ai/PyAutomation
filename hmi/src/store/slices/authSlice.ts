import { createSlice, PayloadAction } from "@reduxjs/toolkit";

const AUTH_STORAGE_KEY = "pyautomation.auth";

const persistAuth = (state: AuthState) => {
  try {
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({
        token: state.token,
        user: state.user,
        status: state.status,
        error: null,
      })
    );
  } catch (_e) {
    // ignore persistence errors (e.g., SSR)
  }
};

const clearPersistedAuth = () => {
  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch (_e) {
    // ignore
  }
};

export type AuthUser = {
  username: string;
  role?: string;
  email?: string;
};

export type AuthState = {
  token: string | null;
  user: AuthUser | null;
  status: "idle" | "loading" | "authenticated" | "error";
  error?: string | null;
};

const initialState: AuthState = {
  token: null,
  user: null,
  status: "idle",
  error: null,
};

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    loginStart(state) {
      state.status = "loading";
      state.error = null;
    },
    loginSuccess(state, action: PayloadAction<{ token: string; user: AuthUser }>) {
      state.status = "authenticated";
      state.token = action.payload.token;
      state.user = action.payload.user;
      state.error = null;
      persistAuth(state);
    },
    loginFailure(state, action: PayloadAction<string>) {
      state.status = "error";
      state.error = action.payload;
    },
    logout(state) {
      state.token = null;
      state.user = null;
      state.status = "idle";
      state.error = null;
      clearPersistedAuth();
    },
    setUser(state, action: PayloadAction<AuthUser | null>) {
      state.user = action.payload;
    },
  },
});

export const { loginStart, loginSuccess, loginFailure, logout, setUser } =
  authSlice.actions;

export default authSlice.reducer;

export { AUTH_STORAGE_KEY };
