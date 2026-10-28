import { AuthError, DarkmoonError, NetworkError, SchemaInvalid } from "../errors.js";

/** JSON SSE with an idle timeout, bounded frames and cancellation on early exit. */
export async function* readSse(
  url: string,
  opts: { token?: string | null; signal?: AbortSignal; timeoutMs?: number } = {},
): AsyncGenerator<unknown, void, unknown> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeoutMs = opts.timeoutMs ?? 15_000;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const arm = () => { clearTimeout(timer); timer = setTimeout(abort, timeoutMs); };
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  if (opts.signal?.aborted) return;
  opts.signal?.addEventListener("abort", abort, { once: true });
  try {
    arm();
    const res = await fetch(url, { headers, signal: controller.signal, redirect: "manual" });
    if (res.status === 401 || res.status === 403) throw new AuthError(`SSE unauthorized (HTTP ${res.status}).`);
    if (!res.ok || !res.body) throw new NetworkError(`SSE stream returned HTTP ${res.status}.`, { status: res.status });
    if (!/^text\/event-stream(?:;|$)/i.test(res.headers.get("content-type") ?? "")) throw new SchemaInvalid("SSE response has an invalid content type.");
    reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let data: string[] = [];
    let frameSize = 0;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim() || data.length) throw new SchemaInvalid("SSE ended with an incomplete frame.");
        return;
      }
      arm(); // Heartbeats count as activity; this is not a total run deadline.
      buffer += decoder.decode(value, { stream: true });
      for (;;) {
        const match = /\r\n|\r|\n/.exec(buffer);
        if (!match || (match[0] === "\r" && match.index === buffer.length - 1)) break;
        const line = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        frameSize += line.length;
        if (frameSize > 1024 * 1024) throw new SchemaInvalid("SSE frame exceeds the size limit.");
        if (!line) {
          if (data.length) {
            let payload: unknown;
            try { payload = JSON.parse(data.join("\n")); }
            catch { throw new SchemaInvalid("SSE returned malformed JSON."); }
            data = [];
            yield payload;
          }
          frameSize = 0;
        } else if (line.startsWith("data:")) {
          data.push(line.slice(5).replace(/^ /, ""));
        }
      }
      if (buffer.length + frameSize > 1024 * 1024) throw new SchemaInvalid("SSE frame exceeds the size limit.");
    }
  } catch (err) {
    if (opts.signal?.aborted) return;
    if (err instanceof DarkmoonError) throw err;
    throw new NetworkError("SSE connection failed or timed out; completion is unverified.");
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", abort);
    controller.abort();
    await reader?.cancel().catch(() => undefined);
    reader?.releaseLock();
  }
}
