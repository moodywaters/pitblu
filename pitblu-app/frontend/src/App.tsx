import {FormEvent, useCallback, useEffect, useMemo, useState} from 'react';
import {PitbluApi, type ClientRole} from './api/client';
import {HomeScreen} from './components/HomeScreen';
import {LiveCookScreen} from './components/LiveCookScreen';
import type {Alert, Cook, CookEvent, CookerProfile, Measurement, NamedResource, Share, ShareSummary, SystemState, TemperatureReading} from './types/api';

type Tab = 'overview' | 'chart' | 'timeline' | 'setup';
type ProbePlan = {coreDeviceId: string; probeChannel: number; purpose: 'pit' | 'food' | 'other'; cookerProfileId?: string; label?: string; target?: number; minimum?: number; maximum?: number};
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
  const [cookerProfiles, setCookerProfiles] = useState<CookerProfile[]>([]);
  const [tab, setTab] = useState<Tab>('overview');
  const [readings, setReadings] = useState<TemperatureReading[]>([]);
  const [events, setEvents] = useState<CookEvent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(new Date());
  const [showCookSetup, setShowCookSetup] = useState(false);
  const view = new URLSearchParams(location.search).get('view');

  const load = useCallback(async () => {
    try {
      setError(null);
      let nextCook: Cook | null = null;
      if (identity.role === 'follower') {
        nextCook = await api.request<Cook>(`/api/v1/follow/${encodeURIComponent(identity.followerToken ?? '')}`);
      } else {
        const nextSystem = await api.request<SystemState>('/api/v1/system');
        setSystem(nextSystem);
        if (identity.role === 'operator') {
          setCookerProfiles(await api.request<CookerProfile[]>('/api/v1/cooker-profiles'));
          setHistory(await api.request<Cook[]>('/api/v1/cooks'));
        }
        const requested = new URLSearchParams(location.search).get('cook');
        const id = requested ?? nextSystem.activeCook?.id
          ?? (identity.role === 'display' && nextSystem.latestCook?.state === 'closed' ? nextSystem.latestCook.id : undefined);
        if (id) nextCook = await api.request<Cook>(`/api/v1/cooks/${encodeURIComponent(id)}`);
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

  if (!credentialReady) return <Shell now={now} home><Credential role={identity.role} onSubmit={token => {api.setCredential(token); setCredentialReady(true);}}/></Shell>;
  if (error && identity.role === 'follower') return <Shell now={now}><section className="empty"><h1>Cook complete</h1><p>This live Cook is no longer available. It may have finished, or its follower link may have been replaced.</p></section></Shell>;
  if (error) return <Shell now={now}><section className="empty"><h1>{error}</h1><p>Check the token and that Pitblu is available.</p><button onClick={() => {api.clearCredential(); setCredentialReady(false);}}>Try another token</button></section></Shell>;
  if (!cook && identity.role === 'follower') return <Shell now={now}><Loading /></Shell>;
  if (!system && !cook && identity.role !== 'follower') return <Shell now={now}><Loading /></Shell>;
  if (identity.role === 'operator' && view === 'history') return <Shell now={now} home activeNav="history"><Journal cooks={history}/></Shell>;
  if (identity.role === 'operator' && view === 'more') return <Shell now={now} home activeNav="more"><More cookers={cookerProfiles} api={api} onRefresh={load}/></Shell>;
  if (!cook) {
    if (identity.role === 'display') return <Shell now={now}><section className="empty"><span className="pulse"/><h1>Ready for the next cook</h1><p>Pitblu is standing by.</p></section></Shell>;
    if (!showCookSetup && view !== 'start') return <Shell now={now} home activeNav="home"><HomeScreen system={system!} history={history} onStart={() => setShowCookSetup(true)}/></Shell>;
    return <Shell now={now} home activeNav="cook"><StartCook history={history} system={system!} cookers={cookerProfiles} api={api} onRefresh={load} onCreate={async (name, cookerProfileIds, anticipatedServeAt, plans) => {
      const created = await mutate<Cook>('/api/v1/cooks', {name: name || null, cookerProfileIds, anticipatedServeAt});
      for (const plan of plans) {
        let foodItemId: string | null = null;
        if (plan.purpose === 'food') {
          const food = await api.request<NamedResource>(`/api/v1/cooks/${created.id}/food-items`, {method: 'POST', body: json({name: plan.label})});
          foodItemId = food.id;
        }
        const cookerId = created.cookers.find(item => item.profileId === plan.cookerProfileId)?.id ?? null;
        const cookerName = created.cookers.find(item => item.id === cookerId)?.name ?? 'Barbecue';
        const measurement = await api.request<Measurement>(`/api/v1/cooks/${created.id}/measurements`, {method: 'POST', body: json(plan.purpose === 'pit' ? {label: `${cookerName} ambient`, kind: 'cooker', cookerId, rangeMinC: plan.minimum, rangeMaxC: plan.maximum} : plan.purpose === 'food' ? {label: plan.label, kind: 'food', cookerId, foodItemId, targetTemperatureC: plan.target, approachingMarginC: 3} : {label: plan.label, kind: 'other', cookerId})});
        await api.request(`/api/v1/cooks/${created.id}/assignments`, {method: 'POST', body: json({measurementId: measurement.id, coreDeviceId: plan.coreDeviceId, probeChannel: plan.probeChannel})});
      }
      const started = await api.request<Cook>(`/api/v1/cooks/${created.id}/start`, {method: 'POST'});
      window.history.replaceState(null, '', `/?cook=${created.id}`);
      setCook(started); setTab('overview'); await load();
    }}/></Shell>;
  }

  const readOnly = identity.role !== 'operator' || cook.state === 'closed';
  const transitionPath: Partial<Record<typeof cook.state, string>> = {active: 'finish-cooking', cooking_finished: 'start-rest', resting: 'serve', served: 'close'};
  return <Shell now={now} home activeNav="cook">
    {identity.role === 'operator' && cook.state === 'closed' && <a className="new-cook" href="/">🔥 Start another cook</a>}
    {identity.role !== 'operator' ? <ReadOnlyCook cook={cook} readings={readings} events={events}
      display={identity.role === 'display'} api={api}/> :
      tab === 'setup' ? <Setup cook={cook} system={system!} disabled={readOnly} api={api} mutate={mutate}/> :
      <LiveCookScreen cook={cook} readings={readings} events={events} alerts={alerts} readOnly={readOnly} onAcknowledge={id => void mutate(`/api/v1/alerts/${id}/acknowledge`)} onEdit={() => setTab('setup')} onEvent={type => void mutate(`/api/v1/cooks/${cook.id}/events`, {type})} onTransition={() => {const path = transitionPath[cook.state]; if (path) void mutate(`/api/v1/cooks/${cook.id}/${path}`);}}/>}
  </Shell>;
}

function Shell({now, children, home = false, activeNav}: {now: Date; children: React.ReactNode; home?: boolean; activeNav?: 'home' | 'cook' | 'history' | 'more'}) {
  const publicView = route().role !== 'operator';
  const selected = activeNav ?? new URLSearchParams(location.search).get('view') ?? 'home';
  return <div className={`app-shell ${home ? 'home-shell' : ''}`}><header><a href="/" className="brand" aria-label="Pitblu home"><img src="/pitblu-header-logo.png" alt="Pitblu"/></a><nav aria-label="Primary"><a className={selected === 'home' ? 'active' : ''} href="/">⌂ <span>Home</span></a><a className={selected === 'cook' ? 'active' : ''} href="/?view=start">♨ <span>Cook</span></a><a className={selected === 'history' ? 'active' : ''} href="/?view=history">◷ <span>History</span></a><a className={selected === 'more' ? 'active' : ''} href="/?view=more">••• <span>More</span></a></nav><div className="header-status"><i className="status-dot live"/> Pitblu connected</div><time>{now.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</time></header><main>{children}</main><footer>Pitblu · Open source{publicView && <> · <a href="https://github.com/moodywaters/pitblu" target="_blank" rel="noreferrer">View Pitblu on GitHub</a></>}</footer></div>;
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

function StartCook({history: cooks, system, cookers, api, onRefresh, onCreate}: {history: Cook[]; system: SystemState; cookers: CookerProfile[]; api: PitbluApi; onRefresh: () => Promise<void>; onCreate: (name: string, cookerProfileIds: string[], anticipatedServeAt: string | null, plans: ProbePlan[]) => Promise<void>}) {
  const sources = system.core.devices.flatMap(device => device.probes.filter(probe => probe.available && probe.present !== false && probe.fresh !== false).map(probe => ({...probe, deviceId: device.deviceId})));
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const plans = sources.flatMap(source => {
      const key = `${source.deviceId}-${source.probe}`;
      const purpose = form.get(`purpose-${key}`);
      if (purpose !== 'pit' && purpose !== 'food' && purpose !== 'other') return [];
      return [{coreDeviceId: source.deviceId, probeChannel: source.probe, purpose,
        cookerProfileId: String(form.get(`cooker-${key}`) ?? '') || undefined,
        label: String(form.get(`label-${key}`) ?? ''), target: Number(form.get(`target-${key}`)),
        minimum: Number(form.get(`min-${key}`)), maximum: Number(form.get(`max-${key}`))} satisfies ProbePlan];
    });
    const profileIds = [...new Set([...form.getAll('cookers').map(String), ...plans.map(plan => plan.cookerProfileId).filter((id): id is string => Boolean(id))])];
    const serve = form.get('serve');
    await onCreate(String(form.get('name')), profileIds, serve ? new Date(String(serve)).toISOString() : null, plans);
  };
  return <div className="start-cook-screen">
    <section className="welcome"><div><div className="eyebrow">Let’s cook</div><h1>Set up the probes</h1><p>Choose your cookers, tell Pitblu what each connected probe is watching, then light the fire.</p></div></section>
    <HardwareReadiness system={system}/>
    <form className="quick-start" onSubmit={submit}>
      <section className="card cook-basics"><span className="step">Today’s cook</span><div className="form-row"><label>Cook name <small>Optional</small><input name="name" maxLength={120} placeholder="Defaults to today’s date"/></label><label>Eating around <small>Optional</small><input name="serve" type="datetime-local"/></label></div><fieldset className="cooker-choice"><legend>Choose one or more barbecues</legend>{cookers.map(cooker => <label key={cooker.id}><input type="checkbox" name="cookers" value={cooker.id}/><span><strong>{cooker.name}</strong>{cooker.description && <small>{cooker.description}</small>}</span></label>)}</fieldset>{!cookers.length && <p className="nudge">Add your WSM, kettle or other barbecue below first—you only need to do this once.</p>}</section>
      <section><span className="step">Connected probes</span><h2>What is each probe watching?</h2>{sources.length ? <div className="probe-grid">{sources.map(source => <ProbePlanCard key={`${source.deviceId}:${source.probe}`} source={source} cookers={cookers}/>)}</div> : <div className="card"><p>No probes are connected. You can still start and add probes later.</p></div>}</section>
      <button className="fire-button">🔥 Start cooking</button>
    </form>
    <details className="gear-drawer" open={!cookers.length}><summary>Manage my barbecues</summary><CookerLibrary cookers={cookers} api={api} onRefresh={onRefresh}/></details>
    <section className="past-cooks"><h2>Previous cooks</h2><div className="grid">{cooks.filter(cook => cook.state === 'closed').map(cook => <a className="card history" href={`/?cook=${cook.id}`} key={cook.id}><span>🔥</span><h3>{cook.name}</h3><p>Served {time(cook.servedAt)}</p></a>)}</div></section>
  </div>;
}

function ProbePlanCard({source, cookers}: {source: {deviceId: string; probe: number; temperatureC: number | null}; cookers: CookerProfile[]}) {
  const [purpose, setPurpose] = useState('unused');
  const key = `${source.deviceId}-${source.probe}`;
  return <article className={`card probe-plan ${purpose}`}><div className="probe-heading"><span><span className={`probe-number probe-${source.probe}`}>{source.probe}</span><strong>Probe {source.probe}</strong><small>{source.deviceId}</small></span><b>{source.temperatureC}°C</b></div><label>Use this for<select name={`purpose-${key}`} value={purpose} onChange={event => setPurpose(event.target.value)}><option value="unused">Not used today</option><option value="food">Food</option><option value="pit">Barbecue temperature</option><option value="other">Other</option></select></label>{purpose !== 'unused' && <label>On which barbecue?<select name={`cooker-${key}`} required><option value="">Choose barbecue</option>{cookers.map(cooker => <option value={cooker.id} key={cooker.id}>{cooker.name}</option>)}</select></label>}{(purpose === 'food' || purpose === 'other') && <div className="probe-options"><label>{purpose === 'food' ? 'What food?' : 'Measurement name'}<input name={`label-${key}`} required placeholder={purpose === 'food' ? 'Brisket flat' : 'Warming cabinet'}/></label>{purpose === 'food' && <label>Ready at °C<input name={`target-${key}`} type="number" step=".1" required placeholder="93"/></label>}</div>}{purpose === 'pit' && <div className="probe-options"><label>Keep above °C<input name={`min-${key}`} type="number" required defaultValue="105"/></label><label>Keep below °C<input name={`max-${key}`} type="number" required defaultValue="135"/></label></div>}</article>;
}

function CookerLibrary({cookers, api, onRefresh}: {cookers: CookerProfile[]; api: PitbluApi; onRefresh: () => Promise<void>}) {
  return <section className="card cooker-library"><span className="step">Your gear</span><h2>My barbecues</h2><p className="muted">Add each barbecue once. You can reuse it every time you cook.</p>{cookers.map(cooker => <div className="cooker-item" key={cooker.id}><strong>♨ {cooker.name}</strong>{cooker.description && <small>{cooker.description}</small>}</div>)}<form onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); await api.request('/api/v1/cooker-profiles', {method: 'POST', body: json({name: form.get('name'), description: form.get('description') || null})}); event.currentTarget.reset(); await onRefresh();}}><label>Barbecue name<input name="name" required placeholder="WSM 57"/></label><label>A few details <small>Optional</small><input name="description" placeholder="Charcoal · 57 cm"/></label><button className="secondary">Add barbecue</button></form></section>;
}

function Journal({cooks}: {cooks: Cook[]}) {
  const complete = cooks.filter(cook => cook.state === 'closed');
  return <section className="journal-screen"><div className="screen-title"><span>Cook history</span><h1>Your cooking journal</h1><p>Every completed Cook, ready to revisit.</p></div><div className="journal-list">{complete.map(cook => <a href={`/?cook=${cook.id}`} className="journal-entry" key={cook.id}><span className="journal-entry-photo"/><div><h2>{cook.name}</h2><p>{cook.cookers.map(item => item.name).join(' · ') || 'Pitblu Cook'}</p><small>{cook.closedAt ? new Date(cook.closedAt).toLocaleDateString() : 'Completed'}</small></div></a>)}{!complete.length && <div className="empty-state"><h2>Your first Cook will appear here</h2><p>Complete and close a Cook to add it to the journal.</p></div>}</div></section>;
}

function More({cookers, api, onRefresh}: {cookers: CookerProfile[]; api: PitbluApi; onRefresh: () => Promise<void>}) {
  return <section className="settings-screen"><div className="screen-title"><span>Settings</span><h1>App configuration</h1><p>Manage the equipment and preferences used across your Cooks.</p></div><div className="settings-grid"><nav aria-label="Settings sections"><a className="active" href="#barbecues">♨ My barbecues</a><a href="#thermometer">◉ Thermometer</a><a href="#appearance">◐ Appearance</a><a href="#about">ⓘ About Pitblu</a></nav><div id="barbecues"><CookerLibrary cookers={cookers} api={api} onRefresh={onRefresh}/></div></div></section>;
}

function Setup({cook, system, disabled, api, mutate}: {cook: Cook; system: SystemState; disabled: boolean; api: PitbluApi; mutate: <T>(path: string, body?: unknown, method?: string) => Promise<T>}) {
  const submitNamed = (path: string) => async (event: FormEvent<HTMLFormElement>) => {event.preventDefault(); const form = new FormData(event.currentTarget); await mutate(path, {name: form.get('name')}); event.currentTarget.reset();};
  const sources = system.core.devices.flatMap(device => device.probes.map(probe => ({...probe, deviceId: device.deviceId})));
  const readySources = sources.filter(source => source.available && source.present !== false && source.fresh !== false);
  const sourceOptions = <>{readySources.map(source => <option key={`${source.deviceId}:${source.probe}`} value={`${source.deviceId}|${source.probe}`}>{source.deviceId} · Probe {source.probe} · {source.temperatureC}°C</option>)}</>;
  const assign = async (measurementId: string, sourceValue: FormDataEntryValue | null) => {if (!sourceValue) return; const [coreDeviceId, channel] = String(sourceValue).split('|'); await mutate(`/api/v1/cooks/${cook.id}/assignments`, {measurementId, coreDeviceId, probeChannel: Number(channel)});};
  return <div className="cook-setup"><HardwareReadiness system={system}/><div className="setup-intro"><span className="step">Get ready</span><h2>Set up the cook</h2><p>Tell Pitblu what’s on the barbecue. Pit temperature is optional.</p></div>
    <section className="card setup-card"><span className="step">1 · The barbecue</span><h2>{cook.cookers[0]?.name ?? 'No barbecue selected'}</h2>{cook.cookers.length ? <><p className="muted">Want to watch the barbecue temperature? Add a pit probe. Otherwise, skip this.</p><form className="friendly-form" onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); const measurement = await api.request<Measurement>(`/api/v1/cooks/${cook.id}/measurements`, {method: 'POST', body: json({label: `${cook.cookers[0].name} pit`, kind: 'cooker', cookerId: cook.cookers[0].id, rangeMinC: Number(form.get('min')), rangeMaxC: Number(form.get('max'))})}); await assign(measurement.id, form.get('source'));}}><label>Pit probe<select name="source" required disabled={disabled}><option value="">Choose a probe</option>{sourceOptions}</select></label><div className="form-row"><label>Keep above °C<input name="min" type="number" defaultValue="105" required disabled={disabled}/></label><label>Keep below °C<input name="max" type="number" defaultValue="135" required disabled={disabled}/></label></div><button disabled={disabled || !readySources.length}>Watch pit temperature</button></form></> : <p>Go back and choose one of your saved barbecues when starting the Cook.</p>}</section>
    <section className="card setup-card"><span className="step">2 · The food</span><h2>What’s going on?</h2><div className="food-list">{cook.foodItems.map(item => <span key={item.id}>🍖 {item.name}</span>)}</div><form className="friendly-form" onSubmit={submitNamed(`/api/v1/cooks/${cook.id}/food-items`)}><label>Add food<input name="name" placeholder="Pork shoulder" required disabled={disabled}/></label><button className="secondary" disabled={disabled}>Add to this Cook</button></form></section>
    <section className="card setup-card"><span className="step">3 · Food probes</span><h2>Watch the important bits</h2><p className="muted">Add one measurement for each place you want to monitor.</p><form className="friendly-form" onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); const measurement = await api.request<Measurement>(`/api/v1/cooks/${cook.id}/measurements`, {method: 'POST', body: json({label: form.get('label'), kind: 'food', foodItemId: form.get('food') || null, targetTemperatureC: Number(form.get('target')), approachingMarginC: 3})}); await assign(measurement.id, form.get('source')); event.currentTarget.reset();}}><label>Call this spot<input name="label" placeholder="Brisket flat" required disabled={disabled}/></label><label>Food<select name="food" required disabled={disabled}><option value="">Choose food</option>{cook.foodItems.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Probe<select name="source" required disabled={disabled}><option value="">Choose a probe</option>{sourceOptions}</select></label><label>Ready at °C<input name="target" type="number" step=".1" required disabled={disabled}/></label><button disabled={disabled || !readySources.length || !cook.foodItems.length}>Add food probe</button></form></section>
    <section className="card setup-card"><span className="step">4 · Light the fire</span><h2>{cook.state === 'draft' ? 'Ready to cook?' : 'Cook underway'}</h2><form onSubmit={async event => {event.preventDefault(); const form = new FormData(event.currentTarget); await mutate(`/api/v1/cooks/${cook.id}`, {name: form.get('name'), anticipatedServeAt: form.get('serve') ? new Date(String(form.get('serve'))).toISOString() : null}, 'PATCH');}}><label>Cook name<input name="name" defaultValue={cook.name} required disabled={disabled}/></label><label>Eating around<input name="serve" type="datetime-local" defaultValue={cook.anticipatedServeAt ? new Date(new Date(cook.anticipatedServeAt).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16) : ''} disabled={disabled}/></label><button className="secondary" disabled={disabled}>Save</button></form>{cook.state === 'draft' && <button className="fire-button" onClick={() => void mutate(`/api/v1/cooks/${cook.id}/start`)}>🔥 Start cooking</button>}</section>
    {cook.measurements.length > 0 && <details className="card advanced"><summary>Fine-tune measurements and probe assignments</summary><div><h3>Measurements</h3>{cook.measurements.map(measurement => <MeasurementEditor key={measurement.id} measurement={measurement} disabled={disabled} mutate={mutate}/>)}</div><div><h3>Probe assignments</h3>{sources.map(source => {const current = cook.assignments?.find(item => item.coreDeviceId === source.deviceId && item.probeChannel === source.probe && !item.endedAt); const ready = source.available && source.present !== false && source.fresh !== false; return <form className="assignment" key={`${source.deviceId}:${source.probe}`} onSubmit={async event => {event.preventDefault(); const measurementId = new FormData(event.currentTarget).get('measurement'); if (measurementId) await mutate(`/api/v1/cooks/${cook.id}/assignments`, {measurementId, coreDeviceId: source.deviceId, probeChannel: source.probe}); else if (current) await mutate(`/api/v1/assignments/${current.id}`, undefined, 'DELETE');}}><span><strong>{source.deviceId} · Probe {source.probe}</strong><small>{ready ? `${source.temperatureC}°C` : 'Unavailable'}</small></span><select name="measurement" defaultValue={current?.measurementId ?? ''} disabled={disabled || (!ready && !current)}><option value="">Not used</option>{cook.measurements.map(item => <option value={item.id} key={item.id}>{item.label}</option>)}</select><button disabled={disabled || (!ready && !current)}>Save</button></form>;})}</div></details>}
    <details className="card advanced"><summary>Follower links</summary><ShareManager cook={cook} disabled={disabled} api={api}/></details>
  </div>;
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

function ReadOnlyCook({cook, readings, events, display, api}: {cook: Cook; readings: TemperatureReading[]; events: CookEvent[]; display: boolean; api: PitbluApi}) {
  const [share, setShare] = useState<Share | null>(null);
  useEffect(() => {
    if (!display || cook.state === 'closed') return;
    void api.request<Share>(`/api/v1/cooks/${cook.id}/default-share`).then(setShare);
  }, [api, cook.id, cook.state, display]);
  return <><LiveCookScreen cook={cook} readings={readings} events={events} alerts={cook.activeAlerts} readOnly/>{share && <section className="qr"><img alt="QR code to follow this cook" src={`/api/v1/shares/qr/${encodeURIComponent(share.token)}`}/><div><strong>Scan to follow the cook</strong><p>Available on this local network</p></div></section>}</>;
}
