"""Quick demo of the MieleLogic library."""

from datetime import datetime, timedelta
from mielelogic import MieleLogic

def main():
    client = MieleLogic(
        username="",
        password="",
        country="dk",
    )

    # 1. Account info
    account = client.get_account()
    print(f"=== Account: {account.name} ===")
    print(f"Card: {account.card_number}")
    print(f"Balance: {account.balance} {account.currency}")
    print(f"Apartment: {account.apartment_number}")
    print()
    for l in account.laundries:
        print(f"  Laundry #{l.number}: {l.name} ({l.address}, {l.zip_code})")
    print()

    # 2. Machine states (live)
    print("=== Machine States ===")
    machines = client.get_machine_states()
    for m in machines:
        status = "BUSY" if m.is_busy else "idle"
        print(f"  {m.name} ({m.type_name}): {m.status_text} [{status}] {m.detail_text}")
    print()

    # 3. Your reservations
    print("=== My Reservations ===")
    reservations = client.get_reservations()
    if not reservations:
        print("  (none)")
    for r in reservations:
        print(f"  Machine {r.machine_number}: {r.start} -> {r.end}")
    print()

    # 4. Available slots for today and tomorrow
    print("=== Available Slots (next 2 days) ===")
    today = datetime.utcnow()
    tomorrow = today + timedelta(days=1)
    for day in [today, tomorrow]:
        slots = client.get_available_slots(date=day)
        if slots:
            print(f"  {day.strftime('%A %Y-%m-%d')}:")
            for s in slots:
                print(f"    {s.machine_name}: {s.start.strftime('%H:%M')}-{s.end.strftime('%H:%M')}")
    print()

    # 5. Full status summary (HASS-friendly)
    print("=== Status Summary (JSON-ready for HASS) ===")
    import json
    summary = client.get_status_summary()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
