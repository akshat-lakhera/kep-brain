/** Read a server-sent event stream from a fetch body (POST streams cannot use EventSource). */
export interface SseMessage {
  event: string;
  data: string;
}

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const i = line.indexOf(":");
    const field = i < 0 ? line : line.slice(0, i);
    const value = i < 0 ? "" : line.slice(i + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}

export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let sep = buffer.indexOf("\n\n");
      while (sep >= 0) {
        const msg = parseBlock(buffer.slice(0, sep));
        buffer = buffer.slice(sep + 2);
        if (msg) yield msg;
        sep = buffer.indexOf("\n\n");
      }
      if (done) {
        const last = parseBlock(buffer);
        if (last) yield last;
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
