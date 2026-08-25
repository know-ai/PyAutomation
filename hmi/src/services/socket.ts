import { io, Socket } from "socket.io-client";
import { SOCKET_IO_URL } from "../config/constants";
import type { Tag } from "./tags";
import type { Alarm } from "./alarms";
import type { Machine } from "./machines";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY, logout } from "../store/slices/authSlice";
import { showToast } from "../utils/toast";

type FanoutHandler = (data: unknown) => void;

/** Initial system snapshot emitted by the server as `on_connection` after auth. */
export type SocketConnectionSnapshot = {
  tags?: Tag[];
  alarms?: Alarm[];
  machines?: Machine[];
  last_alarms?: unknown[];
  last_active_alarms?: Alarm[];
  last_events?: unknown[];
  last_logs?: unknown[];
};

export type SocketConnectionPhase = "connected" | "connecting" | "reconnecting" | "disconnected";

export type SocketConnectionState = {
  connected: boolean;
  connecting: boolean;
  /** true on connect after a prior disconnect in this session (not first connect). */
  reconnect: boolean;
  phase: SocketConnectionPhase;
};

type ConnectionListener = (state: SocketConnectionState) => void;
type TagActivityListener = (at: number) => void;

class SocketService {
  private socket: Socket | null = null;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = Infinity;
  private isConnecting: boolean = false;
  private wasDisconnected: boolean = false;
  private hadSuccessfulConnection: boolean = false;
  private lastToken: string | null = null;
  private disconnectedAt: number | null = null;
  private phaseTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Map<string, Set<FanoutHandler>>();
  private readonly nativeBound = new Set<string>();
  private readonly connectionListeners = new Set<ConnectionListener>();
  private readonly tagActivityListeners = new Set<TagActivityListener>();
  private lastOnTagAt: number | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  /** App-level session heartbeat (hmi_sessions); independent of Engine.IO ping. */
  private static readonly HEARTBEAT_MS = 15_000;
  /**
   * After transport disconnect, stay on "reconnecting" (yellow) this long before red.
   * With server ping_interval=15s + ping_timeout=30s, dead-peer detection is ≤45s;
   * 15s yellow grace keeps red within the overall 45s budget in typical cases.
   */
  static readonly DISCONNECTED_PHASE_MS = 15_000;
  /** Watchdog: no on.tag while socket is up → data-stale (yellow). */
  static readonly DATA_STALE_MS = 5_000;

  private computePhase(): SocketConnectionPhase {
    if (this.isConnected) {
      return "connected";
    }
    if (!this.hadSuccessfulConnection) {
      return this.isConnecting ? "connecting" : "disconnected";
    }
    const elapsed = this.disconnectedAt ? Date.now() - this.disconnectedAt : 0;
    if (elapsed >= SocketService.DISCONNECTED_PHASE_MS) {
      return "disconnected";
    }
    return "reconnecting";
  }

  private clearPhaseTimer(): void {
    if (this.phaseTimer) {
      clearTimeout(this.phaseTimer);
      this.phaseTimer = null;
    }
  }

  private schedulePhaseTimer(): void {
    this.clearPhaseTimer();
    if (!this.disconnectedAt || this.isConnected) {
      return;
    }
    const elapsed = Date.now() - this.disconnectedAt;
    const remaining = SocketService.DISCONNECTED_PHASE_MS - elapsed;
    if (remaining <= 0) {
      return;
    }
    this.phaseTimer = setTimeout(() => {
      this.phaseTimer = null;
      if (!this.isConnected) {
        this.emitConnection(false);
      }
    }, remaining);
  }

  private snapshot(reconnect = false): SocketConnectionState {
    return {
      connected: this.isConnected,
      connecting: this.isConnecting,
      reconnect,
      phase: this.computePhase(),
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

  onTagActivity(listener: TagActivityListener): () => void {
    this.tagActivityListeners.add(listener);
    if (this.lastOnTagAt !== null) {
      listener(this.lastOnTagAt);
    }
    return () => {
      this.tagActivityListeners.delete(listener);
    };
  }

  getLastOnTagAt(): number | null {
    return this.lastOnTagAt;
  }

  private noteTagActivity(): void {
    const at = Date.now();
    this.lastOnTagAt = at;
    for (const listener of this.tagActivityListeners) {
      listener(at);
    }
  }

  getConnectionPhase(): SocketConnectionPhase {
    return this.computePhase();
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

  private markDisconnected(): void {
    this.wasDisconnected = true;
    this.isConnected = false;
    this.isConnecting = false;
    if (!this.disconnectedAt) {
      this.disconnectedAt = Date.now();
    }
    this.stopHeartbeat();
    this.schedulePhaseTimer();
    this.emitConnection(false);
  }

  private markConnected(): void {
    // Only treat as reconnect when we had a prior disconnect in this session.
    const reconnect = this.wasDisconnected;
    this.hadSuccessfulConnection = true;
    this.wasDisconnected = false;
    this.isConnected = true;
    this.isConnecting = false;
    this.reconnectAttempts = 0;
    this.disconnectedAt = null;
    this.clearPhaseTimer();
    this.ensureTagActivityBinding();
    this.bindPendingNatives();
    this.startHeartbeat();
    this.emitConnection(reconnect);
  }

  /** Always listen for on.tag so the freshness watchdog arms even before UI subscribers. */
  private ensureTagActivityBinding(): void {
    if (!this.listeners.has("on.tag")) {
      this.listeners.set("on.tag", new Set());
    }
    this.bindNative("on.tag");
  }

  private handleConnectError(err: Error): void {
    this.reconnectAttempts++;
    this.isConnecting = false;
    this.emitConnection(false);
    const message = String(err?.message || err || "");
    if (message.includes("Authentication failed")) {
      this.stopHeartbeat();
      this.clearPhaseTimer();
      this.disconnectedAt = null;
      store.dispatch(logout());
      showToast("Session expired or invalid. Please sign in again.", "error");
    }
  }

  private bindNative(event: string): void {
    if (!this.socket || this.nativeBound.has(event)) {
      return;
    }
    this.socket.on(event, (data: unknown) => {
      if (event === "on.tag") {
        this.noteTagActivity();
      }
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
      // Keep false: connect() only after auth token is available.
      autoConnect: false,
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 500,
      reconnectionDelayMax: 5000,
      randomizationFactor: 0.5,
      timeout: 15000,
      auth: (cb) => {
        cb(this.socketAuthPayload());
      },
    });

    this.socket.on("connect", () => {
      this.markConnected();
    });

    this.socket.on("disconnect", () => {
      this.markDisconnected();
    });

    this.socket.on("connect_error", (err: Error) => {
      if (this.hadSuccessfulConnection) {
        this.wasDisconnected = true;
        if (!this.disconnectedAt) {
          this.disconnectedAt = Date.now();
          this.schedulePhaseTimer();
        }
      }
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
    this.clearPhaseTimer();
    this.disconnectedAt = null;
    this.lastOnTagAt = null;
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
    this.hadSuccessfulConnection = false;
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

  /**
   * Full runtime snapshot sent once after each successful Socket.IO auth.
   * Prefer this over waiting for `on.alarm` deltas (alarms may already be active).
   */
  onConnectionSnapshot(
    callback: (payload: SocketConnectionSnapshot) => void
  ): () => void {
    return this.subscribe<SocketConnectionSnapshot>("on_connection", callback);
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
