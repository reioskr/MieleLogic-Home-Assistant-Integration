"""Sensor platform for Miele Logic integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MACHINE_TYPES
from .coordinator import MieleLogicCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: MieleLogicCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    # Create a sensor per machine
    machines = coordinator.data.get("machines", [])
    for machine in machines:
        entities.append(MachineSensor(coordinator, entry, machine))

    # Reservation count sensor
    entities.append(ReservationCountSensor(coordinator, entry))

    # Next reservation sensor
    entities.append(NextReservationSensor(coordinator, entry))

    async_add_entities(entities)


class MachineSensor(CoordinatorEntity[MieleLogicCoordinator], SensorEntity):
    """Sensor for a single laundry machine."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MieleLogicCoordinator,
        entry: ConfigEntry,
        machine: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._machine_number = machine["MachineNumber"]
        machine_type = MACHINE_TYPES.get(str(machine["MachineType"]), "machine")
        self._attr_name = f"{machine['UnitName']}"
        self._attr_unique_id = (
            f"mielelogic_{entry.data['username']}_{self._machine_number}"
        )
        self._attr_icon = (
            "mdi:washing-machine" if machine_type == "washer" else "mdi:tumble-dryer"
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, str(self.coordinator.api.laundry_number))},
            "name": f"Laundry {self.coordinator.api.laundry_number}",
            "manufacturer": "Miele",
            "model": "MieleLogic Communal Laundry",
        }

    @property
    def native_value(self) -> str | None:
        """Return the state (status text)."""
        for m in self.coordinator.data.get("machines", []):
            if m["MachineNumber"] == self._machine_number:
                return m.get("Text1", "Unknown")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        for m in self.coordinator.data.get("machines", []):
            if m["MachineNumber"] == self._machine_number:
                machine_type = MACHINE_TYPES.get(str(m["MachineType"]), "unknown")
                is_busy = m.get("MachineColor", 1) != 1
                return {
                    "machine_number": self._machine_number,
                    "machine_type": machine_type,
                    "busy": is_busy,
                    "detail": m.get("Text2", ""),
                    "color_code": m.get("MachineColor", 0),
                    "symbol": m.get("MachineSymbol", 0),
                    "group": m.get("GroupNumber", 0),
                    "laundry_number": m.get("LaundryNumber"),
                }
        return {}


class ReservationCountSensor(CoordinatorEntity[MieleLogicCoordinator], SensorEntity):
    """Sensor showing the number of active reservations."""

    _attr_has_entity_name = True
    _attr_name = "Reservations"
    _attr_icon = "mdi:calendar-check"

    def __init__(
        self,
        coordinator: MieleLogicCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"mielelogic_{entry.data['username']}_reservations"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, str(self.coordinator.api.laundry_number))},
            "name": f"Laundry {self.coordinator.api.laundry_number}",
            "manufacturer": "Miele",
            "model": "MieleLogic Communal Laundry",
        }

    @property
    def native_value(self) -> int:
        """Return number of active reservations."""
        return len(self.coordinator.data.get("reservations", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return reservation details as attributes."""
        reservations = self.coordinator.data.get("reservations", [])
        attrs: dict[str, Any] = {"max_reservations": 2}
        for i, r in enumerate(reservations):
            attrs[f"reservation_{i+1}_machine"] = r.get("MachineNumber")
            attrs[f"reservation_{i+1}_start"] = r.get("Start")
            attrs[f"reservation_{i+1}_end"] = r.get("End")
        return attrs


class NextReservationSensor(CoordinatorEntity[MieleLogicCoordinator], SensorEntity):
    """Sensor showing the next upcoming reservation."""

    _attr_has_entity_name = True
    _attr_name = "Next Reservation"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: MieleLogicCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"mielelogic_{entry.data['username']}_next_reservation"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, str(self.coordinator.api.laundry_number))},
            "name": f"Laundry {self.coordinator.api.laundry_number}",
            "manufacturer": "Miele",
            "model": "MieleLogic Communal Laundry",
        }

    @property
    def native_value(self):
        """Return the start time of the next reservation."""
        from datetime import datetime, timezone

        reservations = self.coordinator.data.get("reservations", [])
        if not reservations:
            return None

        now = datetime.now(timezone.utc)
        upcoming = []
        for r in reservations:
            try:
                start = datetime.fromisoformat(r["Start"]).replace(tzinfo=timezone.utc)
                if start > now:
                    upcoming.append(start)
            except (KeyError, ValueError):
                continue

        if upcoming:
            return min(upcoming)

        # If all reservations are in the past or current, return the first one
        try:
            return datetime.fromisoformat(
                reservations[0]["Start"]
            ).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the next reservation."""
        reservations = self.coordinator.data.get("reservations", [])
        if not reservations:
            return {}

        # Take the first reservation (usually earliest)
        r = reservations[0]
        return {
            "machine_number": r.get("MachineNumber"),
            "start": r.get("Start"),
            "end": r.get("End"),
        }
