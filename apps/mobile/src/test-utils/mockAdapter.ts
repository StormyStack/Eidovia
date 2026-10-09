/**
 * Minimal fake HTTP layer for axios: routes requests to a handler and records them.
 * Errors are raised exactly the way axios' real adapters raise them, so the real
 * interceptors and toApiError() are exercised.
 */

import { AxiosError, AxiosHeaders, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';

export interface RecordedRequest {
  method: string;
  url: string;
  authorization: string | null;
  body: unknown;
}

export type MockReply =
  | { status: number; data?: unknown }
  | 'network-error'
  | 'timeout'
  | 'never';

export type MockHandler = (request: RecordedRequest) => MockReply | Promise<MockReply>;

export function installMockAdapter(client: AxiosInstance, handler: MockHandler): RecordedRequest[] {
  const calls: RecordedRequest[] = [];

  client.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const headers = AxiosHeaders.from(config.headers);
    const auth = headers.get('Authorization');
    const request: RecordedRequest = {
      method: (config.method ?? 'get').toUpperCase(),
      url: config.url ?? '',
      authorization: typeof auth === 'string' ? auth : null,
      body: typeof config.data === 'string' ? JSON.parse(config.data) : config.data ?? null,
    };
    calls.push(request);

    const reply = await handler(request);

    if (reply === 'network-error') {
      throw new AxiosError('Network Error', AxiosError.ERR_NETWORK, config, {});
    }
    if (reply === 'timeout') {
      throw new AxiosError(`timeout of ${config.timeout}ms exceeded`, AxiosError.ETIMEDOUT, config, {});
    }
    if (reply === 'never') {
      return new Promise((_resolve, reject) => {
        config.signal?.addEventListener?.('abort', () => reject(new AxiosError('canceled', AxiosError.ERR_CANCELED, config)));
      });
    }

    const response = {
      data: reply.data ?? null,
      status: reply.status,
      statusText: String(reply.status),
      headers: {},
      config,
      request: {},
    };
    if (reply.status >= 200 && reply.status < 300) return response;
    throw new AxiosError(
      `Request failed with status code ${reply.status}`,
      reply.status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
      config,
      {},
      response,
    );
  };

  return calls;
}

/** Contract error body helper. */
export const errorBody = (code: string, message: string, fields?: Record<string, string>) => ({
  detail: { code, message, ...(fields ? { fields } : {}) },
});
