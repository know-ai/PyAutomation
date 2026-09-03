import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { getAuthzMe, type AuthzActionsMap } from "../../services/authz";
import { loginStart, logout } from "./authSlice";

export type AuthzState = {
  views: AuthzActionsMap;
  rest: AuthzActionsMap;
  status: "idle" | "loading" | "ready" | "error";
};

const initialState: AuthzState = {
  views: {},
  rest: {},
  status: "idle",
};

export const loadAuthzMe = createAsyncThunk("authz/loadMe", async () => {
  return getAuthzMe();
});

const authzSlice = createSlice({
  name: "authz",
  initialState,
  reducers: {
    clearAuthz() {
      return initialState;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadAuthzMe.pending, (state) => {
        state.status = "loading";
      })
      .addCase(loadAuthzMe.fulfilled, (state, action) => {
        state.views = action.payload.views || {};
        state.rest = action.payload.rest || {};
        state.status = "ready";
      })
      .addCase(loadAuthzMe.rejected, (state) => {
        state.status = "error";
        state.views = {};
        state.rest = {};
      })
      .addCase(logout, () => initialState)
      .addCase(loginStart, () => initialState);
  },
});

export const { clearAuthz } = authzSlice.actions;
export default authzSlice.reducer;
