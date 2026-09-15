import {useEffect, useState} from 'react';
import {PitbluApi} from '../api/client';
import type {CoreDevice, CoreOperation, DiscoveredThermometer, SystemState, ThermometerScan, ThermometerState} from '../types/api';

const connectedStates = new Set(['connected', 'polling']);
const reconnectingStates = new Set(['connecting', 'reconnecting', 'backoff', 'discovering']);
const friendlyState = (device: CoreDevice) => connectedStates.has(device.observedState ?? '') ? 'Connected' : reconnectingStates.has(device.observedState ?? '') ? 'Reconnecting' : 'Unavailable';
const recent = (value?: string | null) => value ? new Date(value).toLocaleString() : 'Not yet available';

export function ThermometerScreen({initialCore, api, onRefresh}: {initialCore: SystemState['core']; api: PitbluApi; onRefresh: () => Promise<void>}) {
  const [state, setState] = useState<ThermometerState>({core: initialCore, devices: initialCore.devices});
  const [scan, setScan] = useState<ThermometerScan | null>(null);
  const [busyDevice, setBusyDevice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => setState(await api.request<ThermometerState>('/api/v1/thermometer'));
  useEffect(() => { void refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const waitForOperation = async (operationId: string) => {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const operation = await api.request<CoreOperation>(`/api/v1/thermometer/operations/${encodeURIComponent(operationId)}`);
      if (operation.status === 'succeeded') { await refresh(); await onRefresh(); return; }
      if (operation.status === 'failed') throw new Error('The thermometer could not connect. Please try again.');
      await new Promise(resolve => window.setTimeout(resolve, 500));
    }
    throw new Error('The thermometer is still trying to connect. Check again shortly.');
  };

  const reconnect = async (device: CoreDevice) => {
    setError(null); setBusyDevice(device.deviceId);
    try {
      const operation = await api.request<CoreOperation>(`/api/v1/thermometer/devices/${encodeURIComponent(device.deviceId)}/reconnect`, {method: 'POST'});
      await waitForOperation(operation.operationId);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Reconnect failed.'); }
    finally { setBusyDevice(null); }
  };

  const find = async () => {
    setError(null); setScan({operationId: '', status: 'running'});
    try {
      const started = await api.request<ThermometerScan>('/api/v1/thermometer/scans', {method: 'POST'});
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const result = await api.request<ThermometerScan>(`/api/v1/thermometer/scans/${encodeURIComponent(started.operationId)}`);
        setScan(result);
        if (result.status === 'succeeded') return;
        if (result.status === 'failed') throw new Error('No thermometers could be found. Please try again.');
        await new Promise(resolve => window.setTimeout(resolve, 500));
      }
      throw new Error('The search is taking longer than expected. Please try again.');
    } catch (reason) { setScan(null); setError(reason instanceof Error ? reason.message : 'Search failed.'); }
  };

  const add = async (device: DiscoveredThermometer) => {
    setError(null); setBusyDevice(device.discoveryId);
    try {
      const result = await api.request<{operation?: CoreOperation}>('/api/v1/thermometer/devices', {method: 'POST', body: JSON.stringify({discoveryId: device.discoveryId, friendlyName: device.name})});
      if (result.operation) await waitForOperation(result.operation.operationId);
      else { await refresh(); await onRefresh(); }
      setScan(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The thermometer could not be added.'); }
    finally { setBusyDevice(null); }
  };

  const coreLabel = state.core.available ? 'Connected' : state.core.state === 'reconnecting' ? 'Reconnecting' : 'Unavailable';
  return <section className="thermometer-screen">
    <div className="screen-title"><span>Device management</span><h1>Thermometer</h1><p>Find, connect and inspect the thermometers available to Pitblu.</p></div>
    <section className="core-status"><div><span className={`status-dot ${state.core.available ? 'live' : ''}`}/><span><small>pitblu-core</small><strong>{coreLabel}</strong></span></div><dl><div><dt>Last contact</dt><dd>{recent(state.core.lastSuccessfulContact)}</dd></div><div><dt>Live updates</dt><dd>{state.core.liveEvents ? 'Receiving events' : state.core.available ? 'Waiting for next event' : 'Unavailable'}</dd></div></dl></section>
    {!state.core.available && <p className="device-notice">Pitblu cannot currently reach pitblu-core. Your Cook history remains available, but thermometer actions are paused until the service reconnects.</p>}
    {error && <p className="device-error" role="alert">{error}</p>}
    <div className="thermometer-devices">{state.devices.map(device => {
      const label = friendlyState(device); const reconnecting = busyDevice === device.deviceId || label === 'Reconnecting';
      const attached = device.probes.filter(probe => probe.present !== false && probe.available).length;
      return <article className="thermometer-device" key={device.deviceId}><header><span className="device-symbol">♨</span><div><small>Weber iGrill</small><h2>{device.friendlyName ?? device.name ?? 'iGrill'}</h2><p><i className={`status-dot ${label === 'Connected' ? 'live' : ''}`}/>{reconnecting ? 'Reconnecting' : label}</p></div>{device.battery?.available && <span className="device-battery">▭ {device.battery.percentage}%<small>Battery</small></span>}</header><dl className="device-facts"><div><dt>Device ID</dt><dd>{device.deviceId}</dd></div>{device.model && <div><dt>Model</dt><dd>{device.model}</dd></div>}<div><dt>Automatic reconnect</dt><dd>{device.automaticReconnection === false ? 'Off' : 'On'}</dd></div></dl>{label !== 'Connected' && <button className="primary-action" disabled={!state.core.available || reconnecting} onClick={() => void reconnect(device)}>{reconnecting ? 'Reconnecting…' : 'Reconnect'}</button>}<section className="physical-probes"><div className="section-heading"><h3>Probes</h3><span>{attached} attached</span></div>{device.probes.map(probe => {const live = probe.available && probe.present !== false && probe.fresh !== false && probe.temperatureC !== null; return <div className="physical-probe" key={probe.probe}><span className={`probe-number probe-${probe.probe}`}>{probe.probe}</span><strong>Probe {probe.probe}</strong><span>{live ? `${probe.temperatureC}°C` : probe.fresh === false ? 'Stale' : 'Unavailable'}<small>{live ? 'Live' : probe.present === false ? 'Not attached' : 'No current reading'}</small></span></div>;})}</section></article>;
    })}</div>
    {!state.devices.length && state.core.available && <section className="no-thermometer"><span className="device-symbol">♨</span><h2>No thermometer connected</h2><p>Search for a nearby supported Weber iGrill.</p></section>}
    <section className="find-thermometer"><button className="primary-action" disabled={!state.core.available || scan?.status === 'running'} onClick={() => void find()}>{scan?.status === 'running' ? 'Searching for thermometers…' : 'Find iGrill'}</button>{scan?.status === 'succeeded' && <div className="found-devices"><h2>Found devices</h2>{scan.devices?.length ? scan.devices.map(device => {const known = state.devices.some(item => item.name === device.name || item.friendlyName === device.name); return <article key={device.discoveryId}><span><strong>{device.name}</strong><small>{device.model ?? 'Compatible iGrill'} · {known ? 'Already added' : 'Available'}</small></span><button disabled={Boolean(busyDevice) || known} onClick={() => void add(device)}>{known ? 'Already added' : busyDevice === device.discoveryId ? 'Connecting…' : 'Add & connect'}</button></article>;}) : <p>No compatible iGrill was found. Make sure it is awake and nearby, then try again.</p>}</div>}</section>
    <details className="device-diagnostics"><summary>Details</summary><p>Last successful contact: {recent(state.core.lastSuccessfulContact)}</p><p>Last live event: {recent(state.core.lastEventAt)}</p></details>
  </section>;
}
