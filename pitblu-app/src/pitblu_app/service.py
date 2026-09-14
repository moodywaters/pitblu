from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime
from typing import Any

from pitblu_app.events import ApplicationEvents
from pitblu_app.models import (
    AssignmentCreate,
    CookCreate,
    CookerProfileCreate,
    CookerProfilePatch,
    CookEventCreate,
    CookPatch,
    CookState,
    DomainError,
    MeasurementCreate,
    MeasurementPatch,
    NamedCreate,
    NamedPatch,
    TelemetryIn,
    utc_now,
)
from pitblu_app.store import Store, public_row


class CookService:
    def __init__(self, store: Store, events: ApplicationEvents, follower_secret: bytes) -> None:
        self.store = store
        self.events = events
        self.follower_secret = follower_secret
        self.reconcile_default_shares()

    def require_mutable_cook(self, cook_id: str) -> dict[str, Any]:
        cook = self.store.require("cooks", cook_id)
        if cook["state"] == CookState.CLOSED:
            raise DomainError("closed cooks are read-only")
        return cook

    async def create_cook(self, body: CookCreate) -> dict[str, Any]:
        item_id, created = self.store.ident("cook"), utc_now()
        now = created.isoformat()
        name = body.name or f"Cook {created.strftime('%d %b %Y').lstrip('0')}"
        profile_ids = list(
            dict.fromkeys(
                [
                    *body.cooker_profile_ids,
                    *([body.cooker_profile_id] if body.cooker_profile_id else []),
                ]
            )
        )
        profiles = [self.store.require("cooker_profiles", profile_id) for profile_id in profile_ids]
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO cooks(id,name,state,anticipated_serve_at,created_at) VALUES(?,?,?,?,?)",
                (item_id, name, CookState.DRAFT, self._dt(body.anticipated_serve_at), now),
            )
            for profile in profiles:
                db.execute(
                    "INSERT INTO cookers(id,cook_id,name,profile_id) VALUES(?,?,?,?)",
                    (self.store.ident("cooker"), item_id, profile["name"], profile["id"]),
                )
        item = self.cook(item_id)
        await self.events.publish("cook.created", item)
        return item

    def cooker_profiles(self) -> list[dict[str, Any]]:
        return [
            public_row(row) for row in self.store.all("SELECT * FROM cooker_profiles ORDER BY name")
        ]

    async def create_cooker_profile(self, body: CookerProfileCreate) -> dict[str, Any]:
        item_id = self.store.ident("cooker_profile")
        try:
            with self.store.transaction() as db:
                db.execute(
                    "INSERT INTO cooker_profiles(id,name,description,created_at) VALUES(?,?,?,?)",
                    (item_id, body.name, body.description, utc_now().isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise DomainError("a cooker with that name already exists") from exc
        item = public_row(self.store.require("cooker_profiles", item_id))
        await self.events.publish("cooker_profile.created", item)
        return item

    async def patch_cooker_profile(
        self, profile_id: str, body: CookerProfilePatch
    ) -> dict[str, Any]:
        self.store.require("cooker_profiles", profile_id)
        values = body.model_dump(exclude_unset=True)
        if values:
            try:
                with self.store.transaction() as db:
                    columns = ",".join(f"{key}=?" for key in values)
                    db.execute(
                        f"UPDATE cooker_profiles SET {columns} WHERE id=?",
                        (*values.values(), profile_id),
                    )
            except sqlite3.IntegrityError as exc:
                raise DomainError("a cooker with that name already exists") from exc
        item = public_row(self.store.require("cooker_profiles", profile_id))
        await self.events.publish("cooker_profile.updated", item)
        return item

    def cooks(self) -> list[dict[str, Any]]:
        return [
            public_row(row)
            for row in self.store.all("SELECT * FROM cooks ORDER BY created_at DESC")
        ]

    def cook(self, cook_id: str) -> dict[str, Any]:
        cook = public_row(self.store.require("cooks", cook_id))
        cook["cookers"] = [
            public_row(x)
            for x in self.store.all("SELECT * FROM cookers WHERE cook_id=?", (cook_id,))
        ]
        cook["foodItems"] = [
            public_row(x)
            for x in self.store.all("SELECT * FROM food_items WHERE cook_id=?", (cook_id,))
        ]
        cook["measurements"] = [
            self.measurement_state(x)
            for x in self.store.all("SELECT * FROM measurements WHERE cook_id=?", (cook_id,))
        ]
        cook["assignments"] = [
            public_row(x)
            for x in self.store.all(
                "SELECT * FROM assignments WHERE cook_id=? ORDER BY started_at", (cook_id,)
            )
        ]
        cook["activeAlerts"] = self.alerts(cook_id, active=True)
        return cook

    async def patch_cook(self, cook_id: str, body: CookPatch) -> dict[str, Any]:
        self.require_mutable_cook(cook_id)
        values = body.model_dump(exclude_unset=True)
        columns = []
        params: list[Any] = []
        for key, value in values.items():
            columns.append(f"{key}=?")
            params.append(self._dt(value) if isinstance(value, datetime) else value)
        if columns:
            with self.store.transaction() as db:
                db.execute(f"UPDATE cooks SET {','.join(columns)} WHERE id=?", (*params, cook_id))
        item = self.cook(cook_id)
        await self.events.publish("cook.updated", item)
        return item

    async def transition(self, cook_id: str, action: str) -> dict[str, Any]:
        row = self.store.require("cooks", cook_id)
        transitions = {
            "start": ({CookState.DRAFT}, CookState.ACTIVE, "started_at", "cook.started"),
            "finish": (
                {CookState.ACTIVE},
                CookState.COOKING_FINISHED,
                "cooking_finished_at",
                "cook.cooking_finished",
            ),
            "rest": (
                {CookState.COOKING_FINISHED},
                CookState.RESTING,
                "rest_started_at",
                "cook.rest_started",
            ),
            "serve": (
                {CookState.COOKING_FINISHED, CookState.RESTING},
                CookState.SERVED,
                "served_at",
                "cook.served",
            ),
            "close": (
                {CookState.COOKING_FINISHED, CookState.RESTING, CookState.SERVED},
                CookState.CLOSED,
                "closed_at",
                "cook.closed",
            ),
        }
        allowed, target, timestamp, event_type = transitions[action]
        if CookState(row["state"]) == target:
            return self.cook(cook_id)
        if CookState(row["state"]) not in allowed:
            raise DomainError(f"cannot {action} a cook in state {row['state']}")
        resolved_alert_ids: list[str] = []
        try:
            with self.store.transaction() as db:
                transition_time = utc_now().isoformat()
                db.execute(
                    f"UPDATE cooks SET state=?, {timestamp}=? WHERE id=?",
                    (target, transition_time, cook_id),
                )
                db.execute(
                    "INSERT INTO cook_events VALUES(?,?,?,?,?,?)",
                    (
                        self.store.ident("event"),
                        cook_id,
                        event_type.replace("cook.", ""),
                        None,
                        transition_time,
                        f"lifecycle:{action}",
                    ),
                )
                if action == "close":
                    db.execute(
                        "UPDATE assignments SET ended_at=? WHERE cook_id=? AND ended_at IS NULL",
                        (utc_now().isoformat(), cook_id),
                    )
                    db.execute(
                        "UPDATE follower_shares SET expires_at=? WHERE cook_id=? AND expires_at IS NULL",
                        (utc_now().isoformat(), cook_id),
                    )
                    resolved_alert_ids = [
                        alert["id"]
                        for alert in self.store.all(
                            "SELECT id FROM alerts WHERE cook_id=? "
                            "AND status IN ('active','acknowledged')",
                            (cook_id,),
                        )
                    ]
                    db.execute(
                        "UPDATE alerts SET status='resolved',resolved_at=? WHERE cook_id=? "
                        "AND status IN ('active','acknowledged')",
                        (transition_time, cook_id),
                    )
        except sqlite3.IntegrityError as exc:
            raise DomainError("another cook is already active") from exc
        if action == "start":
            self.ensure_default_share(cook_id)
        item = self.cook(cook_id)
        await self.events.publish(event_type, item)
        for alert_id in resolved_alert_ids:
            await self.events.publish(
                "alert.resolved", public_row(self.store.require("alerts", alert_id))
            )
        return item

    async def add_named(self, table: str, cook_id: str, body: NamedCreate) -> dict[str, Any]:
        self.require_mutable_cook(cook_id)
        if table not in {"cookers", "food_items"}:
            raise ValueError("invalid collection")
        prefix = "cooker" if table == "cookers" else "food"
        item_id = self.store.ident(prefix)
        with self.store.transaction() as db:
            db.execute(
                f"INSERT INTO {table}(id,cook_id,name) VALUES(?,?,?)", (item_id, cook_id, body.name)
            )
        item = public_row(self.store.require(table, item_id))
        await self.events.publish("cook.updated", {"cookId": cook_id})
        return item

    async def patch_named(self, table: str, item_id: str, body: NamedPatch) -> dict[str, Any]:
        existing = self.store.require(table, item_id)
        self.require_mutable_cook(existing["cook_id"])
        with self.store.transaction() as db:
            db.execute(f"UPDATE {table} SET name=? WHERE id=?", (body.name, item_id))
        item = public_row(self.store.require(table, item_id))
        await self.events.publish("cook.updated", {"cookId": item["cookId"]})
        return item

    async def add_measurement(self, cook_id: str, body: MeasurementCreate) -> dict[str, Any]:
        self.require_mutable_cook(cook_id)
        for table, item_id in (("cookers", body.cooker_id), ("food_items", body.food_item_id)):
            if item_id and self.store.require(table, item_id)["cook_id"] != cook_id:
                raise DomainError(
                    "related item belongs to a different cook", 422, "validation_error"
                )
        item_id = self.store.ident("measurement")
        values = body.model_dump()
        with self.store.transaction() as db:
            db.execute(
                """INSERT INTO measurements(id,cook_id,label,kind,cooker_id,food_item_id,
                target_temperature_c,approaching_margin_c,range_min_c,range_max_c,range_persistence_seconds)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (item_id, cook_id, *values.values()),
            )
        item = self.measurement(item_id)
        await self.events.publish("measurement.created", item)
        return item

    def measurement(self, measurement_id: str) -> dict[str, Any]:
        return self.measurement_state(self.store.require("measurements", measurement_id))

    def measurement_state(self, row: dict[str, Any]) -> dict[str, Any]:
        item = public_row(row)
        current, target = row["current_temperature_c"], row["target_temperature_c"]
        item["approachingTemperatureC"] = (
            target - row["approaching_margin_c"] if target is not None else None
        )
        if not row["available"]:
            item["interpretedState"] = "unavailable"
        elif target is not None and current is not None and current >= target:
            item["interpretedState"] = "target_reached"
        elif (
            target is not None
            and current is not None
            and current >= target - row["approaching_margin_c"]
        ):
            item["interpretedState"] = "approaching_target"
        elif (
            row["range_min_c"] is not None and current is not None and current < row["range_min_c"]
        ):
            item["interpretedState"] = "below_range"
        elif (
            row["range_max_c"] is not None and current is not None and current > row["range_max_c"]
        ):
            item["interpretedState"] = "above_range"
        else:
            item["interpretedState"] = "normal"
        recent = self.store.all(
            "SELECT temperature_c,observed_at FROM temperature_readings WHERE measurement_id=? AND available=1 AND temperature_c IS NOT NULL ORDER BY observed_at DESC LIMIT 12",
            (row["id"],),
        )
        item["trendCPerHour"] = self._trend(recent)
        return item

    async def patch_measurement(
        self, measurement_id: str, body: MeasurementPatch
    ) -> dict[str, Any]:
        existing = self.store.require("measurements", measurement_id)
        self.require_mutable_cook(existing["cook_id"])
        values = body.model_dump(exclude_unset=True)
        merged_min = values.get("range_min_c", existing["range_min_c"])
        merged_max = values.get("range_max_c", existing["range_max_c"])
        if merged_min is not None and merged_max is not None and merged_min >= merged_max:
            raise DomainError("rangeMinC must be below rangeMaxC", 422, "validation_error")
        if values:
            with self.store.transaction() as db:
                db.execute(
                    f"UPDATE measurements SET {','.join(f'{k}=?' for k in values)} WHERE id=?",
                    (*values.values(), measurement_id),
                )
        item = self.measurement(measurement_id)
        await self.events.publish("measurement.updated", item)
        return item

    async def assign(self, cook_id: str, body: AssignmentCreate) -> dict[str, Any]:
        self.require_mutable_cook(cook_id)
        measurement = self.store.require("measurements", body.measurement_id)
        if measurement["cook_id"] != cook_id:
            raise DomainError("measurement belongs to a different cook", 422, "validation_error")
        source_assignment = self.store.one(
            "SELECT * FROM assignments WHERE core_device_id=? AND probe_channel=? "
            "AND ended_at IS NULL",
            (body.core_device_id, body.probe_channel),
        )
        if source_assignment and source_assignment["cook_id"] != cook_id:
            raise DomainError("physical source is assigned to another open cook")
        now, item_id = utc_now().isoformat(), self.store.ident("assignment")
        with self.store.transaction() as db:
            db.execute(
                "UPDATE assignments SET ended_at=? WHERE cook_id=? AND ended_at IS NULL "
                "AND (measurement_id=? OR (core_device_id=? AND probe_channel=?))",
                (
                    now,
                    cook_id,
                    body.measurement_id,
                    body.core_device_id,
                    body.probe_channel,
                ),
            )
            db.execute(
                "INSERT INTO assignments VALUES(?,?,?,?,?,?,NULL)",
                (
                    item_id,
                    cook_id,
                    body.measurement_id,
                    body.core_device_id,
                    body.probe_channel,
                    now,
                ),
            )
        item = public_row(self.store.one("SELECT * FROM assignments WHERE id=?", (item_id,)) or {})
        await self.events.publish("probe.assignment.changed", item)
        return item

    async def end_assignment(self, assignment_id: str) -> dict[str, Any]:
        row = self.store.one("SELECT * FROM assignments WHERE id=?", (assignment_id,))
        if not row:
            raise DomainError("assignment not found", 404, "not_found")
        self.require_mutable_cook(row["cook_id"])
        with self.store.transaction() as db:
            db.execute(
                "UPDATE assignments SET ended_at=COALESCE(ended_at,?) WHERE id=?",
                (utc_now().isoformat(), assignment_id),
            )
        item = public_row(
            self.store.one("SELECT * FROM assignments WHERE id=?", (assignment_id,)) or {}
        )
        await self.events.publish("probe.assignment.changed", item)
        return item

    async def ingest(self, body: TelemetryIn) -> dict[str, Any] | None:
        cook = self.store.one(
            "SELECT * FROM cooks WHERE state IN ('active','cooking_finished','resting','served')"
        )
        if not cook:
            return None
        assignment = self.store.one(
            "SELECT * FROM assignments WHERE core_device_id=? AND probe_channel=? AND ended_at IS NULL",
            (body.core_device_id, body.probe_channel),
        )
        received = utc_now().isoformat()
        try:
            with self.store.transaction() as db:
                db.execute(
                    """INSERT INTO temperature_readings(cook_id,measurement_id,assignment_id,core_device_id,probe_channel,temperature_c,observed_at,received_at,available,event_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        cook["id"],
                        assignment["measurement_id"] if assignment else None,
                        assignment["id"] if assignment else None,
                        body.core_device_id,
                        body.probe_channel,
                        body.temperature_c,
                        body.observed_at.isoformat(),
                        received,
                        body.available,
                        body.event_id,
                    ),
                )
                if assignment:
                    db.execute(
                        "UPDATE measurements SET current_temperature_c=?,current_observed_at=?,available=? WHERE id=?",
                        (
                            body.temperature_c,
                            body.observed_at.isoformat(),
                            body.available,
                            assignment["measurement_id"],
                        ),
                    )
        except sqlite3.IntegrityError:
            return None
        if not assignment:
            return None
        await self.evaluate_alerts(assignment["measurement_id"])
        item = self.measurement(assignment["measurement_id"])
        await self.events.publish("measurement.updated", item)
        return item

    async def mark_feed_unavailable(self) -> None:
        measurements = self.store.all(
            "SELECT DISTINCT m.*,a.id AS assignment_id,a.core_device_id,a.probe_channel "
            "FROM measurements m JOIN assignments a "
            "ON a.measurement_id=m.id JOIN cooks c ON c.id=m.cook_id "
            "WHERE a.ended_at IS NULL AND c.state IN "
            "('active','cooking_finished','resting','served')"
        )
        with self.store.transaction() as db:
            for measurement in measurements:
                if not measurement["available"]:
                    continue
                observed_at = utc_now().isoformat()
                db.execute(
                    "INSERT INTO temperature_readings(cook_id,measurement_id,assignment_id,"
                    "core_device_id,probe_channel,temperature_c,observed_at,received_at,"
                    "available,event_id) VALUES(?,?,?,?,?,NULL,?,?,0,?)",
                    (
                        measurement["cook_id"],
                        measurement["id"],
                        measurement["assignment_id"],
                        measurement["core_device_id"],
                        measurement["probe_channel"],
                        observed_at,
                        observed_at,
                        f"feed-unavailable:{measurement['assignment_id']}:{observed_at}",
                    ),
                )
                db.execute(
                    "UPDATE measurements SET available=0 WHERE id=?",
                    (measurement["id"],),
                )
        for measurement in measurements:
            await self.evaluate_alerts(measurement["id"])
            await self.events.publish("measurement.updated", self.measurement(measurement["id"]))

    async def evaluate_alerts(self, measurement_id: str) -> None:
        row = self.store.require("measurements", measurement_id)
        conditions: dict[str, tuple[bool, str, str, str, dict[str, Any]]] = {}
        temp = row["current_temperature_c"]
        if row["target_temperature_c"] is not None and temp is not None:
            target = row["target_temperature_c"]
            conditions["temperature.approaching_target"] = (
                temp >= target - row["approaching_margin_c"] and temp < target,
                "prompt",
                f"{row['label']} is approaching target",
                "Check the food soon",
                {"targetTemperatureC": target},
            )
            conditions["temperature.target_reached"] = (
                temp >= target,
                "attention",
                f"{row['label']} has reached its target",
                "Check the meat",
                {"targetTemperatureC": target},
            )
        range_low = (
            temp is not None and row["range_min_c"] is not None and temp < row["range_min_c"]
        )
        range_high = (
            temp is not None and row["range_max_c"] is not None and temp > row["range_max_c"]
        )
        range_persisted = False
        if range_low or range_high:
            since = row["out_of_range_since"]
            if since is None:
                since = utc_now().isoformat()
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE measurements SET out_of_range_since=? WHERE id=?",
                        (since, measurement_id),
                    )
            elapsed = (utc_now() - datetime.fromisoformat(since)).total_seconds()
            range_persisted = elapsed >= row["range_persistence_seconds"]
        elif row["out_of_range_since"] is not None:
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE measurements SET out_of_range_since=NULL WHERE id=?",
                    (measurement_id,),
                )
        if temp is not None:
            if row["range_min_c"] is not None:
                conditions["temperature.below_range"] = (
                    range_low and range_persisted,
                    "alarm",
                    f"{row['label']} temperature is low",
                    "Check the cooker",
                    {"rangeMinC": row["range_min_c"]},
                )
            if row["range_max_c"] is not None:
                conditions["temperature.above_range"] = (
                    range_high and range_persisted,
                    "alarm",
                    f"{row['label']} temperature is high",
                    "Check the cooker",
                    {"rangeMaxC": row["range_max_c"]},
                )
        conditions["probe.unavailable"] = (
            not bool(row["available"]),
            "alarm",
            f"{row['label']} is unavailable",
            "Check the probe",
            {},
        )
        for kind, (triggered, severity, message, action, threshold) in conditions.items():
            active = self.store.one(
                "SELECT * FROM alerts WHERE measurement_id=? AND type=? AND status IN ('active','acknowledged')",
                (measurement_id, kind),
            )
            if triggered and not active:
                alert_id = self.store.ident("alert")
                with self.store.transaction() as db:
                    db.execute(
                        "INSERT INTO alerts(id,cook_id,measurement_id,type,severity,status,message,action,current_temperature_c,threshold_json,triggered_at) VALUES(?,?,?,?,?,'active',?,?,?,?,?)",
                        (
                            alert_id,
                            row["cook_id"],
                            measurement_id,
                            kind,
                            severity,
                            message,
                            action,
                            temp,
                            __import__("json").dumps(threshold),
                            utc_now().isoformat(),
                        ),
                    )
                await self.events.publish(
                    "alert.triggered", public_row(self.store.require("alerts", alert_id))
                )
            elif not triggered and active:
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE alerts SET status='resolved',resolved_at=? WHERE id=?",
                        (utc_now().isoformat(), active["id"]),
                    )
                await self.events.publish(
                    "alert.resolved", public_row(self.store.require("alerts", active["id"]))
                )

    def telemetry(
        self,
        cook_id: str,
        start: str | None,
        end: str | None,
        max_points: int | None = None,
    ) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM temperature_readings WHERE cook_id=?", [cook_id]
        if start:
            sql, params = sql + " AND observed_at>=?", [*params, start]
        if end:
            sql, params = sql + " AND observed_at<=?", [*params, end]
        rows = [public_row(x) for x in self.store.all(sql + " ORDER BY observed_at", tuple(params))]
        if max_points is None or len(rows) <= max_points:
            return rows
        mandatory = {0, len(rows) - 1}
        mandatory.update(index for index, row in enumerate(rows) if not row["available"])
        remaining = max(max_points - len(mandatory), 0)
        stride = max(len(rows) / max(remaining, 1), 1)
        selected = mandatory | {
            min(int(index * stride), len(rows) - 1) for index in range(remaining)
        }
        return [row for index, row in enumerate(rows) if index in selected]

    def assignments(self, cook_id: str) -> list[dict[str, Any]]:
        self.store.require("cooks", cook_id)
        return [
            public_row(row)
            for row in self.store.all(
                "SELECT * FROM assignments WHERE cook_id=? ORDER BY started_at",
                (cook_id,),
            )
        ]

    def shares(self, cook_id: str) -> list[dict[str, Any]]:
        self.store.require("cooks", cook_id)
        return [
            {
                "id": row["id"],
                "cookId": row["cook_id"],
                "createdAt": row["created_at"],
                "revokedAt": row["revoked_at"],
                "expiresAt": row["expires_at"],
                "active": row["revoked_at"] is None and row["expires_at"] is None,
                "isDefault": bool(row["is_default"]),
            }
            for row in self.store.all(
                "SELECT * FROM follower_shares WHERE cook_id=? ORDER BY created_at",
                (cook_id,),
            )
        ]

    async def add_event(
        self, cook_id: str, body: CookEventCreate, key: str | None
    ) -> dict[str, Any]:
        self.require_mutable_cook(cook_id)
        if key:
            existing = self.store.one(
                "SELECT * FROM cook_events WHERE cook_id=? AND idempotency_key=?", (cook_id, key)
            )
            if existing:
                return public_row(existing)
        item_id = self.store.ident("event")
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO cook_events VALUES(?,?,?,?,?,?)",
                (
                    item_id,
                    cook_id,
                    body.type,
                    body.note,
                    self._dt(body.occurred_at) or utc_now().isoformat(),
                    key,
                ),
            )
        item = public_row(self.store.one("SELECT * FROM cook_events WHERE id=?", (item_id,)) or {})
        await self.events.publish("cook_event.created", item)
        return item

    def alerts(self, cook_id: str | None = None, active: bool = False) -> list[dict[str, Any]]:
        clauses, params = [], []
        if cook_id:
            clauses.append("cook_id=?")
            params.append(cook_id)
        if active:
            clauses.append("status IN ('active','acknowledged')")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return [
            public_row(x)
            for x in self.store.all(
                "SELECT * FROM alerts" + where + " ORDER BY triggered_at DESC", tuple(params)
            )
        ]

    async def acknowledge(self, alert_id: str) -> dict[str, Any]:
        alert = self.store.require("alerts", alert_id)
        if alert["status"] == "active":
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE alerts SET status='acknowledged',acknowledged_at=? WHERE id=?",
                    (utc_now().isoformat(), alert_id),
                )
        item = public_row(self.store.require("alerts", alert_id))
        await self.events.publish("alert.acknowledged", item)
        return item

    def create_share(self, cook_id: str) -> tuple[dict[str, Any], str]:
        cook = self.store.require("cooks", cook_id)
        if cook["state"] in {CookState.DRAFT, CookState.CLOSED}:
            raise DomainError("only a live cook can be shared")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        item_id = self.store.ident("share")
        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO follower_shares(id,cook_id,token_hash,created_at) VALUES(?,?,?,?)",
                (item_id, cook_id, digest, utc_now().isoformat()),
            )
        return {"id": item_id, "cookId": cook_id, "createdAt": utc_now().isoformat()}, token

    def reconcile_default_shares(self) -> None:
        for cook in self.store.all(
            "SELECT id FROM cooks WHERE state IN ('active','cooking_finished','resting','served')"
        ):
            self.ensure_default_share(cook["id"])

    def ensure_default_share(self, cook_id: str) -> dict[str, Any]:
        cook = self.store.require("cooks", cook_id)
        if cook["state"] not in {
            CookState.ACTIVE,
            CookState.COOKING_FINISHED,
            CookState.RESTING,
            CookState.SERVED,
        }:
            raise DomainError("default follower share is available only for a live cook")
        existing = self.store.one(
            "SELECT * FROM follower_shares WHERE cook_id=? AND is_default=1 "
            "AND revoked_at IS NULL AND expires_at IS NULL",
            (cook_id,),
        )
        if existing and existing["token_nonce"]:
            token = self._default_follower_token(cook_id, existing["token_nonce"])
            if hmac.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), existing["token_hash"]
            ):
                return self._default_share_response(existing, token)
        now = utc_now().isoformat()
        nonce = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
        token = self._default_follower_token(cook_id, nonce)
        item_id = self.store.ident("share")
        with self.store.transaction() as db:
            db.execute(
                "UPDATE follower_shares SET expires_at=? WHERE cook_id=? AND is_default=1 "
                "AND revoked_at IS NULL AND expires_at IS NULL",
                (now, cook_id),
            )
            db.execute(
                "INSERT INTO follower_shares(id,cook_id,token_hash,created_at,is_default,token_nonce) "
                "VALUES(?,?,?,?,1,?)",
                (item_id, cook_id, hashlib.sha256(token.encode()).hexdigest(), now, nonce),
            )
        row = self.store.one("SELECT * FROM follower_shares WHERE id=?", (item_id,))
        assert row is not None
        return self._default_share_response(row, token)

    def regenerate_default_share(self, cook_id: str) -> dict[str, Any]:
        now = utc_now().isoformat()
        with self.store.transaction() as db:
            db.execute(
                "UPDATE follower_shares SET revoked_at=? WHERE cook_id=? AND is_default=1 "
                "AND revoked_at IS NULL AND expires_at IS NULL",
                (now, cook_id),
            )
        return self.ensure_default_share(cook_id)

    def _default_follower_token(self, cook_id: str, nonce: str) -> str:
        signature = hmac.new(
            self.follower_secret, f"{cook_id}:{nonce}".encode(), hashlib.sha256
        ).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return f"{nonce}.{encoded_signature}"

    @staticmethod
    def _default_share_response(row: dict[str, Any], token: str) -> dict[str, Any]:
        return {
            "id": row["id"],
            "cookId": row["cook_id"],
            "createdAt": row["created_at"],
            "isDefault": True,
            "token": token,
            "followerPath": f"/follow/{token}",
        }

    def follower_cook(self, token: str) -> dict[str, Any]:
        share = self.follower_share(token)
        cook = self.cook(share["cook_id"])
        cook.pop("assignments", None)
        return cook

    def follower_share(self, token: str) -> dict[str, Any]:
        digest = hashlib.sha256(token.encode()).hexdigest()
        share = self.store.one(
            "SELECT * FROM follower_shares WHERE token_hash=? AND revoked_at IS NULL "
            "AND expires_at IS NULL",
            (digest,),
        )
        if not share:
            raise DomainError("This live cook is no longer available", 404, "share_unavailable")
        return share

    def follower_telemetry(
        self, token: str, start: str | None, end: str | None, max_points: int | None
    ) -> list[dict[str, Any]]:
        share = self.follower_share(token)
        rows = self.telemetry(share["cook_id"], start, end, max_points)
        for row in rows:
            row.pop("coreDeviceId", None)
            row.pop("probeChannel", None)
            row.pop("assignmentId", None)
            row.pop("receivedAt", None)
            row.pop("event_id", None)
        return rows

    def follower_events(self, token: str) -> list[dict[str, Any]]:
        share = self.follower_share(token)
        return [
            public_row(row)
            for row in self.store.all(
                "SELECT id,cook_id,type,note,occurred_at FROM cook_events "
                "WHERE cook_id=? ORDER BY occurred_at",
                (share["cook_id"],),
            )
        ]

    def revoke_share(self, share_id: str) -> None:
        with self.store.transaction() as db:
            db.execute(
                "UPDATE follower_shares SET revoked_at=? WHERE id=?",
                (utc_now().isoformat(), share_id),
            )

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _trend(rows: list[dict[str, Any]]) -> float | None:
        if len(rows) < 3:
            return None
        values = list(reversed(rows))
        start, end = values[0], values[-1]
        seconds = (
            datetime.fromisoformat(end["observed_at"])
            - datetime.fromisoformat(start["observed_at"])
        ).total_seconds()
        return (
            round((end["temperature_c"] - start["temperature_c"]) * 3600 / seconds, 1)
            if seconds > 0
            else None
        )
