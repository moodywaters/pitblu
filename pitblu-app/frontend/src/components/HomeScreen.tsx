import type {Cook, CoreDevice, SystemState} from '../types/api';

const probeColours = ['red', 'blue', 'green', 'amber'];

function DeviceStatus({device}: {device: CoreDevice}) {
  const connected = device.probes.some(probe => probe.available && probe.present !== false);
  return <article className="device-status" aria-label={`${device.friendlyName ?? device.name ?? device.deviceId} status`}>
    <span className="device-symbol" aria-hidden="true">♨</span>
    <span><strong>{device.friendlyName ?? device.name ?? device.deviceId}</strong><small><i className={connected ? 'status-dot live' : 'status-dot'}/>{connected ? 'Connected' : 'Unavailable'}</small></span>
    {device.battery?.available && <span className="battery" aria-label={`${device.battery.percentage}% battery`}>▭ {device.battery.percentage}%</span>}
  </article>;
}

function ProbeReading({probe, deviceId}: {probe: CoreDevice['probes'][number]; deviceId: string}) {
  const live = probe.available && probe.present !== false && probe.fresh !== false && probe.temperatureC !== null;
  const colour = probeColours[(probe.probe - 1) % probeColours.length];
  return <article className={`home-probe ${live ? '' : 'unavailable'}`} aria-label={`${deviceId}, Probe ${probe.probe}`}>
    <span className={`probe-number ${colour}`}>{probe.probe}</span>
    <span className="probe-label">Probe {probe.probe}</span>
    <strong>{live ? <>{probe.temperatureC}<sup>°C</sup></> : <>— —<sup>°C</sup></>}</strong>
    <small><i className={`status-dot ${live ? 'live' : ''}`}/>{live ? 'Live' : probe.fresh === false ? 'Reading stale' : 'Not connected'}</small>
  </article>;
}

export function HomeScreen({system, history, onStart}: {system: SystemState; history: Cook[]; onStart: () => void}) {
  const devices = system.core.devices;
  const probes = devices.flatMap(device => device.probes.map(probe => ({probe, deviceId: device.deviceId})));
  return <div className="home-screen">
    <section className="home-hero">
      <div className="hero-copy"><p className="script-line">Good food. Better times.</p><h1>Everything’s ready</h1><p>Your thermometer is connected and ready.</p></div>
      <div className="home-readings">
        <h2>Live probe readings</h2>
        <div className="home-probe-grid">{probes.length ? probes.map(({probe, deviceId}) => <ProbeReading key={`${deviceId}:${probe.probe}`} probe={probe} deviceId={deviceId}/>) : <p className="no-probes">No thermometer probes are available.</p>}</div>
      </div>
      <aside className="home-action">
        {devices.map(device => <DeviceStatus key={device.deviceId} device={device}/>)}
        <div><h2>Ready to cook?</h2><p>Start a new cook to track temperatures, events and notes.</p></div>
        <button className="primary-action" onClick={onStart}>🔥 Start a cook</button>
      </aside>
    </section>
    <section className="recent-cooks"><div className="section-heading"><h2>Recent cooks</h2><span>Journal</span></div><div className="journal-grid">
      {history.filter(cook => cook.state === 'closed').slice(0, 4).map(cook => <a className="journal-card" href={`/?cook=${cook.id}`} key={cook.id}><span className="journal-photo"/><strong>{cook.name}</strong><small>{cook.closedAt ? new Date(cook.closedAt).toLocaleDateString() : 'Completed cook'}</small></a>)}
      {!history.some(cook => cook.state === 'closed') && <p className="empty-journal">Completed cooks will appear here in your journal.</p>}
    </div></section>
  </div>;
}
