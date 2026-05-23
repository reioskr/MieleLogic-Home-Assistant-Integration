"""
Miele Logic communal laundry API client.

Talks to the MieleLogic (PayPerWash) booking system used by communal laundries
in Scandinavia. Wraps the REST API behind https://mielelogic.com.

Designed for future Home Assistant integration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import requests

logger = logging.getLogger(__name__)

AUTH_URL = "https://sec.mielelogic.com/v7/token"
API_URL = "https://api.mielelogic.com/v7"
CLIENT_ID = "YV1ZAQ7BTE9IT2ZBZXLJ"

COUNTRY_CODES = {
    "denmark": "DA",
    "dk": "DA",
    "sweden": "SE",
    "se": "SE",
    "norway": "NO",
    "no": "NO",
    "finland": "FI",
    "fi": "FI",
    "germany": "DE",
    "de": "DE",
}

MACHINE_TYPES = {
    "51": "washer",
    "57": "dryer",
}


class SlotStatus(str, Enum):
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    RESERVED_BY_ME = "ReservedByMe"
    UNAVAILABLE = "Unavailable"


class MachineSymbol(int, Enum):
    WASHER = 0
    DRYER = 1


class MachineColor(int, Enum):
    GREEN = 1  # idle / available
    RED = 2  # busy / in use
    YELLOW = 3  # finishing
    GREY = 0  # offline


@dataclass
class MachineState:
    laundry_number: int
    machine_number: int
    name: str
    machine_type: str
    status_text: str
    detail_text: str
    symbol: int
    color: int

    @property
    def is_busy(self) -> bool:
        return self.color != 1

    @property
    def type_name(self) -> str:
        return MACHINE_TYPES.get(self.machine_type, f"unknown({self.machine_type})")


@dataclass
class TimeSlot:
    machine_number: int
    machine_name: str
    start: datetime
    end: datetime
    status: SlotStatus

    @property
    def is_available(self) -> bool:
        return self.status == SlotStatus.AVAILABLE

    @property
    def is_mine(self) -> bool:
        return self.status == SlotStatus.RESERVED_BY_ME

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass
class Reservation:
    laundry_number: int
    machine_number: int
    start: datetime
    end: datetime


@dataclass
class Laundry:
    number: int
    name: str
    address: str
    zip_code: str


@dataclass
class AccountInfo:
    name: str
    card_number: str
    balance: float
    currency: str
    account_type: int
    apartment_number: str
    laundries: list[Laundry] = field(default_factory=list)


class AuthError(Exception):
    pass


class ApiError(Exception):
    pass


class MieleLogic:
    """Client for the MieleLogic communal laundry booking API."""

    def __init__(
        self,
        username: str,
        password: str,
        country: str = "dk",
    ):
        self._username = username
        self._password = password
        self._country_code = COUNTRY_CODES.get(country.lower(), country.upper())
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Origin": "https://mielelogic.com",
            "Referer": "https://mielelogic.com/",
        })
        self._token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires: datetime = datetime.min
        self._laundry_number: int | None = None

    def _ensure_auth(self) -> None:
        if self._token and datetime.utcnow() < self._token_expires - timedelta(seconds=30):
            return
        if self._refresh_token:
            try:
                self._do_refresh()
                return
            except Exception:
                logger.debug("Refresh failed, re-authenticating")
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
            raise AuthError(f"Login failed: {body.get('error_description', body)}")
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
        logger.debug("Authenticated as %s, token expires in %ds", body.get("userName"), expires_in)

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

    # ── Account ──────────────────────────────────────────────────────

    def get_account(self) -> AccountInfo:
        """Get account details including accessible laundries."""
        data = self._get("/accounts/Details")
        card = data["Cards"][0]
        laundries = [
            Laundry(
                number=int(l["LaundryNumber"]),
                name=l["Name"],
                address=l["Address"],
                zip_code=l["ZipCode"],
            )
            for l in data.get("AccessibleLaundries", [])
        ]
        if laundries and self._laundry_number is None:
            self._laundry_number = laundries[0].number
        return AccountInfo(
            name=card["Name"],
            card_number=card["CardContent"],
            balance=card["AccountBallance"],
            currency=card["Currency"],
            account_type=card["AccountType"],
            apartment_number=data.get("ApartmentNumber", ""),
            laundries=laundries,
        )

    @property
    def laundry_number(self) -> int:
        if self._laundry_number is None:
            self.get_account()
        assert self._laundry_number is not None
        return self._laundry_number

    @laundry_number.setter
    def laundry_number(self, value: int) -> None:
        self._laundry_number = value

    # ── Machine states ───────────────────────────────────────────────

    def get_machine_states(self, language: str = "da") -> list[MachineState]:
        """Get real-time status of all machines (running, idle, etc.)."""
        data = self._get(
            f"/Country/{self._country_code}/Laundry/{self.laundry_number}/laundrystates",
            params={"language": language},
        )
        return [
            MachineState(
                laundry_number=m["LaundryNumber"],
                machine_number=m["MachineNumber"],
                name=m["UnitName"],
                machine_type=str(m["MachineType"]),
                status_text=m["Text1"],
                detail_text=m.get("Text2", ""),
                symbol=m["MachineSymbol"],
                color=m["MachineColor"],
            )
            for m in data["MachineStates"]
        ]

    # ── Timetable ────────────────────────────────────────────────────

    def get_timetable(self, laundry_number: int | None = None) -> list[TimeSlot]:
        """
        Get the full booking timetable (typically 5 weeks ahead).
        Returns time slots for all machines that support reservations.
        """
        ln = laundry_number or self.laundry_number
        data = self._get(f"/country/{self._country_code}/laundry/{ln}/timetable")

        my_reservations = self._get_my_reservation_set(ln)

        slots: list[TimeSlot] = []
        for _key, machine in data.get("MachineTimeTables", {}).items():
            mn = machine["MachineNumber"]
            name = machine["MachineName"]
            for entry in machine.get("TimeTable", []):
                start = _parse_dt(entry["Start"])
                end = _parse_dt(entry["End"])
                status = SlotStatus(entry["Status"])
                if (mn, entry["Start"]) in my_reservations:
                    status = SlotStatus.RESERVED_BY_ME
                slots.append(TimeSlot(
                    machine_number=mn,
                    machine_name=name,
                    start=start,
                    end=end,
                    status=status,
                ))
        return slots

    def _get_my_reservation_set(self, laundry_number: int) -> set[tuple[int, str]]:
        """Get a set of (machine_number, start_iso) for my reservations."""
        try:
            data = self._get(f"/reservations", params={"laundry": laundry_number})
            return {
                (r["MachineNumber"], r["Start"])
                for r in data.get("Reservations", [])
            }
        except Exception:
            return set()

    def get_available_slots(
        self,
        machine_number: int | None = None,
        date: datetime | None = None,
    ) -> list[TimeSlot]:
        """Get available slots, optionally filtered by machine and/or date."""
        slots = self.get_timetable()
        result = []
        for s in slots:
            if not s.is_available:
                continue
            if machine_number and s.machine_number != machine_number:
                continue
            if date and s.start.date() != date.date():
                continue
            result.append(s)
        return result

    # ── Reservations ─────────────────────────────────────────────────

    def get_reservations(self, laundry_number: int | None = None) -> list[Reservation]:
        """Get your current reservations."""
        ln = laundry_number or self.laundry_number
        data = self._get("/reservations", params={"laundry": ln})
        return [
            Reservation(
                laundry_number=ln,
                machine_number=r["MachineNumber"],
                start=_parse_dt(r["Start"]),
                end=_parse_dt(r["End"]),
            )
            for r in data.get("Reservations", [])
        ]

    def create_reservation(
        self,
        machine_number: int,
        start: datetime,
        end: datetime,
        laundry_number: int | None = None,
    ) -> dict[str, Any]:
        """
        Book a time slot.

        Args:
            machine_number: Machine to book (1-5 for washers at your laundry).
            start: Slot start time (must match a timetable slot exactly).
            end: Slot end time (must match a timetable slot exactly).
            laundry_number: Override laundry (defaults to your primary).

        Returns:
            API response dict.
        """
        ln = laundry_number or self.laundry_number
        payload = {
            "MachineNumber": machine_number,
            "LaundryNumber": ln,
            "Start": _format_dt(start),
            "End": _format_dt(end),
        }
        return self._put("/reservations", json_data=payload)

    def delete_reservation(
        self,
        machine_number: int,
        start: datetime,
        end: datetime,
        laundry_number: int | None = None,
    ) -> dict[str, Any]:
        """Cancel a reservation."""
        ln = laundry_number or self.laundry_number
        return self._delete(
            "/reservations",
            params={
                "MachineNumber": machine_number,
                "LaundryNumber": ln,
                "Start": _format_dt(start),
                "End": _format_dt(end),
            },
        )

    # ── Convenience ──────────────────────────────────────────────────

    def book_next_available(
        self,
        machine_number: int | None = None,
        after: datetime | None = None,
    ) -> Reservation | None:
        """Book the next available slot. Returns the reservation or None if full."""
        after = after or datetime.utcnow()
        slots = self.get_available_slots(machine_number=machine_number)
        for slot in slots:
            if slot.start >= after:
                self.create_reservation(
                    machine_number=slot.machine_number,
                    start=slot.start,
                    end=slot.end,
                )
                return Reservation(
                    laundry_number=self.laundry_number,
                    machine_number=slot.machine_number,
                    start=slot.start,
                    end=slot.end,
                )
        return None

    def get_status_summary(self) -> dict[str, Any]:
        """
        One-call summary of everything: machine states + your reservations.
        Suitable for a Home Assistant sensor.
        """
        machines = self.get_machine_states()
        reservations = self.get_reservations()
        return {
            "machines": [
                {
                    "number": m.machine_number,
                    "name": m.name,
                    "type": m.type_name,
                    "status": m.status_text,
                    "detail": m.detail_text,
                    "busy": m.is_busy,
                }
                for m in machines
            ],
            "reservations": [
                {
                    "machine": r.machine_number,
                    "start": r.start.isoformat(),
                    "end": r.end.isoformat(),
                    "minutes_until": max(0, int((r.start - datetime.utcnow()).total_seconds() / 60)),
                }
                for r in reservations
            ],
        }


def _parse_dt(s: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s}")


def _format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")
