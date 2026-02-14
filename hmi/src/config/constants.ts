/**
 * Obtiene una variable de entorno, primero desde window.__ENV__ (inyectada en runtime)
 * y luego desde import.meta.env (inyectada en build time)
 */
function getEnvVar(key: string): string | undefined {
  // Primero intentar desde window.__ENV__ (inyectado en runtime)
  if (typeof window !== "undefined" && (window as any).__ENV__) {
    const runtimeValue = (window as any).__ENV__[key];
    if (runtimeValue !== undefined && runtimeValue !== null && runtimeValue !== "") {
      return runtimeValue;
    }
  }
  // Fallback a import.meta.env (build time)
  const buildTimeValue = import.meta.env[key];
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
      return "https";
    }
    // Si es "false" o cualquier otro valor, usar HTTP
    return "http";
  }

  // Detectar desde window.location si estamos en HTTPS
  if (typeof window !== "undefined") {
    if (window.location.protocol === "https:") {
      return "https";
    }
  }

  // Fallback a HTTP
  return "http";
}

/**
 * Detecta automáticamente el host y puerto del backend desde la URL actual del navegador
 * cuando no hay variables de entorno configuradas
 */
function detectHostFromLocation(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    const port = window.location.port;
    // Si hay puerto en la URL, usarlo; si no, usar el puerto por defecto 8050
    return port ? `${host}:${port}` : `${host}:8050`;
  }
  return "localhost:8050";
}

/**
 * Obtiene la URL base de la API con detección automática de protocolo y host
 */
function getApiBaseUrl(): string {
  const envUrl = getEnvVar("VITE_API_BASE_URL") || import.meta.env.VITE_API_BASE_URL;
  const protocol = detectProtocol();
  const envHost = getEnvVar("VITE_API_HOST") || import.meta.env.VITE_API_HOST;
  
  // Si VITE_API_BASE_URL está completa, usarla directamente
  if (envUrl && (envUrl.startsWith("http://") || envUrl.startsWith("https://"))) {
    return envUrl.endsWith("/api") ? envUrl : `${envUrl}/api`;
  }

  // Si VITE_API_BASE_URL es solo la ruta sin protocolo
  if (envUrl && !envUrl.startsWith("http")) {
    return `${protocol}://${envUrl}`;
  }

  // Si hay VITE_API_HOST configurado, usarlo
  if (envHost) {
    return `${protocol}://${envHost}/api`;
  }

  // Si no hay variables de entorno, detectar automáticamente desde window.location
  const detectedHost = detectHostFromLocation();
  return `${protocol}://${detectedHost}/api`;
}

/**
 * Obtiene la URL de Socket.IO con detección automática de protocolo y host
 */
function getSocketIoUrl(): string {
  const envUrl = getEnvVar("VITE_SOCKET_IO_URL") || import.meta.env.VITE_SOCKET_IO_URL;
  const protocol = detectProtocol();
  const envHost = getEnvVar("VITE_API_HOST") || import.meta.env.VITE_API_HOST;

  // Si VITE_SOCKET_IO_URL está completa, usarla directamente
  if (envUrl && (envUrl.startsWith("http://") || envUrl.startsWith("https://"))) {
    return envUrl;
  }

  // Si VITE_SOCKET_IO_URL es solo el host sin protocolo
  if (envUrl && !envUrl.startsWith("http")) {
    return `${protocol}://${envUrl}`;
  }

  // Si hay VITE_API_HOST configurado, usarlo
  if (envHost) {
    return `${protocol}://${envHost}`;
  }

  // Si no hay variables de entorno, detectar automáticamente desde window.location
  const detectedHost = detectHostFromLocation();
  return `${protocol}://${detectedHost}`;
}

export const API_BASE_URL = getApiBaseUrl();
export const SOCKET_IO_URL = getSocketIoUrl();

// Exportar el protocolo detectado para uso en otros módulos
export const DETECTED_PROTOCOL = detectProtocol();


