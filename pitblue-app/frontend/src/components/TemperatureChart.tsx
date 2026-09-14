import {useEffect, useRef} from 'react';
import type {Cook, CookEvent, TemperatureReading} from '../types/api';

export function TemperatureChart({readings, cook, events}: {
  readings: TemperatureReading[]; cook: Cook; events: CookEvent[];
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const values = readings.filter(row => row.temperatureC != null);
    if (!canvas || !values.length) return;
    const width = canvas.clientWidth || 800, height = 340, ratio = devicePixelRatio || 1;
    canvas.width = width * ratio; canvas.height = height * ratio;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.scale(ratio, ratio);
    const temperatures = values.map(row => row.temperatureC as number);
    const low = Math.min(...temperatures) - 5, high = Math.max(...temperatures) + 5;
    const stamps = values.map(row => new Date(row.observedAt).getTime());
    const first = Math.min(...stamps), span = Math.max(Math.max(...stamps) - first, 1);
    const x = (stamp: string) => 44 + (new Date(stamp).getTime() - first) / span * (width - 64);
    const y = (temp: number) => 310 - (temp - low) / (high - low) * 270;
    const colors = ['#0878e8', '#27a77d', '#ee9d34', '#a56ce6', '#e95572', '#087f8c'];
    cook.measurements.forEach((measurement, index) => {
      const rows = readings.filter(row => row.measurementId === measurement.id);
      context.beginPath(); context.strokeStyle = colors[index % colors.length]; context.lineWidth = 3;
      let active = false;
      rows.forEach(row => {
        if (!row.available || row.temperatureC == null) { active = false; return; }
        active ? context.lineTo(x(row.observedAt), y(row.temperatureC)) : context.moveTo(x(row.observedAt), y(row.temperatureC));
        active = true;
      });
      context.stroke();
      if (measurement.targetTemperatureC != null) {
        context.save(); context.setLineDash([7, 6]); context.globalAlpha = .5;
        context.beginPath(); context.moveTo(44, y(measurement.targetTemperatureC));
        context.lineTo(width - 20, y(measurement.targetTemperatureC)); context.stroke(); context.restore();
      }
    });
    context.save(); context.strokeStyle = '#6f8499'; context.globalAlpha = .35; context.lineWidth = 1;
    events.forEach(event => {
      const stamp = new Date(event.occurredAt).getTime();
      if (stamp < first || stamp > first + span) return;
      context.beginPath(); context.moveTo(x(event.occurredAt), 30); context.lineTo(x(event.occurredAt), 310); context.stroke();
    });
    context.restore();
  }, [readings, cook, events]);
  return readings.length ? <canvas ref={ref} aria-label="Temperature history chart" />
    : <p className="muted">No telemetry recorded yet.</p>;
}
