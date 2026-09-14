import {PitbluApi} from './client';

describe('PitbluApi', () => {
  beforeEach(() => sessionStorage.clear());

  it('uses a bearer token without putting it in the URL', async () => {
    const api = new PitbluApi('operator');
    api.setCredential('operator-secret');
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({status: 'ok'}), {status: 200}));
    await api.request('/api/v1/system');
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/system', expect.objectContaining({
      headers: expect.any(Headers)
    }));
    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer operator-secret');
    expect(fetchMock.mock.calls[0][0]).not.toContain('operator-secret');
  });

  it('does not attach an application bearer token for followers', async () => {
    sessionStorage.setItem('pitblu-follower-token', 'wrong-token');
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({id: 'cook'}), {status: 200})
    );
    await new PitbluApi('follower', 'capability').request('/api/v1/follow/capability');
    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.has('Authorization')).toBe(false);
  });
});
