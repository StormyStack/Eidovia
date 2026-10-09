import { normaliseApiUrl } from '../config';

describe('normaliseApiUrl (EXPO_PUBLIC_API_URL)', () => {
  it.each([
    ['http://192.168.0.244:8000', 'http://192.168.0.244:8000'],
    ['  http://10.0.2.2:8000/ ', 'http://10.0.2.2:8000'],
    ['https://api.example.com//', 'https://api.example.com'],
  ])('accepts %s', (raw, url) => {
    expect(normaliseApiUrl(raw)).toEqual({ url, error: null });
  });

  it.each([undefined, '', '   '])('reports a missing value (%s)', (raw) => {
    const result = normaliseApiUrl(raw);
    expect(result.url).toBe('');
    expect(result.error).toMatch(/not set/);
  });

  it.each(['192.168.0.244:8000', 'ftp://x', 'http://'])('rejects a malformed value (%s)', (raw) => {
    const result = normaliseApiUrl(raw);
    expect(result.url).toBe('');
    expect(result.error).toMatch(/must start with http/);
  });
});
