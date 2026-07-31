const backendUrl = () => {
  const configured = process.env.API_PROXY_URL || 'http://127.0.0.1:8000';
  return `${configured.replace(/\/$/, '')}/api/v1/chat`;
};

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  const headers = new Headers();
  for (const name of ['authorization', 'content-type', 'x-api-key', 'x-provider-endpoint']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const upstream = await fetch(backendUrl(), {
    method: 'POST',
    headers,
    body: request.body,
    signal: request.signal,
    cache: 'no-store',
    // Node's fetch requires half-duplex when forwarding a request stream.
    duplex: 'half',
  } as RequestInit & { duplex: 'half' });

  const responseHeaders = new Headers();
  responseHeaders.set('Content-Type', upstream.headers.get('content-type') || 'text/event-stream');
  responseHeaders.set('Cache-Control', 'no-cache, no-transform');
  responseHeaders.set('Connection', 'keep-alive');
  responseHeaders.set('X-Accel-Buffering', 'no');

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
