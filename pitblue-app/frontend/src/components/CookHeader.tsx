import type {Cook} from '../types/api';

const time = (value: string | null) => value ? new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '—';

export function CookHeader({cook, now}: {cook: Cook; now: Date}) {
  const elapsed = cook.startedAt
    ? `${Math.max(0, Math.floor((now.getTime() - new Date(cook.startedAt).getTime()) / 60000))} min elapsed`
    : 'Not started';
  return <section className="hero">
    <div className="eyebrow">{cook.state === 'closed' ? 'Cook complete' : cook.state === 'draft' ? 'Setup' : '● Live'}</div>
    <h1>{cook.name}</h1>
    <div className="meta"><span>{elapsed}</span><span>{cook.anticipatedServeAt ? `Serve ${time(cook.anticipatedServeAt)}` : 'No serve target'}</span><span>{cook.state.replaceAll('_', ' ')}</span></div>
  </section>;
}
