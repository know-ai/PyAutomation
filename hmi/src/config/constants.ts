/**
 * Obtiene una variable de entorno, primero desde window.__ENV__ (inyectada en runtime)
 * y luego desde import.meta.env (inyectada en build time)
 */
function getEnvVar(key: string): string | undefined {
  // Primero intentar desde window.__ENV__ (inyectado en runtime)
  if (typeof window !== "undefined" && (window as any).__ENV__) {
    const runtimeValue = (window as any).__ENV__[key];
    if (runtimeValue !== undefined && runtimeValue !== null && runtimeValue !== "") {
      console.log(`[DEBUG] ${key} encontrado en window.__ENV__:`, runtimeValue);
      return runtimeValue;
    }
  }
  // Fallback a import.meta.env (build time)
  const buildTimeValue = import.meta.env[key];
  if (buildTimeValue !== undefined) {
    console.log(`[DEBUG] ${key} encontrado en import.meta.env:`, buildTimeValue);
  }
  return buildTimeValue;
}

/**
 * Detecta automáticamente el protocolo (HTTP/HTTPS) basándose en:
 * 1. Variable de entorno VITE_API_BASE_URL (si incluye protocolo)
 * 2. Variable de entorno VITE_USE_HTTPS (booleano)
 * 3. Protocolo de la página actual (si estamos en HTTPS, usar HTTPS)
 * 4. Fallback a HTTP por defecto
 */
function detectProtocol(): "http" | "https" {
  const envUrl = getEnvVar("VITE_API_BASE_URL") || import.meta.env.VITE_API_BASE_URL;
  const useHttps = getEnvVar("VITE_USE_HTTPS") || import.meta.env.VITE_USE_HTTPS;

  // Si VITE_API_BASE_URL incluye protocolo, extraerlo
  if (envUrl) {
    if (envUrl.startsWith("https://")) {
      return "https";
    }
    if (envUrl.startsWith("http://")) {
      return "http";
    }
  }

  // Si VITE_USE_HTTPS está definido, usarlo (tiene prioridad sobre detección automática)
  // Acepta tanto string "true"/"false" como boolean true/false
  if (useHttps !== undefined && useHttps !== null && useHttps !== "") {
    const useHttpsStr = String(useHttps).toLowerCase().trim();
    if (useHttpsStr === "true" || useHttps === true) {
      console.log("[DEBUG] VITE_USE_HTTPS=true detectado, usando HTTPS");
      return "https";
    }
    // Si es "false" o cualquier otro valor, usar HTTP
    console.log("[DEBUG] VITE_USE_HTTPS=false o no válido, usando HTTP");
    return "http";
  }

  // Detectar desde window.location si estamos en HTTPS
  if (typeof window !== "undefined") {
    if (window.location.protocol === "https:") {
      console.log("[DEBUG] Protocolo HTTPS detectado desde window.location");
      return "https";
    }
  }

  // Fallback a HTTP
  console.log("[DEBUG] Usando HTTP por defecto");
  return "http";
}

/**
 * Obtiene la URL base de la API con detección automática de protocolo
 */
function getApiBaseUrl(): string {
  const envUrl = getEnvVar("VITE_API_BASE_URL") || import.meta.env.VITE_API_BASE_URL;
  const protocol = detectProtocol();
  const defaultHost = getEnvVar("VITE_API_HOST") || import.meta.env.VITE_API_HOST || "localhost:8050";

  // Si VITE_API_BASE_URL está completa, usarla directamente
  if (envUrl && (envUrl.startsWith("http://") || envUrl.startsWith("https://"))) {
    return envUrl.endsWith("/api") ? envUrl : `${envUrl}/api`;
  }

  // Si VITE_API_BASE_URL es solo la ruta sin protocolo
  if (envUrl && !envUrl.startsWith("http")) {
    return `${protocol}://${envUrl}`;
  }

  // Construir URL con protocolo detectado
  return `${protocol}://${defaultHost}/api`;
}

/**
 * Obtiene la URL de Socket.IO con detección automática de protocolo
 */
function getSocketIoUrl(): string {
  const envUrl = getEnvVar("VITE_SOCKET_IO_URL") || import.meta.env.VITE_SOCKET_IO_URL;
  const protocol = detectProtocol();
  const defaultHost = getEnvVar("VITE_API_HOST") || import.meta.env.VITE_API_HOST || "localhost:8050";

  // Si VITE_SOCKET_IO_URL está completa, usarla directamente
  if (envUrl && (envUrl.startsWith("http://") || envUrl.startsWith("https://"))) {
    return envUrl;
  }

  // Si VITE_SOCKET_IO_URL es solo el host sin protocolo
  if (envUrl && !envUrl.startsWith("http")) {
    return `${protocol}://${envUrl}`;
  }

  // Construir URL con protocolo detectado
  return `${protocol}://${defaultHost}`;
}

export const API_BASE_URL = getApiBaseUrl();
export const SOCKET_IO_URL = getSocketIoUrl();

// Exportar el protocolo detectado para uso en otros módulos
export const DETECTED_PROTOCOL = detectProtocol();


