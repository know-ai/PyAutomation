import { io, Socket } from "socket.io-client";
import { SOCKET_IO_URL } from "../config/constants";
import type { Tag } from "./tags";
import type { Alarm } from "./alarms";
import type { Machine } from "./machines";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY, logout } from "../store/slices/authSlice";
import { showToast } from "../utils/toast";

type FanoutHandler = (data: unknown) => void;

export type SocketConnectionState = {
  connected: boolean;
  connecting: boolean;
  /** true on connect after a prior disconnect in this session (not first connect). */
  reconnect: boolean;
};

type ConnectionListener = (state: SocketConnectionState) => void;

class SocketService {
  private socket: Socket | null = null;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = Infinity;
  private isConnecting: boolean = false;
  private wasDisconnected: boolean = false;
  private lastToken: string | null = null;
  private readonly listeners = new Map<string, Set<FanoutHandler>>();
  private readonly nativeBound = new Set<string>();
  private readonly connectionListeners = new Set<ConnectionListener>();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private static readonly HEARTBEAT_MS = 30_000;

  private snapshot(reconnect = false): SocketConnectionState {
    return {
      connected: this.isConnected,
      connecting: this.isConnecting,
      reconnect,
    };
  }

  private emitConnection(reconnect = false): void {
    const state = this.snapshot(reconnect);
    for (const listener of this.connectionListeners) {
      listener(state);
    }
  }

  onConnectionChange(listener: ConnectionListener): () => void {
    this.connectionListeners.add(listener);
    listener(this.snapshot(false));
    return () => {
      this.connectionListeners.delete(listener);
    };
  }

  private getToken(): string | null {
    const state = store.getState();
    let token = state.auth.token;

    if (!token) {
      try {
        const raw = localStorage.getItem(AUTH_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          token = parsed?.token ?? null;
        }
      } catch (_e) {
        // ignore
      }
    }

    return token;
  }

  private socketAuthPayload(): { token: string; reconnect: boolean } | Record<string, never> {
    const token = this.getToken();
    if (!token) return {};
    return { token, reconnect: this.wasDisconnected };
  }

  private applySocketAuth(): void {
    if (!this.socket) return;
    try {
      (this.socket as Socket & { auth?: unknown }).auth = this.socketAuthPayload();
    } catch (_e) {
      // ignore
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket?.connected) {
        this.socket.emit("ping");
      }
    }, SocketService.HEARTBEAT_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private handleConnectError(err: Error): void {
    this.reconnectAttempts++;
    this.isConnecting = false;
    this.emitConnection(false);
    const message = String(err?.message || err || "");
    if (message.includes("Authentication failed")) {
      this.stopHeartbeat();
      store.dispatch(logout());
      showToast("Session expired or invalid. Please sign in again.", "error");
    }
  }

  private bindNative(event: string): void {
    if (!this.socket || this.nativeBound.has(event)) {
      return;
    }
    this.socket.on(event, (data: unknown) => {
      const callbacks = this.listeners.get(event);
      if (!callbacks || callbacks.size === 0) {
        return;
      }
      for (const callback of callbacks) {
        callback(data);
      }
    });
    this.nativeBound.add(event);
  }

  private bindPendingNatives(): void {
    for (const event of this.listeners.keys()) {
      this.bindNative(event);
    }
  }

  private subscribe<T>(event: string, callback: (data: T) => void): () => void {
    let bucket = this.listeners.get(event);
    if (!bucket) {
      bucket = new Set();
      this.listeners.set(event, bucket);
    }
    const handler = callback as FanoutHandler;
    bucket.add(handler);
    this.connect();
    this.bindNative(event);
    return () => {
      this.listeners.get(event)?.delete(handler);
    };
  }

  connect(): void {
    const token = this.getToken();
    if (!token) {
      return;
    }

    if (this.socket) {
      if (this.lastToken !== token) {
        this.applySocketAuth();
        this.lastToken = token;
        this.socket.disconnect();
        this.isConnecting = true;
        this.emitConnection(false);
        this.socket.connect();
      }
      if (!this.socket.connected && !this.isConnecting) {
        this.isConnecting = true;
        this.emitConnection(false);
        this.socket.connect();
      }
      this.bindPendingNatives();
      return;
    }

    this.lastToken = token;
    this.isConnecting = true;
    this.emitConnection(false);

    this.socket = io(SOCKET_IO_URL, {
      autoConnect: false,
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
      auth: (cb) => {
        cb(this.socketAuthPayload());
      },
    });

    this.socket.on("connect", () => {
      const reconnect = this.wasDisconnected;
      this.wasDisconnected = false;
      this.isConnected = true;
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      this.bindPendingNatives();
      this.startHeartbeat();
      this.emitConnection(reconnect);
    });

    this.socket.on("disconnect", () => {
      this.wasDisconnected = true;
      this.isConnected = false;
      this.isConnecting = false;
      this.stopHeartbeat();
      this.emitConnection(false);
    });

    this.socket.on("connect_error", (err: Error) => {
      this.handleConnectError(err);
    });

    this.socket.io.on("reconnect_attempt", () => {
      if (this.isConnected) return;
      this.applySocketAuth();
      this.isConnecting = true;
      this.emitConnection(false);
    });

    this.bindPendingNatives();
    this.socket.connect();
  }

  disconnect(): void {
    this.stopHeartbeat();
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.disconnect();
      this.socket = null;
    }
    this.nativeBound.clear();
    this.listeners.clear();
    this.isConnected = false;
    this.isConnecting = false;
    this.wasDisconnected = false;
    this.emitConnection(false);
  }

  onLogUpdate(callback: (log: Record<string, unknown>) => void): () => void {
    return this.subscribe<Record<string, unknown>>("on.log", callback);
  }

  onTagUpdate(callback: (tag: Tag) => void): () => void {
    return this.subscribe<Tag>("on.tag", callback);
  }

  onAlarmUpdate(callback: (alarm: Alarm) => void): () => void {
    return this.subscribe<Alarm>("on.alarm", callback);
  }

  getSocket(): Socket | null {
    return this.socket;
  }

  onMachineUpdate(callback: (machine: Machine) => void): () => void {
    return this.subscribe<Machine>("on.machine", callback);
  }

  getIsConnected(): boolean {
    return this.isConnected;
  }

  onMachinePropertyUpdate(
    callback: (data: Record<string, Record<string, any>>) => void
  ): () => void {
    return this.subscribe<Record<string, Record<string, any>>>(
      "on.machine.property",
      callback
    );
  }

  onOpcUaDisconnected(
    callback: (data: { message: string; server_url?: string }) => void
  ): () => void {
    return this.subscribe<{ message: string; server_url?: string }>(
      "on.opcua.disconnected",
      callback
    );
  }

  onOpcUaConnected(
    callback: (data: { message: string; server_url?: string }) => void
  ): () => void {
    return this.subscribe<{ message: string; server_url?: string }>(
      "on.opcua.connected",
      callback
    );
  }

  nativeListenerCount(event: string): number {
    return this.socket?.listeners(event).length ?? 0;
  }

  callbackCount(event: string): number {
    return this.listeners.get(event)?.size ?? 0;
  }

  listenerCount(event?: string): Record<string, { native: number; callbacks: number }> | { native: number; callbacks: number } {
    if (event) {
      return {
        native: this.nativeListenerCount(event),
        callbacks: this.callbackCount(event),
      };
    }
    const snapshot: Record<string, { native: number; callbacks: number }> = {};
    for (const name of this.listeners.keys()) {
      snapshot[name] = {
        native: this.nativeListenerCount(name),
        callbacks: this.callbackCount(name),
      };
    }
    return snapshot;
  }
}

export const socketService = new SocketService();
