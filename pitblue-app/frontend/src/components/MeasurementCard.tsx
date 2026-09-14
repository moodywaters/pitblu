import type {Measurement} from '../types/api';

export function MeasurementCard({measurement}: {measurement: Measurement}) {
  const target = measurement.targetTemperatureC != null
    ? `Target ${measurement.targetTemperatureC}°C`
    : measurement.rangeMinC != null ? `Range ${measurement.rangeMinC}–${measurement.rangeMaxC}°C` : '';
  return <article className={`card measurement ${measurement.available ? '' : 'unavailable'}`}>
    <h3>{measurement.label}</h3>
    <div className="temperature">{measurement.available && measurement.currentTemperatureC != null
      ? `${measurement.currentTemperatureC}°` : 'Unavailable'}</div>
    <div className="target">{target}</div>
    {!measurement.available && measurement.currentTemperatureC != null &&
      <p className="muted">Last reading {measurement.currentTemperatureC}°C</p>}
    {measurement.trendCPerHour != null && <p>{measurement.trendCPerHour > 0 ? '+' : ''}{measurement.trendCPerHour}°C/hour</p>}
    <small>{measurement.interpretedState?.replaceAll('_', ' ')}</small>
  </article>;
}
