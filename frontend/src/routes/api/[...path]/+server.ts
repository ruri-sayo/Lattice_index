import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const hopByHopHeaders = new Set([
  'connection',
  'content-length',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade'
]);

async function proxy({ request, params, url }: Parameters<RequestHandler>[0]): Promise<Response> {
  const backendApiBase = (env.BACKEND_API_BASE || 'http://localhost:8000').replace(/\/$/, '');
  const target = new URL(`/api/${params.path ?? ''}${url.search}`, backendApiBase);
  const headers = new Headers(request.headers);

  for (const header of hopByHopHeaders) {
    headers.delete(header);
  }

  const init: RequestInit = {
    method: request.method,
    headers
  };

  if (!['GET', 'HEAD'].includes(request.method)) {
    init.body = await request.arrayBuffer();
  }

  const response = await fetch(target, init);
  const responseHeaders = new Headers(response.headers);

  for (const header of hopByHopHeaders) {
    responseHeaders.delete(header);
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
