import {FormEvent, useCallback, useEffect, useMemo, useState} from 'react';
import {PitbluApi, type ClientRole} from './api/client';
import {AlertList} from './components/AlertList';
import {CookHeader} from './components/CookHeader';
import {MeasurementCard} from './components/MeasurementCard';
import {TemperatureChart} from './components/TemperatureChart';
import type {Alert, Cook, CookEvent, Measurement, NamedResource, Share, ShareSummary, SystemState, TemperatureReading} from './types/api';

type Tab = 'overview' | 'chart' | 'timeline' | 'setup';
const json = (value: unknown) => JSON.stringify(value);
const time = (value: string | null) => value ? new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '—';

function route(): {role: ClientRole; followerToken?: string} {
  const match = location.pathname.match(/^\/follow\/([^/]+)/);
  if (match) return {role: 'follower', followerToken: decodeURIComponent(match[1])};
  return {role: location.pathname === '/display' ? 'display' : 'operator'};
}

export default function App() {
  const identity = useMemo(route, []);
  const api = useMemo(() => new PitbluApi(identity.role, identity.followerToken), [identity]);
  const [credentialReady, setCredentialReady] = useState(api.hasCredential());
  const [system, setSystem] = useState<SystemState | null>(null);
  const [cook, setCook] = useState<Cook | null>(null);
  const [history, setHistory] = useState<Cook[]>([]);
  const [tab, setTab] = useState<Tab>('overview');
  const [readings, setReadings] = useState<TemperatureReading[]>([]);
  const [events, setEvents] = useState<CookEvent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(new Date());

  const load = useCallback(async () => {
    try {
      setError(null);
      let nextCook: Cook | null = null;
      if (identity.role === 'follower') {
        nextCook = await api.request<Cook>(`/api/v1/follow/${encodeURIComponent(identity.followerToken ?? '')}`);
      } else {
        const nextSystem = await api.request<SystemState>('/api/v1/system');
        setSystem(nextSystem);
        const requested = new URLSearchParams(location.search).get('cook');
        const id = requested ?? nextSystem.activeCook?.id
          ?? (identity.role === 'display' && nextSystem.latestCook?.state === 'closed' ? nextSystem.latestCook.id : undefined);
        if (id) nextCook = await api.request<Cook>(`/api/v1/cooks/${encodeURIComponent(id)}`);
        else if (identity.role === 'operator') setHistory(await api.request<Cook[]>('/api/v1/cooks'));
      }
      setCook(nextCook);
      if (nextCook) {
        const prefix = identity.role === 'follower'
          ? `/api/v1/follow/${encodeURIComponent(identity.followerToken ?? '')}`
          : `/api/v1/cooks/${nextCook.id}`;
        const [nextReadings, nextEvents] = await Promise.all([
          api.request<TemperatureReading[]>(`${prefix}/telemetry?maxPoints=2000`),
          api.request<CookEvent[]>(`${prefix}/events`)
        ]);
        setReadings(nextReadings); setEvents(nextEvents);
        if (identity.role !== 'follower') setAlerts(await api.request<Alert[]>(`/api/v1/alerts?cookId=${nextCook.id}`));
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Pitblu is unavailable.'); }
  }, [api, identity]);

  useEffect(() => { if (credentialReady) void load(); }, [credentialReady, load]);
  useEffect(() => {
    if (!credentialReady) return;
    const controller = new AbortController();
    api.stream(() => void load(), controller.signal);
    return () => controller.abort();
  }, [api, credentialReady, load]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const mutate = async <T,>(path: string, body?: unknown, method = 'POST'): Promise<T> => {
    const headers = path.endsWith('/events') && method === 'POST'
      ? {'Idempotency-Key': crypto.randomUUID()} : undefined;
    const result = await api.request<T>(path, {method, headers, body: body === undefined ? undefined : json(body)});
    await load(); return result;
  };

  if (!credentialReady) return <Shell now={now}><Credential role={identity.role} onSubmit={token => {api.setCredential(token); setCredentialReady(true);}}/></Shell>;
  if (error && identity.role === 'follower') return <Shell now={now}><section className="empty"><h1>Cook complete</h1><p>This live Cook is no longer available. It may have finished, or its follower link may have been replaced.</p></section></Shell>;
  if (error) return <Shell now={now}><section className="empty"><h1>{error}</h1><p>Check the token and that Pitblu is available.</p><button onClick={() => {api.clearCredential(); setCredentialReady(false);}}>Try another token</button></section></Shell>;
  if (!cook && identity.role === 'follower') return <Shell now={now}><Loading /></Shell>;
  if (!system && !cook && identity.role !== 'follower') return <Shell now={now}><Loading /></Shell>;
  if (!cook) {
    if (identity.role === 'display') return <Shell now={now}><section className="empty"><span className="pulse"/><h1>Ready for the next cook</h1><p>Pitblu is standing by.</p></section></Shell>;
    return <Shell now={now}><StartCook history={history} system={system!} onCreate={async name => {
      const created = await mutate<Cook>('/api/v1/cooks', {name});
      window.history.replaceState(null, '', `/?cook=${created.id}`);
      setCook(created); setTab('setup');
    }}/></Shell>;
  }

  const readOnly = identity.role !== 'operator' || cook.state === 'closed';
  return <Shell now={now}>
    <CookHeader cook={cook} now={now}/>
    <AlertList alerts={identity.role === 'follower' ? cook.activeAlerts : alerts} canAcknowledge={!readOnly}
      onAcknowledge={id => void mutate(`/api/v1/alerts/${id}/acknowledge`)}/>
    {identity.role === 'operator' && <nav className="tabs" aria-label="Cook views">
      {(['overview', 'chart', 'timeline', 'setup'] as Tab[]).map(value =>
        <button className={tab === value ? 'selected' : ''} onClick={() => setTab(value)} key={value}>{value}</button>)}
    </nav>}
    {identity.role !== 'operator' ? <ReadOnlyCook cook={cook} readings={readings} events={events}
      display={identity.role === 'display'} api={api}/> :
      tab === 'setup' ? <Setup cook={cook} system={system!} disabled={readOnly} api={api} mutate={mutate}/> :
      tab === 'chart' ? <section className="card"><h2>Temperature history</h2><TemperatureChart readings={readings} cook={cook} events={events}/><p className="muted">Lines are measurements, dashed lines are food targets, and vertical marks are events. Unavailable samples form honest gaps.</p></section> :
      tab === 'timeline' ? <Timeline events={events} alerts={alerts} readings={readings}/> :
      <><Overview cook={cook}/>{!readOnly && <Actions cook={cook} mutate={mutate}/>}</>}
  </Shell>;
}

function Shell({now, children}: {now: Date; children: React.ReactNode}) {
  const publicView = route().role !== 'operator';
  return <div className="app-shell"><header><a href="/" className="brand">Pitblu</a><time>{now.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</time></header><main>{children}</main><footer>Pitblu · Open source{publicView && <> · <a href="https://github.com/moodywaters/pitblu" target="_blank" rel="noreferrer">View Pitblu on GitHub</a></>}</footer></div>;
}

function Loading() { return <section className="empty"><span className="pulse"/><h1>Connecting to Pitblu…</h1></section>; }

function Credential({role, onSubmit}: {role: ClientRole; onSubmit: (token: string) => void}) {
  return <section className="credential"><div className="eyebrow">Private local access</div><h1>Welcome to Pitblu</h1><p>Enter the {role} token configured for this screen. It stays in this browser tab.</p><form onSubmit={event => {event.preventDefault(); const token = String(new FormData(event.currentTarget).get('token')).trim(); if (token) onSubmit(token);}}><label>{role === 'display' ? 'Display token' : 'Operator token'}<input name="token" type="password" autoComplete="current-password" required autoFocus/></label><button>Continue</button></form></section>;
}

function HardwareReadiness({system}: {system: SystemState}) {
  const probeCount = system.core.devices.reduce((total, device) => total + device.probes.filter(probe => probe.available && probe.present !== false && probe.fresh !== false).length, 0);
  return <section className={`readiness ${system.core.available ? 'ready' : 'offline'}`}>
    <strong>{system.core.available ? 'Thermometer service connected' : 'Thermometer service unavailable'}</strong>
    <span>{system.core.available ? `${system.core.devices.length} device${system.core.devices.length === 1 ? '' : 's'} · ${probeCount} ready probe${probeCount === 1 ? '' : 's'}` : 'You can prepare a Cook now; live readings will resume when the service reconnects.'}</span>
  </section>;
}

function StartCook({history: cooks, system, onCreate}: {history: Cook[]; system: SystemState; onCreate: (name: string) => Promise<void>}) {
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); await onCreate(String(form.get('name'))); };
  return <><HardwareReadiness system={system}/><section className="start"><div className="eyebrow">Ready</div><h1>Start a cook</h1><form onSubmit={submit}><input name="name" required maxLength={120} placeholder="Saturday Brisket"/><button>Create Cook</button></form></section><section><h2>Cook history</h2><div className="grid">{cooks.filter(cook => cook.state === 'closed').map(cook => <a className="card history" href={`/?cook=${cook.id}`} key={cook.id}><h3>{cook.name}</h3><p>Served {time(cook.servedAt)}</p></a>)}</div></section></>;
}

function Overview({cook}: {cook: Cook}) {
  const groups = new Map<string, typeof cook.measurements>();
  cook.measurements.forEach(measurement => {
    const name = cook.cookers.find(cooker => cooker.id === measurement.cookerId)?.name ?? 'Other';
    groups.set(name, [...(groups.get(name) ?? []), measurement]);
  });
  if (!groups.size) return <section className="card"><h2>No measurements yet</h2><p>Add semantic measurements and assign probes in Setup.</p></section>;
  return <>{[...groups].map(([name, measurements]) => <section className="group" key={name}><h2>{name}</h2><div className="grid">{measurements.map(item => <MeasurementCard measurement={item} key={item.id}/>)}</div></section>)}</>;
}

function Actions({cook, mutate}: {cook: Cook; mutate: <T>(path: string, body?: unknown, method?: string) => Promise<T>}) {
  const eventTypes = ['added_fuel', 'adjusted_vents', 'spritzed', 'wrapped', 'checked_meat', 'moved_to_oven'];
  const transitions: Partial<Record<typeof cook.state, [string, string]>> = {active: ['finish-cooking', 'Finish cooking'], cooking_finished: ['start-rest', 'Start rest'], resting: ['serve', 'Mark served'], served: ['close', 'Close cook']};
  const transition = transitions[cook.state];
  return <section className="card"><h2>Add Event</h2><div className="chips">{eventTypes.map(type => <button key={type} onClick={() => void mutate(`/api/v1/cooks/${cook.id}/events`, {type}, 'POST')}>{type.replaceAll('_', ' ')}</button>)}</div><NoteComposer onAdd={note => mutate(`/api/v1/cooks/${cook.id}/events`, {type: 'note', note})}/>{transition && <button className="danger" onClick={() => void mutate(`/api/v1/cooks/${cook.id}/${transition[0]}`)}>{transition[1]}</button>}</section>;
}

function NoteComposer({onAdd}: {onAdd: (note: string) => Promise<unknown>}) {
  const [note, setNote] = useState('');
  return <form className="note-form" onSubmit={async event => {event.preventDefault(); if (!note.trim()) return; await onAdd(note.trim()); setNote('');}}><label>Cook note<input value={note} maxLength={1000} onChange={event => setNote(event.target.value)} placeholder="What happened?"/></label><button>Add note</button></form>;
}

function Setup({cook, system, disabled, api, mutate}: {cook: Cook; system: SystemState; disabled: boolean; api: PitbluApi; mutate: <T>(path: string, body?: unknown, method?: string) => Promise<T>}) {
  const submitNamed = (path: string) => async (event: FormEvent<HTMLFormElement>) => {event.preventDefault(); const form = new FormData(event.currentTarget); await mutate(path, {name: form.get('name')}); event.currentTarget.reset();};
  const sources = system.core.devices.flatMap(device => device.probes.map(probe => ({...probe, deviceId: device.deviceId})));
  return <div className="setup-grid"><div className="wide"><HardwareReadiness system={system}/></div>
    <section className="card"><h2>Cook details</h2><form onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); await mutate(`/api/v1/cooks/${cook.id}`, {name: form.get('name'), anticipatedServeAt: form.get('serve') ? new Date(String(form.get('serve'))).toISOString() : null}, 'PATCH');}}><label>Name<input name="name" defaultValue={cook.name} required disabled={disabled}/></label><label>Serve target<input name="serve" type="datetime-local" defaultValue={cook.anticipatedServeAt ? new Date(new Date(cook.anticipatedServeAt).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''} disabled={disabled}/></label><button disabled={disabled}>Save details</button></form>{cook.state === 'draft' && <button onClick={() => void mutate(`/api/v1/cooks/${cook.id}/start`)}>Start Cook</button>}</section>
    <section className="card"><h2>Cookers and food</h2><EditableNames title="Cooker" items={cook.cookers} disabled={disabled} patchPath="cookers" mutate={mutate}/><form onSubmit={submitNamed(`/api/v1/cooks/${cook.id}/cookers`)}><label>New cooker<input name="name" placeholder="WSM 57" required disabled={disabled}/></label><button disabled={disabled}>Add cooker</button></form><EditableNames title="Food" items={cook.foodItems} disabled={disabled} patchPath="food-items" mutate={mutate}/><form onSubmit={submitNamed(`/api/v1/cooks/${cook.id}/food-items`)}><label>New food<input name="name" placeholder="Brisket" required disabled={disabled}/></label><button disabled={disabled}>Add food</button></form></section>
    <section className="card"><h2>Add measurement</h2><form onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); const number = (key: string) => form.get(key) === '' ? null : Number(form.get(key)); await mutate(`/api/v1/cooks/${cook.id}/measurements`, {label: form.get('label'), kind: form.get('kind'), foodItemId: form.get('food') || null, cookerId: form.get('cooker') || null, targetTemperatureC: number('target'), approachingMarginC: number('margin'), rangeMinC: number('min'), rangeMaxC: number('max')}); event.currentTarget.reset();}}><label>Label<input name="label" placeholder="Brisket Flat" required disabled={disabled}/></label><label>Type<select name="kind" disabled={disabled}><option value="food">Food</option><option value="cooker">Cooker temperature</option><option value="other">Other</option></select></label><label>Food<select name="food" disabled={disabled}><option value="">None</option>{cook.foodItems.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Cooker<select name="cooker" disabled={disabled}><option value="">None</option>{cook.cookers.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Food target °C<input name="target" type="number" step=".1" disabled={disabled}/></label><label>Approaching margin °C<input name="margin" type="number" defaultValue="3" min="0" step=".1" disabled={disabled}/></label><label>Cooker minimum °C<input name="min" type="number" step=".1" disabled={disabled}/></label><label>Cooker maximum °C<input name="max" type="number" step=".1" disabled={disabled}/></label><button disabled={disabled}>Add measurement</button></form></section>
    <section className="card wide"><h2>Measurements</h2>{cook.measurements.map(measurement => <MeasurementEditor key={measurement.id} measurement={measurement} disabled={disabled} mutate={mutate}/>)}</section>
    <section className="card wide"><h2>Probe assignments</h2>{sources.length ? sources.map(source => {const current = cook.assignments?.find(item => item.coreDeviceId === source.deviceId && item.probeChannel === source.probe && !item.endedAt); const ready = source.available && source.present !== false && source.fresh !== false; return <form className="assignment" key={`${source.deviceId}:${source.probe}`} onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); const measurementId = form.get('measurement'); if (measurementId) await mutate(`/api/v1/cooks/${cook.id}/assignments`, {measurementId, coreDeviceId: source.deviceId, probeChannel: source.probe}); else if (current) await mutate(`/api/v1/assignments/${current.id}`, undefined, 'DELETE');}}><span><strong>{source.deviceId} · Probe {source.probe}</strong><small>{ready ? `${source.temperatureC}°C` : 'Unavailable'}</small></span><select name="measurement" defaultValue={current?.measurementId ?? ''} disabled={disabled || (!ready && !current)}><option value="">Not used</option>{cook.measurements.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}</select><button disabled={disabled || (!ready && !current)}>Save</button></form>;}) : <p>No thermometer sources are currently available. You can start without probes.</p>}</section>
    <ShareManager cook={cook} disabled={disabled} api={api}/>
  </div>;
}

function EditableNames({title, items, disabled, patchPath, mutate}: {title: string; items: NamedResource[]; disabled: boolean; patchPath: 'cookers' | 'food-items'; mutate: <T>(path: string, body?: unknown, method?: string) => Promise<T>}) {
  return <div className="editable-list">{items.map(item => <form key={item.id} onSubmit={async event => {event.preventDefault(); await mutate(`/api/v1/${patchPath}/${item.id}`, {name: new FormData(event.currentTarget).get('name')}, 'PATCH');}}><label>{title}<input name="name" defaultValue={item.name} required disabled={disabled}/></label><button className="quiet" disabled={disabled}>Rename</button></form>)}</div>;
}

function MeasurementEditor({measurement, disabled, mutate}: {measurement: Measurement; disabled: boolean; mutate: <T>(path: string, body?: unknown, method?: string) => Promise<T>}) {
  return <form className="measurement-editor" onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); const number = (key: string) => form.get(key) === '' ? null : Number(form.get(key)); await mutate(`/api/v1/measurements/${measurement.id}`, {label: form.get('label'), targetTemperatureC: number('target'), approachingMarginC: number('margin'), rangeMinC: number('min'), rangeMaxC: number('max'), rangePersistenceSeconds: number('persistence')}, 'PATCH');}}>
    <label>Label<input name="label" defaultValue={measurement.label} required disabled={disabled}/></label>
    <label>Target °C<input name="target" type="number" step=".1" defaultValue={measurement.targetTemperatureC ?? ''} disabled={disabled}/></label>
    <label>Margin °C<input name="margin" type="number" min="0" step=".1" defaultValue={measurement.approachingMarginC} disabled={disabled}/></label>
    <label>Minimum °C<input name="min" type="number" step=".1" defaultValue={measurement.rangeMinC ?? ''} disabled={disabled}/></label>
    <label>Maximum °C<input name="max" type="number" step=".1" defaultValue={measurement.rangeMaxC ?? ''} disabled={disabled}/></label>
    <label>Range delay (seconds)<input name="persistence" type="number" min="0" defaultValue={measurement.rangePersistenceSeconds} disabled={disabled}/></label>
    <button disabled={disabled}>Update</button>
  </form>;
}

function ShareManager({cook, disabled, api}: {cook: Cook; disabled: boolean; api: PitbluApi}) {
  const [shares, setShares] = useState<ShareSummary[]>([]);
  const [issued, setIssued] = useState<Share | null>(null);
  const refresh = useCallback(async () => setShares(await api.request<ShareSummary[]>(`/api/v1/cooks/${cook.id}/shares`)), [api, cook.id]);
  useEffect(() => {void refresh();}, [refresh]);
  const live = cook.state !== 'draft' && cook.state !== 'closed';
  return <section className="card wide"><h2>Follower access</h2><p className="muted">Follower links are read-only and work on the local network. Newly issued links are shown once.</p>
    <div className="chips"><button disabled={disabled || !live} onClick={async () => {const result = await api.request<Share>(`/api/v1/cooks/${cook.id}/shares`, {method: 'POST', body: '{}', headers: {'Content-Type': 'application/json'}}); setIssued(result); await refresh();}}>Create follower link</button><button className="quiet" disabled={disabled || !live} onClick={async () => {const result = await api.request<Share>(`/api/v1/cooks/${cook.id}/default-share/regenerate`, {method: 'POST'}); setIssued(result); await refresh();}}>Replace display QR link</button></div>
    {issued && <div className="issued"><strong>Save or share this local link now</strong><code>{location.origin}{issued.followerPath}</code></div>}
    {shares.map(share => <div className="share-row" key={share.id}><span>{share.isDefault ? 'Display QR' : 'Follower link'}<small>{share.active ? `Active · created ${new Date(share.createdAt).toLocaleString()}` : 'Inactive'}</small></span>{share.active && <button className="quiet" disabled={disabled} onClick={async () => {await api.request(`/api/v1/shares/${share.id}`, {method: 'DELETE'}); setIssued(null); await refresh();}}>Revoke</button>}</div>)}
  </section>;
}

function Timeline({events, alerts, readings}: {events: CookEvent[]; alerts: Alert[]; readings: TemperatureReading[]}) {
  const items = [...events.map(item => ({at: item.occurredAt, label: item.type.replaceAll('_', ' '), detail: item.note})), ...alerts.map(item => ({at: item.triggeredAt, label: item.message, detail: item.action}))].sort((a, b) => +new Date(b.at) - +new Date(a.at));
  return <><section className="card"><h2>Timeline</h2>{items.length ? items.map((item, index) => <div className="timeline" key={`${item.at}:${index}`}><time>{time(item.at)}</time><div><strong>{item.label}</strong>{item.detail && <p>{item.detail}</p>}</div></div>) : <p>No meaningful events yet.</p>}</section><section className="card"><h2>Recorded telemetry</h2><p>{readings.length} readings preserved.</p></section></>;
}

function ReadOnlyCook({cook, readings, events, display, api}: {cook: Cook; readings: TemperatureReading[]; events: CookEvent[]; display: boolean; api: PitbluApi}) {
  const [share, setShare] = useState<Share | null>(null);
  useEffect(() => {
    if (!display || cook.state === 'closed') return;
    void api.request<Share>(`/api/v1/cooks/${cook.id}/default-share`).then(setShare);
  }, [api, cook.id, cook.state, display]);
  return <><Overview cook={cook}/><section className="card"><h2>Cook history</h2><TemperatureChart readings={readings} cook={cook} events={events}/></section><section className="card"><h2>Recent events</h2>{events.slice(-5).reverse().map(item => <div className="timeline" key={item.id}><time>{time(item.occurredAt)}</time><strong>{item.type.replaceAll('_', ' ')}</strong></div>)}</section>{share && <section className="qr"><img alt="QR code to follow this cook" src={`/api/v1/shares/qr/${encodeURIComponent(share.token)}`}/><div><strong>Scan to follow the cook</strong><p>Available on this local network</p></div></section>}</>;
}
