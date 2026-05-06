"""JSON file storage for the delivery management bot."""
import json
import os
import threading
from datetime import datetime, timedelta
from typing import Any

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
_lock = threading.Lock()


def _empty_data() -> dict[str, Any]:
    return {
        "expenses": [],
        "incomes": [],
        "customers": [],
        "users": [],
        "next_expense_id": 1,
        "next_income_id": 1,
        "next_customer_id": 1,
    }


def _load() -> dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return _empty_data()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _empty_data()
    base = _empty_data()
    base.update(data)
    return base


def _save(data: dict[str, Any]) -> None:
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


# ---------------- Expenses ----------------

def add_expense(user_id: int, amount: float, category: str, description: str) -> dict[str, Any]:
    with _lock:
        data = _load()
        expense = {
            "id": data["next_expense_id"],
            "user_id": user_id,
            "amount": float(amount),
            "category": category,
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        }
        data["next_expense_id"] += 1
        data["expenses"].append(expense)
        _save(data)
        return expense


def get_expenses_between(user_id: int, start: datetime, end: datetime) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
    out = []
    for e in data["expenses"]:
        if e["user_id"] != user_id:
            continue
        try:
            ts = datetime.fromisoformat(e["timestamp"])
        except ValueError:
            continue
        if start <= ts < end:
            out.append(e)
    out.sort(key=lambda x: x["timestamp"])
    return out


def get_expenses_today(user_id: int) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)
    return get_expenses_between(user_id, start, end)


def get_expenses_last_n_days(user_id: int, days: int) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    end = datetime(now.year, now.month, now.day) + timedelta(days=1)
    start = end - timedelta(days=days)
    return get_expenses_between(user_id, start, end)


def get_expenses_current_week(user_id: int) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Return expenses for the current week (Monday 00:00 to next Monday 00:00, UTC)."""
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    start = today - timedelta(days=today.weekday())  # Monday
    end = start + timedelta(days=7)
    return get_expenses_between(user_id, start, end), start, end


def get_expenses_previous_week(user_id: int) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Return expenses for the previous Mon–Sun week (UTC)."""
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    this_monday = today - timedelta(days=today.weekday())
    prev_start = this_monday - timedelta(days=7)
    prev_end = this_monday
    return get_expenses_between(user_id, prev_start, prev_end), prev_start, prev_end


def get_expenses_current_month(user_id: int) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Return expenses for the current calendar month (UTC)."""
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    return get_expenses_between(user_id, start, end), start, end


def get_expense(user_id: int, expense_id: int) -> dict[str, Any] | None:
    with _lock:
        data = _load()
    for e in data["expenses"]:
        if e["id"] == expense_id and e["user_id"] == user_id:
            return e
    return None


def update_expense(
    user_id: int,
    expense_id: int,
    amount: float | None = None,
    category: str | None = None,
    description: str | None = None,
) -> dict[str, Any] | None:
    with _lock:
        data = _load()
        for e in data["expenses"]:
            if e["id"] == expense_id and e["user_id"] == user_id:
                if amount is not None:
                    e["amount"] = float(amount)
                if category is not None:
                    e["category"] = category
                if description is not None:
                    e["description"] = description
                _save(data)
                return e
    return None


def delete_expense(user_id: int, expense_id: int) -> bool:
    with _lock:
        data = _load()
        before = len(data["expenses"])
        data["expenses"] = [
            e for e in data["expenses"]
            if not (e["id"] == expense_id and e["user_id"] == user_id)
        ]
        removed = len(data["expenses"]) < before
        if removed:
            _save(data)
        return removed


# ---------------- Incomes ----------------

def add_income(user_id: int, amount: float, note: str = "") -> dict[str, Any]:
    with _lock:
        data = _load()
        income = {
            "id": data["next_income_id"],
            "user_id": user_id,
            "amount": float(amount),
            "note": note,
            "timestamp": datetime.utcnow().isoformat(),
        }
        data["next_income_id"] += 1
        data["incomes"].append(income)
        _save(data)
        return income


def get_incomes_between(user_id: int, start: datetime, end: datetime) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
    out = []
    for i in data["incomes"]:
        if i["user_id"] != user_id:
            continue
        try:
            ts = datetime.fromisoformat(i["timestamp"])
        except ValueError:
            continue
        if start <= ts < end:
            out.append(i)
    out.sort(key=lambda x: x["timestamp"])
    return out


def get_incomes_today(user_id: int) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day)
    end = start + timedelta(days=1)
    return get_incomes_between(user_id, start, end)


def get_incomes_last_n_days(user_id: int, days: int) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    end = datetime(now.year, now.month, now.day) + timedelta(days=1)
    start = end - timedelta(days=days)
    return get_incomes_between(user_id, start, end)


def get_incomes_current_month(user_id: int) -> tuple[list[dict[str, Any]], datetime, datetime]:
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    return get_incomes_between(user_id, start, end), start, end


def get_incomes_current_week(user_id: int) -> tuple[list[dict[str, Any]], datetime, datetime]:
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=7)
    return get_incomes_between(user_id, start, end), start, end


def get_incomes_previous_week(user_id: int) -> tuple[list[dict[str, Any]], datetime, datetime]:
    now = datetime.utcnow()
    today = datetime(now.year, now.month, now.day)
    this_monday = today - timedelta(days=today.weekday())
    prev_start = this_monday - timedelta(days=7)
    prev_end = this_monday
    return get_incomes_between(user_id, prev_start, prev_end), prev_start, prev_end


def delete_income(user_id: int, income_id: int) -> bool:
    with _lock:
        data = _load()
        before = len(data["incomes"])
        data["incomes"] = [
            i for i in data["incomes"]
            if not (i["id"] == income_id and i["user_id"] == user_id)
        ]
        removed = len(data["incomes"]) < before
        if removed:
            _save(data)
        return removed


# ---------------- Customers ----------------

def add_customer(
    user_id: int,
    name: str,
    latitude: float | None,
    longitude: float | None,
    address: str | None,
    notes: str | None,
) -> dict[str, Any]:
    with _lock:
        data = _load()
        customer = {
            "id": data["next_customer_id"],
            "user_id": user_id,
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat(),
        }
        data["next_customer_id"] += 1
        data["customers"].append(customer)
        _save(data)
        return customer


def list_customers(user_id: int) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
    return [c for c in data["customers"] if c["user_id"] == user_id]


def get_customer(user_id: int, customer_id: int) -> dict[str, Any] | None:
    for c in list_customers(user_id):
        if c["id"] == customer_id:
            return c
    return None


# ---------------- Users (for reminders) ----------------

def register_user(user_id: int, chat_id: int) -> None:
    """Add or update a user record so we can reach them with reminders."""
    with _lock:
        data = _load()
        for u in data["users"]:
            if u["user_id"] == user_id:
                u["chat_id"] = chat_id
                u["reminders_enabled"] = u.get("reminders_enabled", True)
                _save(data)
                return
        data["users"].append({
            "user_id": user_id,
            "chat_id": chat_id,
            "reminders_enabled": True,
            "registered_at": datetime.utcnow().isoformat(),
        })
        _save(data)


def list_users() -> list[dict[str, Any]]:
    with _lock:
        data = _load()
    return list(data.get("users", []))


def set_reminders_enabled(user_id: int, enabled: bool) -> bool:
    with _lock:
        data = _load()
        for u in data["users"]:
            if u["user_id"] == user_id:
                u["reminders_enabled"] = bool(enabled)
                _save(data)
                return True
    return False


# ---------------- Monthly budget ----------------

def set_budget(user_id: int, chat_id: int, amount: float) -> None:
    """Set (or replace) the monthly budget for a user. Resets alert tracking."""
    with _lock:
        data = _load()
        for u in data["users"]:
            if u["user_id"] == user_id:
                u["chat_id"] = chat_id
                u["budget"] = float(amount)
                u["budget_alerts_sent"] = {}
                _save(data)
                return
        data["users"].append({
            "user_id": user_id,
            "chat_id": chat_id,
            "reminders_enabled": True,
            "budget": float(amount),
            "budget_alerts_sent": {},
            "registered_at": datetime.utcnow().isoformat(),
        })
        _save(data)


def get_budget(user_id: int) -> float | None:
    with _lock:
        data = _load()
    for u in data["users"]:
        if u["user_id"] == user_id:
            b = u.get("budget")
            return float(b) if b is not None else None
    return None


def clear_budget(user_id: int) -> bool:
    with _lock:
        data = _load()
        for u in data["users"]:
            if u["user_id"] == user_id and u.get("budget") is not None:
                u["budget"] = None
                u["budget_alerts_sent"] = {}
                _save(data)
                return True
    return False


# ---------------- PIN lock ----------------

def set_pin(user_id: int, chat_id: int, pin_hash: str | None) -> None:
    """Set or clear the PIN hash for a user."""
    with _lock:
        data = _load()
        for u in data["users"]:
            if u["user_id"] == user_id:
                u["chat_id"] = chat_id
                u["pin_hash"] = pin_hash
                _save(data)
                return
        data["users"].append({
            "user_id": user_id,
            "chat_id": chat_id,
            "reminders_enabled": True,
            "pin_hash": pin_hash,
            "registered_at": datetime.utcnow().isoformat(),
        })
        _save(data)


def get_pin_hash(user_id: int) -> str | None:
    with _lock:
        data = _load()
    for u in data["users"]:
        if u["user_id"] == user_id:
            return u.get("pin_hash")
    return None


def mark_budget_alert(user_id: int, month_key: str, threshold: int) -> bool:
    """Record a threshold alert. Returns True if newly recorded (not already sent)."""
    with _lock:
        data = _load()
        for u in data["users"]:
            if u["user_id"] == user_id:
                alerts = u.setdefault("budget_alerts_sent", {})
                month_alerts = alerts.setdefault(month_key, [])
                if threshold in month_alerts:
                    return False
                month_alerts.append(threshold)
                _save(data)
                return True
    return False


def delete_customer(user_id: int, customer_id: int) -> bool:
    with _lock:
        data = _load()
        before = len(data["customers"])
        data["customers"] = [
            c for c in data["customers"]
            if not (c["id"] == customer_id and c["user_id"] == user_id)
        ]
        removed = len(data["customers"]) < before
        if removed:
            _save(data)
        return removed
