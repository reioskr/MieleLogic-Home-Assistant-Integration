"""Calendar platform for Miele Logic integration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
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
    """Set up calendar from a config entry."""
    coordinator: MieleLogicCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MieleLogicCalendar(coordinator, entry)])


class MieleLogicCalendar(
    CoordinatorEntity[MieleLogicCoordinator], CalendarEntity
):
    """Calendar entity showing laundry reservations."""

    _attr_has_entity_name = True
    _attr_name = "Laundry Bookings"
    _attr_icon = "mdi:washing-machine"

    def __init__(
        self,
        coordinator: MieleLogicCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"mielelogic_{entry.data['username']}_calendar"

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
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        events = self._get_events_from_data()
        if not events:
            return None
        now = datetime.now(timezone.utc)
        # Find current or next event
        for ev in events:
            if ev.end > now:
                return ev
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events in a date range."""
        events = self._get_events_from_data()
        return [
            ev
            for ev in events
            if ev.start < end_date and ev.end > start_date
        ]

    def _get_events_from_data(self) -> list[CalendarEvent]:
        """Convert reservations to calendar events."""
        reservations = self.coordinator.data.get("reservations", [])
        machines = self.coordinator.data.get("machines", [])

        # Build machine name lookup
        machine_names: dict[int, str] = {}
        for m in machines:
            mn = m["MachineNumber"]
            machine_type = MACHINE_TYPES.get(str(m["MachineType"]), "Machine")
            machine_names[mn] = f"{m['UnitName']} ({machine_type.title()})"

        events: list[CalendarEvent] = []
        for r in reservations:
            try:
                mn = r["MachineNumber"]
                start = datetime.fromisoformat(r["Start"]).replace(tzinfo=timezone.utc)
                end = datetime.fromisoformat(r["End"]).replace(tzinfo=timezone.utc)
                name = machine_names.get(mn, f"Machine {mn}")

                events.append(
                    CalendarEvent(
                        summary=f"🧺 {name}",
                        start=start,
                        end=end,
                        description=f"Laundry reservation on {name}",
                    )
                )
            except (KeyError, ValueError) as err:
                _LOGGER.warning("Failed to parse reservation: %s", err)
                continue

        events.sort(key=lambda e: e.start)
        return events
