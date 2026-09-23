/**
 * Survives DomainConfigSlot remounts (tab spinner, leave/return to /machines/detailed)
 * so model upload progress and "Listo para Guardar" badges stay consistent.
 */

export type DomainUploadProgress = {
  percent: number;
  current: number;
  total: number;
  nodeLabel: string;
};

export type DomainUploadSession = {
  pendingFiles: Record<string, File[]>;
  uploadProgress: DomainUploadProgress | null;
  saving: boolean;
};

type Listener = () => void;

const sessions = new Map<string, DomainUploadSession>();
const listeners = new Map<string, Set<Listener>>();

function emptySession(): DomainUploadSession {
  return { pendingFiles: {}, uploadProgress: null, saving: false };
}

export function getDomainUploadSession(machineName: string): DomainUploadSession {
  const existing = sessions.get(machineName);
  if (existing) return existing;
  const created = emptySession();
  sessions.set(machineName, created);
  return created;
}

export function patchDomainUploadSession(
  machineName: string,
  patch: Partial<DomainUploadSession>
): DomainUploadSession {
  const prev = getDomainUploadSession(machineName);
  const next: DomainUploadSession = {
    pendingFiles: patch.pendingFiles !== undefined ? patch.pendingFiles : prev.pendingFiles,
    uploadProgress:
      patch.uploadProgress !== undefined ? patch.uploadProgress : prev.uploadProgress,
    saving: patch.saving !== undefined ? patch.saving : prev.saving,
  };
  sessions.set(machineName, next);
  for (const listener of listeners.get(machineName) || []) {
    listener();
  }
  return next;
}

export function clearDomainUploadSession(machineName: string): void {
  sessions.set(machineName, emptySession());
  for (const listener of listeners.get(machineName) || []) {
    listener();
  }
}

export function subscribeDomainUploadSession(
  machineName: string,
  listener: Listener
): () => void {
  let bucket = listeners.get(machineName);
  if (!bucket) {
    bucket = new Set();
    listeners.set(machineName, bucket);
  }
  bucket.add(listener);
  return () => {
    bucket?.delete(listener);
    if (bucket && bucket.size === 0) {
      listeners.delete(machineName);
    }
  };
}

/** Test helper — drop all in-memory upload sessions. */
export function resetDomainUploadSessionsForTests(): void {
  sessions.clear();
  listeners.clear();
}
