import {cleanup, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {PitbluApi} from '../api/client';
import type {SystemState, ThermometerState} from '../types/api';
import {ThermometerScreen} from './ThermometerScreen';

const connected: ThermometerState = {core: {available: true, state: 'connected', liveEvents: true, lastSuccessfulContact: '2026-09-15T08:00:00Z', devices: []}, devices: [{deviceId: 'igrill-a', friendlyName: 'Weber iGrill', model: 'igrill-v202', observedState: 'polling', automaticReconnection: true, battery: {available: true, fresh: true, percentage: 82}, probes: [{probe: 1, temperatureC: 67, available: true, present: true, fresh: true}, {probe: 2, temperatureC: 21, available: true, present: true, fresh: true}, {probe: 3, temperatureC: null, available: true, present: false, fresh: true}]}]};

const apiWith = (implementation: (path: string, options?: RequestInit) => Promise<unknown>) => ({request: vi.fn(implementation)}) as unknown as PitbluApi;

describe('ThermometerScreen', () => {
  afterEach(cleanup);

  it('separates connected core, device and physical probe status', async () => {
    const api = apiWith(async () => connected);
    render(<ThermometerScreen initialCore={connected.core} api={api} onRefresh={vi.fn()}/>);
    expect(await screen.findByText('Receiving events')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Weber iGrill'})).toBeInTheDocument();
    expect(screen.getByText('2 attached')).toBeInTheDocument();
    expect(screen.getByText('67°C')).toBeInTheDocument();
    expect(screen.getByText('Not attached')).toBeInTheDocument();
    expect(screen.getByText(/82/)).toBeInTheDocument();
  });

  it('shows core unavailability separately and disables device actions', async () => {
    const unavailable: SystemState['core'] = {available: false, state: 'reconnecting', devices: connected.devices};
    const api = apiWith(async () => ({core: unavailable, devices: connected.devices.map(device => ({...device, observedState: 'disconnected'}))}));
    render(<ThermometerScreen initialCore={unavailable} api={api} onRefresh={vi.fn()}/>);
    expect(await screen.findByText(/Cook history remains available/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Reconnect'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Find iGrill'})).toBeDisabled();
  });

  it('reconnects a known unavailable iGrill through pitblu-app', async () => {
    const deviceState = {...connected, devices: connected.devices.map(device => ({...device, observedState: 'disconnected'}))};
    const api = apiWith(async (path, options) => {
      if (path.endsWith('/reconnect') && options?.method === 'POST') return {operationId: 'reconnect-1', status: 'running'};
      if (path.endsWith('/operations/reconnect-1')) return {operationId: 'reconnect-1', status: 'succeeded'};
      return deviceState;
    });
    render(<ThermometerScreen initialCore={deviceState.core} api={api} onRefresh={vi.fn()}/>);
    await userEvent.click(await screen.findByRole('button', {name: 'Reconnect'}));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith('/api/v1/thermometer/devices/igrill-a/reconnect', {method: 'POST'}));
    expect([...vi.mocked(api.request).mock.calls].every(([path]) => String(path).startsWith('/api/v1/'))).toBe(true);
  });

  it('shows authoritative reconnecting progress and prevents duplicate reconnects', async () => {
    const deviceState = {...connected, devices: connected.devices.map(device => ({...device, observedState: 'disconnected'}))};
    const api = apiWith(async path => path.endsWith('/reconnect') ? await new Promise(() => undefined) : deviceState);
    render(<ThermometerScreen initialCore={deviceState.core} api={api} onRefresh={vi.fn()}/>);
    await userEvent.click(await screen.findByRole('button', {name: 'Reconnect'}));
    expect(await screen.findByRole('button', {name: 'Reconnecting…'})).toBeDisabled();
  });

  it('searches, renders a discovered iGrill and adds it through pitblu-app', async () => {
    const empty: ThermometerState = {core: {...connected.core, devices: []}, devices: []};
    const api = apiWith(async (path, options) => {
      if (path === '/api/v1/thermometer/scans' && options?.method === 'POST') return {operationId: 'scan-1', status: 'running'};
      if (path.endsWith('/scans/scan-1')) return {operationId: 'scan-1', status: 'succeeded', devices: [{discoveryId: 'found-1', name: 'iGrill_V202-TEST', model: 'igrill-v202'}]};
      if (path === '/api/v1/thermometer/devices' && options?.method === 'POST') return {operation: {operationId: 'connect-1', status: 'running'}};
      if (path.endsWith('/operations/connect-1')) return {operationId: 'connect-1', status: 'succeeded'};
      return empty;
    });
    render(<ThermometerScreen initialCore={empty.core} api={api} onRefresh={vi.fn()}/>);
    expect(await screen.findByRole('heading', {name: 'No thermometer connected'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Find iGrill'}));
    expect(await screen.findByText('iGrill_V202-TEST')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Add & connect'}));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith('/api/v1/thermometer/devices', expect.objectContaining({method: 'POST'})));
  });

  it('shows scanning progress and prevents duplicate searches', async () => {
    const empty: ThermometerState = {core: {...connected.core, devices: []}, devices: []};
    const api = apiWith(async (path, options) => path === '/api/v1/thermometer/scans' && options?.method === 'POST' ? await new Promise(() => undefined) : empty);
    render(<ThermometerScreen initialCore={empty.core} api={api} onRefresh={vi.fn()}/>);
    await userEvent.click(await screen.findByRole('button', {name: 'Find iGrill'}));
    expect(await screen.findByRole('button', {name: 'Searching for thermometers…'})).toBeDisabled();
  });
});
