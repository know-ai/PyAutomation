/**
 * Listener mínimo de `on.tag` contra el backend PyAutomation (Socket.IO + WSS).
 *
 *   cd snippets/on-tag-wss
 *   npm install
 *   npm run dev
 *
 * Misma receta que la HMI (`hmi/src/services/socket.ts`):
 *   - URL https del origen (Socket.IO escala a wss)
 *   - transports websocket + polling
 *   - auth.token desde POST /api/users/login
 *
 * En Node hay un extra que el navegador no necesita: engine.io-client
 * defaulta `rejectUnauthorized: true`, así que un cert de lab tumba el
 * WebSocket aunque `NODE_TLS_REJECT_UNAUTHORIZED=0` deje pasar el login.
 */
import { io } from "socket.io-client";

// --- hardcode ---
const HOST = "https://192.168.1.80:8050"; // wss usa este origen https
const USERNAME = "admin";
const PASSWORD = "admin";
/** Certificado de lab (idetect.crt). Pon false si el cert es de CA pública. */
const ALLOW_SELF_SIGNED = true;
// --- /hardcode ---

if (ALLOW_SELF_SIGNED) {
  // Solo cubre fetch()/login. El handshake Socket.IO usa rejectUnauthorized.
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
}

async function login(): Promise<string> {
  const url = `${HOST.replace(/\/$/, "")}/api/users/login`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  const body = (await res.json().catch(() => ({}))) as {
    apiKey?: string;
    message?: string;
  };
  if (!res.ok || !body.apiKey) {
    throw new Error(
      `Login ${res.status}: ${body.message || JSON.stringify(body)}`
    );
  }
  console.log(`[login] ok user=${USERNAME}`);
  return body.apiKey;
}

function formatConnectError(err: Error): string {
  const extra = err as Error & {
    description?: unknown;
    context?: unknown;
    type?: string;
    data?: unknown;
  };
  const parts = [err.message];
  if (extra.type) parts.push(`type=${extra.type}`);
  if (extra.description) parts.push(`desc=${String(extra.description)}`);
  if (extra.context) parts.push(`ctx=${String(extra.context)}`);
  if (extra.data) parts.push(`data=${JSON.stringify(extra.data)}`);
  return parts.join(" | ");
}

async function main(): Promise<void> {
  const token = await login();
  const socket = io(HOST, {
    // Igual que SocketService.connect() en la HMI.
    transports: ["websocket", "polling"],
    reconnection: true,
    timeout: 15000,
    auth: (cb) => {
      cb({ token, reconnect: false });
    },
    // Node / engine.io-client: el default es true y el WSS de lab muere aquí.
    rejectUnauthorized: !ALLOW_SELF_SIGNED,
  });

  socket.on("connect", () => {
    const transport = socket.io.engine?.transport?.name ?? "unknown";
    console.log(`[socket] connected sid=${socket.id} transport=${transport}`);
  });
  socket.on("on_connection", (payload: unknown) => {
    const snap = payload as { tags?: unknown[] };
    console.log(
      `[on_connection] tags=${Array.isArray(snap.tags) ? snap.tags.length : "?"}`
    );
  });
  socket.on("on.tag", (payload: unknown) => {
    console.log("[on.tag]", JSON.stringify(payload));
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
