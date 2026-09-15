import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import {PitbluApi} from './api/client';
import type {Cook, SystemState} from './types/api';

const cook: Cook = {
  id: 'cook-1', name: 'Saturday brisket', state: 'active',
  startedAt: '2026-09-14T08:00:00Z', anticipatedServeAt: null,
  servedAt: null, closedAt: null, cookers: [], foodItems: [],
  measurements: [], assignments: [], activeAlerts: []
};

const system: SystemState = {
  core: {available: true, devices: [{deviceId: 'igrill-a', probes: [
    {probe: 1, temperatureC: 68, available: true, present: true, fresh: true},
    {probe: 2, temperatureC: null, available: true, present: false, fresh: true}
  ]}]},
  activeCook: {id: cook.id, name: cook.name, state: cook.state},
  latestCook: {id: cook.id, name: cook.name, state: cook.state}
};

describe('application surfaces', () => {
  afterEach(cleanup);

  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
    vi.spyOn(PitbluApi.prototype, 'stream').mockImplementation(() => undefined);
  });

  it('lets an operator create a Cook through the API', async () => {
    sessionStorage.setItem('pitblu-operator-token', 'operator-secret');
    let started = false;
    const request = vi.spyOn(PitbluApi.prototype, 'request').mockImplementation(async (path, options) => {
      if (path === '/api/v1/system') return {...system, activeCook: started ? system.activeCook : null, latestCook: null};
      if (path === '/api/v1/cooker-profiles') return [{id: 'wsm', name: 'WSM 57', description: null, createdAt: '2026-09-14T08:00:00Z'}];
      if (path === '/api/v1/cooks' && options?.method === 'POST') return {...cook, state: 'draft', cookers: [{id: 'cooker', name: 'WSM 57'}]};
      if (path === '/api/v1/cooks/cook-1/start') {started = true; return cook;}
      if (path === '/api/v1/cooks/cook-1') return cook;
      if (path.includes('/telemetry') || path.endsWith('/events') || path.startsWith('/api/v1/alerts')) return [];
      if (path === '/api/v1/cooks') return [];
      return [];
    });

    render(<App/>);
    await screen.findByRole('heading', {name: 'Everything’s ready'});
    expect(screen.getByText('Probe 1')).toBeInTheDocument();
    expect(screen.getByText('68')).toBeInTheDocument();
    expect(screen.getByText('Not connected')).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'Manage igrill-a'})).toHaveAttribute('href', '/?view=thermometer');
    await userEvent.click(screen.getByRole('button', {name: /start a cook/i}));
    await screen.findByRole('heading', {name: 'Set up the probes'});
    expect(screen.getByRole('link', {name: 'Pitblu home'})).toBeInTheDocument();
    expect(screen.getByText(/1 ready probe$/)).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText('Defaults to today’s date'), 'Sunday ribs');
    await userEvent.click(screen.getByRole('checkbox', {name: /WSM 57/i}));
    await userEvent.click(screen.getByRole('button', {name: /start cooking/i}));

    await screen.findByText('Saturday brisket');
    expect(request).toHaveBeenCalledWith('/api/v1/cooks', expect.objectContaining({method: 'POST'}));
    expect(request).toHaveBeenCalledWith('/api/v1/cooks/cook-1/start', expect.objectContaining({method: 'POST'}));
    expect(window.location.search).toBe('?cook=cook-1');
  });

  it('keeps the Live Display read-only while showing its backend-managed QR link', async () => {
    sessionStorage.setItem('pitblu-display-token', 'display-secret');
    window.history.replaceState(null, '', '/display');
    const request = vi.spyOn(PitbluApi.prototype, 'request').mockImplementation(async path => {
      if (path === '/api/v1/system') return system;
      if (path === `/api/v1/cooks/${cook.id}`) return cook;
      if (path.includes('/telemetry') || path.endsWith('/events') || path.startsWith('/api/v1/alerts')) return [];
      if (path.endsWith('/default-share')) return {id: 'share', cookId: cook.id, token: 'follower-capability', followerPath: '/follow/follower-capability', isDefault: true};
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<App/>);
    expect(await screen.findByAltText('QR code to follow this cook')).toBeInTheDocument();
    expect(screen.queryByText('Setup')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /create follower/i})).not.toBeInTheDocument();
    await waitFor(() => expect(request).toHaveBeenCalledWith(`/api/v1/cooks/${cook.id}/default-share`));
  });

  it('renders a Cook-scoped follower view without an application credential', async () => {
    window.history.replaceState(null, '', '/follow/follower-capability');
    const request = vi.spyOn(PitbluApi.prototype, 'request').mockImplementation(async path => {
      if (path === '/api/v1/follow/follower-capability') return cook;
      if (path.includes('/telemetry') || path.endsWith('/events')) return [];
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<App/>);
    await screen.findByText('Saturday brisket');
    expect(screen.queryByText('Setup')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /acknowledge/i})).not.toBeInTheDocument();
    expect(request).toHaveBeenCalledWith('/api/v1/follow/follower-capability');
  });

  it('handles an expired follower capability as a finished Cook', async () => {
    window.history.replaceState(null, '', '/follow/expired-capability');
    vi.spyOn(PitbluApi.prototype, 'request').mockRejectedValue(new Error('resource not found'));

    render(<App/>);
    expect(await screen.findByRole('heading', {name: 'Cook complete'})).toBeInTheDocument();
    expect(screen.getByText(/no longer available/i)).toBeInTheDocument();
  });

  it('offers another Cook after a Cook is complete', async () => {
    sessionStorage.setItem('pitblu-operator-token', 'operator-secret');
    window.history.replaceState(null, '', '/?cook=cook-1');
    vi.spyOn(PitbluApi.prototype, 'request').mockImplementation(async path => {
      if (path === '/api/v1/system') return {...system, activeCook: null, latestCook: {...system.latestCook!, state: 'closed'}};
      if (path === '/api/v1/cooker-profiles') return [];
      if (path === '/api/v1/cooks') return [];
      if (path === `/api/v1/cooks/${cook.id}`) return {...cook, state: 'closed'};
      if (path.includes('/telemetry') || path.endsWith('/events') || path.startsWith('/api/v1/alerts')) return [];
      throw new Error(`Unexpected request: ${path}`);
    });

    render(<App/>);
    expect(await screen.findByRole('link', {name: /start another cook/i})).toHaveAttribute('href', '/');
  });
});
