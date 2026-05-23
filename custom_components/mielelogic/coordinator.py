"""DataUpdateCoordinator for MieleLogic."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MieleLogicAPI, ApiError, AuthError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class MieleLogicCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching MieleLogic data."""

    def __init__(self, hass: HomeAssistant, api: MieleLogicAPI) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            account = await self.hass.async_add_executor_job(self.api.get_account)
            machines = await self.hass.async_add_executor_job(self.api.get_machine_states)
            reservations = await self.hass.async_add_executor_job(
                self.api.get_reservations
            )
            timetable = await self.hass.async_add_executor_job(self.api.get_timetable)

            return {
                "account": account,
                "machines": machines,
                "reservations": reservations,
                "timetable": timetable,
                "laundry_number": self.api.laundry_number,
            }
        except AuthError as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except ApiError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
