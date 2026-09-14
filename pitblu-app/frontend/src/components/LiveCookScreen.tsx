import {useMemo, useState} from 'react';
import type {Alert, Cook, CookEvent, TemperatureReading} from '../types/api';
import {TemperatureChart} from './TemperatureChart';

const elapsed = (startedAt: string | null) => {
  if (!startedAt) return 'Not started';
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 60000));
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};

export function LiveCookScreen({cook, readings, events, alerts, readOnly, onEvent, onTransition, onEdit, onAcknowledge}: {
  cook: Cook; readings: TemperatureReading[]; events: CookEvent[]; alerts: Alert[]; readOnly: boolean;
  onEvent?: (type: string) => void; onTransition?: () => void; onEdit?: () => void; onAcknowledge?: (id: string) => void;
}) {
  const [focus, setFocus] = useState<string | null>(null);
  const groups = useMemo(() => {
    const result = new Map<string, typeof cook.measurements>();
    cook.measurements.forEach(measurement => {
      const label = cook.cookers.find(item => item.id === measurement.cookerId)?.name ?? (measurement.kind === 'food' ? 'Food' : 'Other');
      result.set(label, [...(result.get(label) ?? []), measurement]);
    });
    return [...result];
  }, [cook]);
  const transition: Partial<Record<typeof cook.state, string>> = {active: 'End cooking', cooking_finished: 'Start rest', resting: 'Mark served', served: 'Close cook'};
  return <div className="live-cook-screen">
    <section className="live-cook-hero">
      <div><span className="live-label"><i className="status-dot live"/>Live cook</span><h1>{cook.name}</h1><p>{cook.cookers.map(item => item.name).join(' · ') || 'Cook in progress'}</p></div>
      <div className="cook-timing"><span><small>Elapsed</small><strong>{elapsed(cook.startedAt)}</strong></span><span><small>Target serve</small><strong>{cook.anticipatedServeAt ? new Date(cook.anticipatedServeAt).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : 'Not set'}</strong></span></div>
      {!readOnly && transition[cook.state] && <button className="end-cook" onClick={onTransition}>{transition[cook.state]}</button>}
    </section>
    {alerts.length > 0 && <section className="cook-alerts" aria-label="Active alerts">{alerts.map(alert => <p key={alert.id}><span><strong>{alert.severity === 'alarm' ? 'Attention' : 'Heads up'}:</strong> {alert.message}</span>{!readOnly && alert.status === 'active' && <button onClick={() => onAcknowledge?.(alert.id)}>Acknowledge</button>}</p>)}</section>}
    <section className="cooker-groups">{groups.length ? groups.map(([name, measurements]) => <article className="cooker-group" key={name}><header><span aria-hidden="true">♨</span><div><h2>{name}</h2><small>{measurements.length} measurement{measurements.length === 1 ? '' : 's'}</small></div>{!readOnly && <button className="icon-action" onClick={onEdit} aria-label={`Edit ${name}`}>•••</button>}</header>{measurements.map(measurement => {
        const assignment = cook.assignments?.find(item => item.measurementId === measurement.id && !item.endedAt);
        const channel = assignment?.probeChannel;
        return <button className={`live-measurement ${focus === measurement.id ? 'selected' : ''}`} key={measurement.id} onClick={() => setFocus(measurement.id)}><span className={`probe-number probe-${channel ?? 0}`}>{channel ?? '·'}</span><span><small>{measurement.label}</small><strong>{measurement.available && measurement.currentTemperatureC !== null ? `${measurement.currentTemperatureC}°C` : 'Unavailable'}</strong></span><span className="measurement-target"><small>{measurement.targetTemperatureC !== null ? 'Target' : 'Range'}</small>{measurement.targetTemperatureC !== null ? `${measurement.targetTemperatureC}°C` : measurement.rangeMinC !== null ? `${measurement.rangeMinC}–${measurement.rangeMaxC}°C` : '—'}</span></button>;
      })}</article>) : <article className="cooker-group empty-group"><h2>No measurements configured</h2>{!readOnly && <button onClick={onEdit}>Set up probes</button>}</article>}</section>
    <section className="live-lower-grid"><article className="chart-panel"><div className="panel-heading"><h2>Chart view</h2><div className="chart-tabs"><button className={focus === null ? 'selected' : ''} onClick={() => setFocus(null)}>All probes</button>{cook.measurements.map(item => <button className={focus === item.id ? 'selected' : ''} onClick={() => setFocus(item.id)} key={item.id}>{item.label}</button>)}</div></div><TemperatureChart readings={readings} cook={cook} events={events} measurementId={focus}/></article>
      <article className="events-panel"><div className="panel-heading"><h2>Recent events</h2>{!readOnly && <button onClick={() => onEvent?.('note')}>+ Add event</button>}</div>{events.length ? events.slice(-6).reverse().map(event => <div className="compact-event" key={event.id}><time>{new Date(event.occurredAt).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</time><span>{event.note || event.type.replaceAll('_', ' ')}</span></div>) : <p className="muted">No events yet.</p>}{!readOnly && <div className="quick-events"><button onClick={() => onEvent?.('added_fuel')}>🔥 Added fuel</button><button onClick={() => onEvent?.('spritzed')}>💧 Spritzed</button><button onClick={() => onEvent?.('wrapped')}>Wrapped</button></div>}</article></section>
  </div>;
}
