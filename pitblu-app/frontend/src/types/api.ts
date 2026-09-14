export type CookState = 'draft' | 'active' | 'cooking_finished' | 'resting' | 'served' | 'closed';
export type MeasurementKind = 'food' | 'cooker' | 'other';

export interface ProbeState {
  probe: number;
  temperatureC: number | null;
  available: boolean;
  present?: boolean;
  fresh?: boolean;
  observedAt?: string;
}

export interface CoreDevice {
  deviceId: string;
  name?: string;
  friendlyName?: string;
  probes: ProbeState[];
  battery?: {available: boolean; fresh: boolean; percentage: number | null};
}

export interface SystemState {
  core: {available: boolean; devices: CoreDevice[]; lastError?: string | null};
  activeCook: Pick<Cook, 'id' | 'name' | 'state'> | null;
  latestCook: Pick<Cook, 'id' | 'name' | 'state'> | null;
}

export interface NamedResource { id: string; name: string; profileId?: string | null; }

export interface CookerProfile extends NamedResource {
  description: string | null;
  createdAt: string;
}

export interface Measurement {
  id: string;
  cookId: string;
  label: string;
  kind: MeasurementKind;
  foodItemId: string | null;
  cookerId: string | null;
  targetTemperatureC: number | null;
  approachingMarginC: number;
  rangeMinC: number | null;
  rangeMaxC: number | null;
  rangePersistenceSeconds: number;
  currentTemperatureC: number | null;
  currentObservedAt: string | null;
  available: boolean;
  interpretedState: string;
  trendCPerHour: number | null;
}

export interface ProbeAssignment {
  id: string;
  measurementId: string;
  coreDeviceId: string;
  probeChannel: number;
  startedAt: string;
  endedAt: string | null;
}

export interface Alert {
  id: string;
  cookId: string;
  measurementId: string;
  type: string;
  severity: 'prompt' | 'attention' | 'alarm';
  status: 'active' | 'acknowledged' | 'resolved';
  message: string;
  action: string | null;
  triggeredAt: string;
  resolvedAt: string | null;
}

export interface Cook {
  id: string;
  name: string;
  state: CookState;
  startedAt: string | null;
  anticipatedServeAt: string | null;
  cookingFinishedAt?: string | null;
  restStartedAt?: string | null;
  servedAt: string | null;
  closedAt: string | null;
  cookers: NamedResource[];
  foodItems: NamedResource[];
  measurements: Measurement[];
  assignments?: ProbeAssignment[];
  activeAlerts: Alert[];
}

export interface TemperatureReading {
  id?: string;
  measurementId: string | null;
  temperatureC: number | null;
  observedAt: string;
  available: boolean;
}

export interface CookEvent {
  id: string;
  cookId: string;
  type: string;
  note: string | null;
  occurredAt: string;
}

export interface Share {
  id: string;
  cookId: string;
  token: string;
  followerPath?: string;
  isDefault?: boolean;
}

export interface ShareSummary {
  id: string;
  cookId: string;
  createdAt: string;
  revokedAt: string | null;
  expiresAt: string | null;
  active: boolean;
  isDefault: boolean;
}

export interface ApplicationEvent<T = Record<string, unknown>> {
  eventId: string;
  type: string;
  occurredAt: string;
  data: T;
}

export interface ApiErrorEnvelope {
  error: {code: string; message: string; correlationId: string; details?: unknown};
}
