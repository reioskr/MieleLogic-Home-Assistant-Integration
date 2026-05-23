"""MieleLogic API client for Home Assistant."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

from .const import AUTH_URL, API_URL, CLIENT_ID, COUNTRY_CODES, MACHINE_TYPES

_LOGGER = logging.getLogger(__name__)


class AuthError(Exception):
    """Authentication error."""


class ApiError(Exception):
    """API error."""


class MieleLogicAPI:
    """Client for the MieleLogic communal laundry booking API."""

    def __init__(self, username: str, password: str, country: str = "dk") -> None:
        self._username = username
        self._password = password
        self._country_code = COUNTRY_CODES.get(country.lower(), country.upper())
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Origin": "https://mielelogic.com",
            "Referer": "https://mielelogic.com/",
        })
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires: datetime = datetime.min
        self._laundry_number: int | None = None
        self._user_name: str | None = None

    @property
    def laundry_number(self) -> int | None:
        return self._laundry_number

    @property
    def user_name(self) -> str | None:
        return self._user_name

    @property
    def country_code(self) -> str:
        return self._country_code

    def _ensure_auth(self) -> None:
        now = datetime.utcnow()
        if self._token and now < self._token_expires - timedelta(seconds=30):
            return
        if self._refresh_token:
            try:
                self._do_refresh()
                return
            except Exception:
                _LOGGER.debug("Refresh failed, re-authenticating")
        self._do_login()

    def _do_login(self) -> None:
        data = (
            f"grant_type=password"
            f"&username={self._username}"
            f"&password={requests.utils.quote(self._password)}"
            f"&client_id={CLIENT_ID}"
            f"&scope={self._country_code}"
        )
        resp = self._session.post(
            AUTH_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise AuthError(f"Login failed: {resp.text}")
        body = resp.json()
        if "access_token" not in body:
            raise AuthError(
                f"Login failed: {body.get('error_description', body)}"
            )
        self._apply_token(body)

    def _do_refresh(self) -> None:
        data = (
            f"grant_type=refresh_token"
            f"&refresh_token={self._refresh_token}"
            f"&client_id={CLIENT_ID}"
        )
        resp = self._session.post(
            AUTH_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise AuthError("Token refresh failed")
        self._apply_token(resp.json())

    def _apply_token(self, body: dict[str, Any]) -> None:
        self._token = body["access_token"]
        self._refresh_token = body.get("refresh_token")
        expires_in = int(body.get("expires_in", 900))
        self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        self._session.headers["Authorization"] = f"Bearer {self._token}"
        self._user_name = body.get("userName")

    def _get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self._ensure_auth()
        resp = self._session.get(f"{API_URL}{path}", **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ResultOK", True):
            raise ApiError(data.get("ResultText", "Unknown error"))
        return data

    def _put(self, path: str, json_data: Any = None, **kwargs: Any) -> dict[str, Any]:
        self._ensure_auth()
        resp = self._session.put(f"{API_URL}{path}", json=json_data, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ResultOK", True):
            raise ApiError(data.get("ResultText", "Unknown error"))
        return data

    def _delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        self._ensure_auth()
        resp = self._session.delete(f"{API_URL}{path}", **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ResultOK", True):
            raise ApiError(data.get("ResultText", "Unknown error"))
        return data

    def test_connection(self) -> bool:
        """Test if credentials are valid."""
        try:
            self._do_login()
            return True
        except Exception:
            return False

    def get_account(self) -> dict[str, Any]:
        """Get account details."""
        data = self._get("/accounts/Details")
        laundries = data.get("AccessibleLaundries", [])
        if laundries and self._laundry_number is None:
            self._laundry_number = int(laundries[0]["LaundryNumber"])
        return data

    def get_machine_states(self, language: str = "en") -> list[dict[str, Any]]:
        """Get real-time status of all machines."""
        if self._laundry_number is None:
            self.get_account()
        data = self._get(
            f"/Country/{self._country_code}/Laundry/{self._laundry_number}"
            f"/laundrystates",
            params={"language": language},
        )
        return data.get("MachineStates", [])

    def get_timetable(self) -> dict[str, Any]:
        """Get the full booking timetable."""
        if self._laundry_number is None:
            self.get_account()
        return self._get(
            f"/country/{self._country_code}/laundry/{self._laundry_number}/timetable"
        )

    def get_reservations(self) -> list[dict[str, Any]]:
        """Get user's current reservations."""
        if self._laundry_number is None:
            self.get_account()
        data = self._get("/reservations", params={"laundry": self._laundry_number})
        return data.get("Reservations", [])

    def get_max_reservations(self) -> int:
        """Get the max number of simultaneous reservations."""
        if self._laundry_number is None:
            self.get_account()
        data = self._get("/reservations", params={"laundry": self._laundry_number})
        return data.get("MaxUserReservations", 2)

    def create_reservation(
        self, machine_number: int, start: str, end: str
    ) -> dict[str, Any]:
        """Create a reservation. start/end are ISO datetime strings."""
        if self._laundry_number is None:
            self.get_account()
        payload = {
            "MachineNumber": machine_number,
            "LaundryNumber": self._laundry_number,
            "Start": start,
            "End": end,
        }
        return self._put("/reservations", json_data=payload)

    def delete_reservation(
        self, machine_number: int, start: str, end: str
    ) -> dict[str, Any]:
        """Delete a reservation. start/end are ISO datetime strings."""
        if self._laundry_number is None:
            self.get_account()
        return self._delete(
            "/reservations",
            params={
                "MachineNumber": machine_number,
                "LaundryNumber": self._laundry_number,
                "Start": start,
                "End": end,
            },
        )
