import type {Alert} from '../types/api';

export function AlertList({alerts, canAcknowledge, onAcknowledge}: {
  alerts: Alert[]; canAcknowledge: boolean; onAcknowledge: (id: string) => void;
}) {
  return <>{alerts.map(alert => <div className={`alert ${alert.severity}`} key={alert.id}>
    <div><strong>{alert.message}</strong>{alert.action && <small>{alert.action}</small>}</div>
    {canAcknowledge && alert.status === 'active' && <button className="quiet" onClick={() => onAcknowledge(alert.id)}>Acknowledge</button>}
  </div>)}</>;
}
