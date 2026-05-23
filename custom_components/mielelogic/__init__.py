"""Miele Logic Laundry integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .api import MieleLogicAPI
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_COUNTRY,
    ATTR_MACHINE_NUMBER,
    ATTR_START,
    ATTR_END,
)
from .coordinator import MieleLogicCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]

SERVICE_CREATE_RESERVATION = "create_reservation"
SERVICE_CANCEL_RESERVATION = "cancel_reservation"
SERVICE_UPDATE_SLOTS = "update_available_slots"

CREATE_RESERVATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MACHINE_NUMBER): cv.positive_int,
        vol.Required(ATTR_START): cv.string,
        vol.Required(ATTR_END): cv.string,
    }
)

CANCEL_RESERVATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MACHINE_NUMBER): cv.positive_int,
        vol.Required(ATTR_START): cv.string,
        vol.Required(ATTR_END): cv.string,
    }
)

DATE_OFFSET_MAP = {
    "Today": 0,
    "Tomorrow": 1,
    "+2 days": 2,
    "+3 days": 3,
    "+4 days": 4,
    "+5 days": 5,
    "+6 days": 6,
}

MACHINE_NAME_MAP = {
    "Vask 1": 1,
    "Vask 2": 2,
    "Vask 3": 3,
    "Vask 4": 4,
    "Vask 5": 5,
}


def _get_available_slots_for(
    timetable: dict[str, Any],
    target_date: str,
    machine_number: int | None,
) -> list[str]:
    """Extract available time slots from timetable data.

    Args:
        timetable: Raw timetable response from API.
        target_date: Date string like '2026-05-24'.
        machine_number: Specific machine, or None for all machines.

    Returns:
        List of slot strings like '09:00 - 11:00'.
    """
    machine_tables = timetable.get("MachineTimeTables", {})
    available_times: set[str] = set()

    for _key, machine in machine_tables.items():
        mn = machine.get("MachineNumber")
        if machine_number is not None and mn != machine_number:
            continue

        for entry in machine.get("TimeTable", []):
            if entry.get("Status") != "Available":
                continue
            start_str = entry.get("Start", "")
            if not start_str.startswith(target_date):
                continue
            try:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = datetime.fromisoformat(entry["End"])
                slot_label = (
                    f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
                )
                available_times.add(slot_label)
            except (ValueError, KeyError):
                continue

    return sorted(available_times)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Miele Logic from a config entry."""
    api = MieleLogicAPI(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        country=entry.data[CONF_COUNTRY],
    )

    coordinator = MieleLogicCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    async def handle_create_reservation(call: ServiceCall) -> None:
        """Handle create_reservation service call."""
        machine_number = call.data[ATTR_MACHINE_NUMBER]
        start = call.data[ATTR_START]
        end = call.data[ATTR_END]
        _LOGGER.info(
            "Creating reservation: machine=%s, start=%s, end=%s",
            machine_number, start, end,
        )
        await hass.async_add_executor_job(
            api.create_reservation, machine_number, start, end
        )
        await coordinator.async_request_refresh()

    async def handle_cancel_reservation(call: ServiceCall) -> None:
        """Handle cancel_reservation service call."""
        machine_number = call.data[ATTR_MACHINE_NUMBER]
        start = call.data[ATTR_START]
        end = call.data[ATTR_END]
        _LOGGER.info(
            "Cancelling reservation: machine=%s, start=%s, end=%s",
            machine_number, start, end,
        )
        await hass.async_add_executor_job(
            api.delete_reservation, machine_number, start, end
        )
        await coordinator.async_request_refresh()

    async def handle_update_available_slots(call: ServiceCall) -> None:
        """Update the laundry_timeslot input_select with actually available slots."""
        # Read current selections from helpers
        machine_state = hass.states.get("input_select.laundry_machine")
        date_state = hass.states.get("input_select.laundry_date")

        if not machine_state or not date_state:
            _LOGGER.warning("Laundry helper entities not found")
            return

        selected_machine = machine_state.state
        selected_date = date_state.state

        # Calculate target date
        day_offset = DATE_OFFSET_MAP.get(selected_date, 0)
        target = datetime.now() + timedelta(days=day_offset)
        target_date = target.strftime("%Y-%m-%d")

        # Get machine number
        machine_number = MACHINE_NAME_MAP.get(selected_machine)

        # Get available slots from cached timetable
        timetable = coordinator.data.get("timetable", {})
        if not timetable:
            _LOGGER.warning("No timetable data available")
            return

        available = _get_available_slots_for(timetable, target_date, machine_number)

        if not available:
            available = ["No slots available"]

        _LOGGER.debug(
            "Available slots for %s on %s: %s",
            selected_machine, target_date, available,
        )

        # Update the input_select options
        await hass.services.async_call(
            "input_select",
            "set_options",
            {
                "entity_id": "input_select.laundry_timeslot",
                "options": available,
            },
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_RESERVATION,
        handle_create_reservation,
        schema=CREATE_RESERVATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_RESERVATION,
        handle_cancel_reservation,
        schema=CANCEL_RESERVATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_SLOTS,
        handle_update_available_slots,
    )

    # Do initial slot update
    hass.async_create_task(handle_update_available_slots(None))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    # Only remove services if no more entries
    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_CREATE_RESERVATION)
        hass.services.async_remove(DOMAIN, SERVICE_CANCEL_RESERVATION)
        hass.services.async_remove(DOMAIN, SERVICE_UPDATE_SLOTS)

    return unload_ok
