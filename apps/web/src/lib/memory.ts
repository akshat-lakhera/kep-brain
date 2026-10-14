export const MEMORY_KEY = "kep.memoryId";

const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/** Generate a ULID (time-ordered, 26 Crockford base32 characters) with crypto randomness. */
export function newUlid(now: number = Date.now()): string {
  let time = "";
  let t = now;
  for (let i = 0; i < 10; i++) {
    time = CROCKFORD[t % 32] + time;
    t = Math.floor(t / 32);
  }
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let rand = "";
  for (const b of bytes) rand += CROCKFORD[b % 32];
  return time + rand;
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** Read the anonymous memory id, creating one on first use. Null when storage is unavailable. */
export function getMemoryId(): string | null {
  const s = storage();
  if (!s) return null;
  try {
    let id = s.getItem(MEMORY_KEY);
    if (!id) {
      id = newUlid();
      s.setItem(MEMORY_KEY, id);
    }
    return id;
  } catch {
    return null;
  }
}

/** Replace the memory id with a fresh one (a new anonymous tenant). */
export function resetMemoryId(): string | null {
  const s = storage();
  if (!s) return null;
  try {
    const id = newUlid();
    s.setItem(MEMORY_KEY, id);
    return id;
  } catch {
    return null;
  }
}
