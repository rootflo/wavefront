/**
 * Reading a `text/event-stream` response body.
 *
 * EventSource cannot be used for these streams: it only issues GETs and
 * carries no Authorization header, while inference streams are POSTs behind a
 * bearer token. So the body is read as a stream and framed here.
 */

/**
 * Invoke `onEvent` with the parsed JSON payload of every complete SSE frame.
 *
 * Resolves when the server closes the stream. An aborted fetch rejects from
 * `reader.read()`, so callers that abort should expect the AbortError.
 */
export async function consumeSSE(response: Response, onEvent: (data: unknown) => void): Promise<void> {
  const reader = response.body?.pipeThrough(new TextDecoderStream()).getReader();
  if (!reader) {
    throw new Error('Streaming is not supported in this browser');
  }

  // Frames arrive split across chunks at arbitrary points, so anything after
  // the last blank line is held back until the rest of it shows up.
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += value;
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        const payload = parseFrame(frame);
        if (payload !== null) onEvent(payload);
      }
    }

    // A server that ends without a trailing blank line still owes us its last
    // frame.
    const trailing = parseFrame(buffer);
    if (trailing !== null) onEvent(trailing);
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): unknown | null {
  if (!frame.trim()) return null;

  const data = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trimStart())
    .join('\n');

  if (!data.trim()) return null;

  try {
    return JSON.parse(data);
  } catch {
    // A malformed frame is not worth tearing the stream down for - the rest
    // of the run is still coming.
    console.error('Discarding unparseable SSE frame:', data);
    return null;
  }
}
