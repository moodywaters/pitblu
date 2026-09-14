import type {ApiErrorEnvelope, ApplicationEvent} from '../types/api';

export type ClientRole = 'operator' | 'display' | 'follower';

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
  }
}

export class PitbluApi {
  private readonly storageKey: string;

  constructor(readonly role: ClientRole, private readonly followerToken?: string) {
    this.storageKey = `pitblu-${role}-token`;
  }

  private token(): string | null {
    return this.role === 'follower' ? null : sessionStorage.getItem(this.storageKey);
  }

  hasCredential(): boolean {
    return this.role === 'follower' || Boolean(this.token());
  }

  setCredential(token: string): void {
    if (this.role !== 'follower') sessionStorage.setItem(this.storageKey, token);
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    const token = this.token();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, {...init, headers});
    if (!response.ok) {
      const body = await response.json().catch(() => null) as ApiErrorEnvelope | null;
      if (response.status === 401) this.clearCredential();
      throw new ApiError(body?.error.message ?? 'Pitblu could not complete that action.', response.status, body?.error.code);
    }
    return (response.status === 204 ? undefined : response.json()) as Promise<T>;
  }

  clearCredential(): void {
    sessionStorage.removeItem(this.storageKey);
  }

  stream(onEvent: (event: ApplicationEvent) => void, signal: AbortSignal): void {
    if (this.role === 'follower') {
      const source = new EventSource(`/api/v1/follow/${encodeURIComponent(this.followerToken ?? '')}/stream`);
      const types = applicationEventTypes;
      types.forEach(type => source.addEventListener(type, event => onEvent(JSON.parse((event as MessageEvent).data) as ApplicationEvent)));
      signal.addEventListener('abort', () => source.close(), {once: true});
      return;
    }
    void this.fetchStream(onEvent, signal);
  }

  private async fetchStream(onEvent: (event: ApplicationEvent) => void, signal: AbortSignal): Promise<void> {
    while (!signal.aborted) {
      try {
        const token = this.token();
        if (!token) return;
        const response = await fetch('/api/v1/events', {
          headers: {Authorization: `Bearer ${token}`}, signal
        });
        if (response.status === 401) { this.clearCredential(); continue; }
        if (!response.ok || !response.body) throw new ApiError('Live updates unavailable', response.status);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!signal.aborted) {
          const {value, done} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {stream: true}).replaceAll('\r\n', '\n');
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';
          frames.forEach(frame => {
            const data = frame.split('\n').find(line => line.startsWith('data:'))?.slice(5).trim();
            if (data) onEvent(JSON.parse(data) as ApplicationEvent);
          });
        }
      } catch (error) {
        if (signal.aborted) return;
      }
      await new Promise(resolve => window.setTimeout(resolve, 2000));
    }
  }
}

export const applicationEventTypes = [
  'cook.started', 'cook.updated', 'cook.cooking_finished', 'cook.rest_started',
  'cook.served', 'cook.closed', 'measurement.updated', 'probe.assignment.changed',
  'cook_event.created', 'alert.triggered', 'alert.acknowledged', 'alert.resolved'
] as const;
