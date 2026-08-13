import { io, Socket } from "socket.io-client";
import { SOCKET_IO_URL } from "../config/constants";
import type { Tag } from "./tags";
import type { Alarm } from "./alarms";
import type { Machine } from "./machines";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY } from "../store/slices/authSlice";

type FanoutHandler = (data: unknown) => void;

class SocketService {
  private socket: Socket | null = null;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = Infinity;
  private isConnecting: boolean = false;
  private lastToken: string | null = null;
  private readonly listeners = new Map<string, Set<FanoutHandler>>();
  private readonly nativeBound = new Set<string>();

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
        try {
          (this.socket as any).auth = { token };
        } catch (_e) {
          // ignore
        }
        this.lastToken = token;
        this.socket.disconnect();
        this.isConnecting = true;
        this.socket.connect();
      }
      if (!this.socket.connected && !this.isConnecting) {
        this.isConnecting = true;
        this.socket.connect();
      }
      this.bindPendingNatives();
      return;
    }

    this.lastToken = token;
    this.isConnecting = true;

    this.socket = io(SOCKET_IO_URL, {
      autoConnect: false,
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
      auth: {
        token: token,
      },
    });

    this.socket.on("connect", () => {
      this.isConnected = true;
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      this.bindPendingNatives();
    });

    this.socket.on("disconnect", () => {
      this.isConnected = false;
      this.isConnecting = false;
    });

    this.socket.on("connect_error", () => {
      this.reconnectAttempts++;
      this.isConnecting = false;
    });

    this.bindPendingNatives();
    this.socket.connect();
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.removeAllListeners();
      this.socket.disconnect();
      this.socket = null;
    }
    this.nativeBound.clear();
    this.listeners.clear();
    this.isConnected = false;
    this.isConnecting = false;
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
}

export const socketService = new SocketService();
