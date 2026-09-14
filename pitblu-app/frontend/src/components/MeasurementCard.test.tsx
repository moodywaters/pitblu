import {render, screen} from '@testing-library/react';
import {MeasurementCard} from './MeasurementCard';
import type {Measurement} from '../types/api';

const measurement: Measurement = {
  id: 'm1', cookId: 'c1', label: 'Brisket Flat', kind: 'food', foodItemId: 'f1',
  cookerId: null, targetTemperatureC: 93, approachingMarginC: 3, rangeMinC: null,
  rangeMaxC: null, rangePersistenceSeconds: 120, currentTemperatureC: 68, currentObservedAt: '2026-01-01T00:00:00Z',
  available: true, interpretedState: 'normal', trendCPerHour: 2.4
};

it('renders semantic meaning and backend interpretation', () => {
  render(<MeasurementCard measurement={measurement}/>);
  expect(screen.getByRole('heading', {name: 'Brisket Flat'})).toBeInTheDocument();
  expect(screen.getByText('68°')).toBeInTheDocument();
  expect(screen.getByText('Target 93°C')).toBeInTheDocument();
});

it('does not present an unavailable value as live', () => {
  render(<MeasurementCard measurement={{...measurement, available: false}}/>);
  expect(screen.getByText('Unavailable')).toBeInTheDocument();
  expect(screen.getByText('Last reading 68°C')).toBeInTheDocument();
});
