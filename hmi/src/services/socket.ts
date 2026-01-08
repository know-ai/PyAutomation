import { io, Socket } from "socket.io-client";
import { SOCKET_IO_URL } from "../config/constants";
import type { Tag } from "./tags";
import type { Alarm } from "./alarms";
import type { Machine } from "./machines";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY } from "../store/slices/authSlice";

class SocketService {
  private socket: Socket | null = null;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = Infinity;
  private tagCallbacks: Array<(tag: Tag) => void> = [];
  private alarmCallbacks: Array<(alarm: Alarm) => void> = [];
  private machineCallbacks: Array<(machine: Machine) => void> = [];
  private opcuaDisconnectedCallbacks: Array<(data: { message: string; server_url?: string }) => void> = [];
  private opcuaConnectedCallbacks: Array<(data: { message: string; server_url?: string }) => void> = [];

  private getToken(): string | null {
    const state = store.getState();
    let token = state.auth.token;

    // Fallback al storage por si el estado aún no está hidratado
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

  connect(): void {
    if (this.socket?.connected) {
      return;
    }

    const token = this.getToken();
    if (!token) {
      return;
    }

    this.socket = io(SOCKET_IO_URL, {
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: this.maxReconnectAttempts,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
      auth: {
        token: token,
      },
      extraHeaders: {
        Authorization: `Bearer ${token}`,
      },
    });

    this.socket.on("connect", () => {
      this.isConnected = true;
      this.reconnectAttempts = 0;
    });

    this.socket.on("disconnect", () => {
      this.isConnected = false;
    });

    this.socket.on("connect_error", () => {
      this.reconnectAttempts++;
    });
  }

  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.isConnected = false;
    }
  }

  onTagUpdate(callback: (tag: Tag) => void): () => void {
    // Store callback for reconnection
    if (!this.tagCallbacks.includes(callback)) {
      this.tagCallbacks.push(callback);
    }

    const handler = (data: Tag) => {
      callback(data);
    };

    // Ensure socket is connected
    if (!this.socket || !this.socket.connected) {
      this.connect();
      // Wait for connection before adding listener
      if (this.socket) {
        this.socket.once("connect", () => {
          this.socket?.on("on.tag", handler);
        });
      }
    } else {
      // Socket is already connected, add listener immediately
      this.socket.on("on.tag", handler);
    }

    // Return cleanup function
    return () => {
      // Remove from callbacks array
      const index = this.tagCallbacks.indexOf(callback);
      if (index > -1) {
        this.tagCallbacks.splice(index, 1);
      }
      // Remove listener
      this.socket?.off("on.tag", handler);
    };
  }

  onAlarmUpdate(callback: (alarm: Alarm) => void): () => void {
    // Store callback for reconnection
    if (!this.alarmCallbacks.includes(callback)) {
      this.alarmCallbacks.push(callback);
    }

    const handler = (data: Alarm) => {
      callback(data);
    };

    // Ensure socket is connected
    if (!this.socket || !this.socket.connected) {
      this.connect();
      // Wait for connection before adding listener
      if (this.socket) {
        this.socket.once("connect", () => {
          this.socket?.on("on.alarm", handler);
        });
      }
    } else {
      // Socket is already connected, add listener immediately
      this.socket.on("on.alarm", handler);
    }

    // Return cleanup function
    return () => {
      // Remove from callbacks array
      const index = this.alarmCallbacks.indexOf(callback);
      if (index > -1) {
        this.alarmCallbacks.splice(index, 1);
      }
      // Remove listener
      this.socket?.off("on.alarm", handler);
    };
  }

  getSocket(): Socket | null {
    return this.socket;
  }

  onMachineUpdate(callback: (machine: Machine) => void): () => void {
    // Store callback for reconnection
    if (!this.machineCallbacks.includes(callback)) {
      this.machineCallbacks.push(callback);
    }

    const handler = (data: Machine) => {
      callback(data);
    };

    // Ensure socket is connected
    if (!this.socket || !this.socket.connected) {
      this.connect();
      // Wait for connection before adding listener
      if (this.socket) {
        this.socket.once("connect", () => {
          this.socket?.on("on.machine", handler);
        });
      }
    } else {
      // Socket is already connected, add listener immediately
      this.socket.on("on.machine", handler);
    }

    // Return cleanup function
    return () => {
      // Remove from callbacks array
      const index = this.machineCallbacks.indexOf(callback);
      if (index > -1) {
        this.machineCallbacks.splice(index, 1);
      }
      // Remove listener
      this.socket?.off("on.machine", handler);
    };
  }

  getIsConnected(): boolean {
    return this.isConnected;
  }

  onOpcUaDisconnected(callback: (data: { message: string; server_url?: string }) => void): () => void {
    // Store callback for reconnection
    if (!this.opcuaDisconnectedCallbacks.includes(callback)) {
      this.opcuaDisconnectedCallbacks.push(callback);
    }

    const handler = (data: { message: string; server_url?: string }) => {
      callback(data);
    };

    // Ensure socket is connected
    if (!this.socket || !this.socket.connected) {
      this.connect();
      // Wait for connection before adding listener
      if (this.socket) {
        this.socket.once("connect", () => {
          this.socket?.on("on.opcua.disconnected", handler);
        });
      }
    } else {
      // Socket is already connected, add listener immediately
      this.socket.on("on.opcua.disconnected", handler);
    }

    // Return cleanup function
    return () => {
      // Remove from callbacks array
      const index = this.opcuaDisconnectedCallbacks.indexOf(callback);
      if (index > -1) {
        this.opcuaDisconnectedCallbacks.splice(index, 1);
      }
      // Remove listener
      this.socket?.off("on.opcua.disconnected", handler);
    };
  }

  onOpcUaConnected(callback: (data: { message: string; server_url?: string }) => void): () => void {
    // Store callback for reconnection
    if (!this.opcuaConnectedCallbacks.includes(callback)) {
      this.opcuaConnectedCallbacks.push(callback);
    }

    const handler = (data: { message: string; server_url?: string }) => {
      callback(data);
    };

    // Ensure socket is connected
    if (!this.socket || !this.socket.connected) {
      this.connect();
      // Wait for connection before adding listener
      if (this.socket) {
        this.socket.once("connect", () => {
          this.socket?.on("on.opcua.connected", handler);
        });
      }
    } else {
      // Socket is already connected, add listener immediately
      this.socket.on("on.opcua.connected", handler);
    }

    // Return cleanup function
    return () => {
      // Remove from callbacks array
      const index = this.opcuaConnectedCallbacks.indexOf(callback);
      if (index > -1) {
        this.opcuaConnectedCallbacks.splice(index, 1);
      }
      // Remove listener
      this.socket?.off("on.opcua.connected", handler);
    };
  }
}

export const socketService = new SocketService();

