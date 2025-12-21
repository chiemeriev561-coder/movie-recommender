"""Sales tracker - Expense model and helpers

Features implemented:
- `Expense` class with type hints and validation using `decimal.Decimal`
- Flexible date parsing (defaults to today)
- Category enum and normalization helper
- Serialization: `to_dict`, `from_dict`, `save_to_json`, `load_from_json`
- Utility methods: `update`, `matches`, `formatted`
- Aggregation helpers: `total_by_category`, `filter_by_date_range`
- Equality and ordering (`__eq__`, `__lt__`)
- A small demo in the `__main__` block
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Any, Dict, Iterable, List
import json
import os
import csv
import tempfile
from pathlib import Path
from collections import defaultdict
import re


class Category(Enum):
    FOOD = "Food"
    TRANSPORT = "Transport"
    UTILITIES = "Utilities"
    ENTERTAINMENT = "Entertainment"
    OTHER = "Other"


def normalize_category(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    val = value.strip()
    if not val:
        return None
    # Try to match to enum (case-insensitive, allow spaces/underscores)
    key = re.sub(r"[\s_-]+", "", val).upper()
    for cat in Category:
        if re.sub(r"[\s_-]+", "", cat.name).upper() == key or cat.value.upper() == val.upper():
            return cat.value
    # Fallback: title-case string
    return val.title()


def _parse_date(value: Any) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        v = value.strip()
        # try iso
        try:
            return date.fromisoformat(v)
        except Exception:
            pass
        # try common formats
        fmts = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]
        for fmt in fmts:
            try:
                return datetime.strptime(v, fmt).date()
            except Exception:
                continue
    raise ValueError(f"Unrecognized date format: {value!r}")


@dataclass
class Expense:
    amount: Decimal = field(compare=False)
    description: str
    category: Optional[str] = None
    date: date = field(default_factory=date.today)
    notes: Optional[str] = None

    def __post_init__(self):
        # Normalize and validate amount
        if not isinstance(self.amount, Decimal):
            try:
                # Convert floats via str to avoid binary issues
                if isinstance(self.amount, float):
                    self.amount = Decimal(str(self.amount))
                else:
                    self.amount = Decimal(self.amount)
            except (InvalidOperation, TypeError) as exc:
                raise ValueError(f"Invalid amount: {self.amount!r}") from exc
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")

        # Description must be non-empty
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Description must be a non-empty string")
        self.description = self.description.strip()

        # Normalize category
        self.category = normalize_category(self.category)

        # Parse/normalize date
        self.date = _parse_date(self.date)

        # Normalize notes
        if self.notes is not None:
            self.notes = str(self.notes).strip() or None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": str(self.amount),
            "description": self.description,
            "category": self.category,
            "date": self.date.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Expense":
        return cls(
            amount=Decimal(str(data.get("amount"))),
            description=data.get("description", ""),
            category=data.get("category"),
            date=_parse_date(data.get("date")),
            notes=data.get("notes"),
        )

    def update(self, **kwargs) -> None:
        # Update supported fields then re-run validations
        for key in ("amount", "description", "category", "date", "notes"):
            if key in kwargs:
                setattr(self, key, kwargs[key])
        self.__post_init__()

    def matches(self, query: str) -> bool:
        q = str(query).lower().strip()
        if not q:
            return False
        if q in str(self.amount):
            return True
        if q in self.description.lower():
            return True
        if self.category and q in self.category.lower():
            return True
        if self.notes and q in self.notes.lower():
            return True
        return False

    def formatted(self) -> str:
        cat = self.category or "Uncategorized"
        notes = f" — {self.notes}" if self.notes else ""
        return f"{self.date.isoformat()} | {cat:12} | ${self.amount:>8} | {self.description}{notes}"

    def __repr__(self) -> str:
        return f"Expense(amount={self.amount!r}, description={self.description!r}, category={self.category!r}, date={self.date!r}, notes={self.notes!r})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Expense):
            return NotImplemented
        return (
            self.amount == other.amount
            and self.description == other.description
            and self.category == other.category
            and self.date == other.date
            and self.notes == other.notes
        )

    def __lt__(self, other: "Expense") -> bool:
        # Sort by date, then amount, then description (case-insensitive)
        if not isinstance(other, Expense):
            return NotImplemented
        return (self.date, self.amount, self.description.lower()) < (other.date, other.amount, other.description.lower())


# Serialization helpers

def save_to_json(path: str, expenses: Iterable[Expense]) -> None:
    """Write JSON atomically to avoid partial files on error."""
    data = [e.to_dict() for e in expenses]
    p = Path(path)
    # Ensure parent exists
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file in same directory then atomically replace
    if p.suffix:
        tmp = p.with_suffix(p.suffix + ".tmp")
    else:
        tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(p))


def load_from_json(path: str) -> List[Expense]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Expense.from_dict(item) for item in data]


# Aggregation / filtering helpers

def total_by_category(expenses: Iterable[Expense]) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for e in expenses:
        key = e.category or "Other"
        totals[key] += e.amount
    return dict(totals)


def filter_by_date_range(expenses: Iterable[Expense], start: Optional[date] = None, end: Optional[date] = None) -> List[Expense]:
    if start is None:
        start = date.min
    if end is None:
        end = date.max
    return [e for e in expenses if start <= e.date <= end]


# ---------- ExpenseManager: centralizes operations and caches sorted list ----------
class ExpenseManager:
    def __init__(self, expenses: Optional[List[Expense]] = None):
        self.expenses: List[Expense] = list(expenses) if expenses else []
        self._sorted_cache: Optional[List[Expense]] = None

    # internal: invalidate cache on modifications
    def _invalidate(self):
        self._sorted_cache = None

    def add(self, expense: Expense) -> None:
        self.expenses.append(expense)
        self._invalidate()

    def remove(self, expense: Expense) -> None:
        self.expenses.remove(expense)
        self._invalidate()

    def update(self, index: int, **kwargs) -> bool:
        ordlist = self.list_sorted()
        if index < 0 or index >= len(ordlist):
            return False
        e = ordlist[index]
        e.update(**kwargs)
        self._invalidate()
        return True

    def list_sorted(self) -> List[Expense]:
        if self._sorted_cache is None:
            # Use a deterministic key to avoid hidden sorting bugs
            self._sorted_cache = sorted(self.expenses, key=lambda e: (e.date, e.amount, e.description.lower()))
        return self._sorted_cache

    def find_by_index(self, display_index: int) -> Optional[Expense]:
        # display_index is 1-based (user-facing); convert to 0-based
        idx = display_index - 1
        ordlist = self.list_sorted()
        if 0 <= idx < len(ordlist):
            return ordlist[idx]
        return None

    def search(self, query: str) -> List[Expense]:
        q = query.lower().strip()
        if not q:
            return []
        found = [e for e in self.expenses if e.matches(q)]
        found.sort(key=lambda x: (x.rating if hasattr(x, 'rating') else 0, x.box_office_millions if hasattr(x, 'box_office_millions') else 0), reverse=True)
        return found

    def totals_by_category(self) -> Dict[str, Decimal]:
        return total_by_category(self.expenses)

    def to_list(self) -> List[Expense]:
        return list(self.expenses)

    def clear(self) -> None:
        self.expenses.clear()
        self._invalidate()


def clear_screen() -> None:
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass


def _prompt_nonempty(prompt: str, default: Optional[str] = None) -> str:
    while True:
        inp = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
        if not inp and default is not None:
            return default
        if inp:
            return inp
        print("Please enter a non-empty value.")


def _prompt_decimal(prompt: str, default: Optional[Decimal] = None) -> Decimal:
    while True:
        inp = input(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not inp and default is not None:
            return default
        try:
            # Use Decimal(str()) to avoid float imprecision
            val = Decimal(inp)
            if val < 0:
                raise ValueError
            return val
        except Exception:
            print("Invalid amount. Enter a non-negative number (e.g., 12.50).")


def _prompt_date(prompt: str, default: Optional[date] = None) -> date:
    while True:
        inp = input(f"{prompt}" + (f" [{default.isoformat()}]" if default else "") + ": ").strip()
        if not inp and default is not None:
            return default
        try:
            return _parse_date(inp)
        except Exception as e:
            print("Unrecognized date format. Try YYYY-MM-DD or DD/MM/YYYY or leave blank for today.")


def create_expense_interactive() -> Expense:
    print("\nAdd a new expense:")
    amount = _prompt_decimal("Amount")
    description = _prompt_nonempty("Description")
    category = input("Category (e.g., Food, Transport) [leave blank for Other]: ").strip() or None
    dt = _prompt_date("Date (YYYY-MM-DD or similar) [leave blank for today]", default=date.today())
    notes = input("Notes (optional): ").strip() or None
    return Expense(amount=amount, description=description, category=category, date=dt, notes=notes)


def list_expenses(manager: 'ExpenseManager') -> None:
    expenses = manager.list_sorted()
    if not expenses:
        print("No expenses recorded.")
        return
    print("\nNo. | Date       | Category     | Amount    | Description")
    print("----+------------+--------------+-----------+---------------------")
    for idx, e in enumerate(expenses, start=1):
        print(f"{idx:3d} | {e.date.isoformat()} | { (e.category or 'Other')[:12]:12} | ${e.amount:>8} | {e.description}")


def view_expense(manager: 'ExpenseManager') -> None:
    if not manager.expenses:
        print("No expenses to view.")
        return
    try:
        choice = int(input("Enter expense number to view (see List): ").strip())
        e = manager.find_by_index(choice)
        if e is None:
            raise IndexError
        print("\n", e)
        print("Formatted:", e.formatted())
    except Exception:
        print("Invalid number.")


def edit_expense(manager: 'ExpenseManager') -> bool:
    if not manager.expenses:
        print("No expenses to edit.")
        return False
    try:
        choice = int(input("Enter expense number to edit (see List): ").strip())
        e = manager.find_by_index(choice)
        if e is None:
            raise IndexError
    except Exception:
        print("Invalid number.")
        return False
    print("Leave blank to keep current value.")
    new_amt = input(f"Amount [{e.amount}]: ").strip()
    new_desc = input(f"Description [{e.description}]: ").strip()
    new_cat = input(f"Category [{e.category or 'Other'}]: ").strip()
    new_date = input(f"Date [{e.date.isoformat()}]: ").strip()
    new_notes = input(f"Notes [{e.notes or ''}]: ").strip()
    upd = {}
    if new_amt:
        try:
            upd['amount'] = Decimal(new_amt)
        except Exception:
            print("Invalid amount entered; edit aborted.")
            return False
    if new_desc:
        upd['description'] = new_desc
    if new_cat:
        upd['category'] = new_cat
    if new_date:
        try:
            upd['date'] = _parse_date(new_date)
        except Exception:
            print("Invalid date entered; edit aborted.")
            return False
    if new_notes:
        upd['notes'] = new_notes
    # Apply update via manager
    manager.update(choice - 1, **upd)
    print("Expense updated.")
    return True

def delete_expense(manager: 'ExpenseManager') -> bool:
    if not manager.expenses:
        print("No expenses to delete.")
        return False
    try:
        choice = int(input("Enter expense number to delete (see List): ").strip())
        e = manager.find_by_index(choice)
        if e is None:
            raise IndexError
    except Exception:
        print("Invalid number.")
        return False
    confirm = input(f"Delete {e.description} (${e.amount}) on {e.date.isoformat()}? [y/N]: ").strip().lower()
    if confirm == 'y':
        manager.remove(e)
        print("Deleted.")
        return True
    print("Delete cancelled.")
    return False

def search_expenses(manager: 'ExpenseManager') -> None:
    q = input("Enter search term: ").strip()
    if not q:
        print("Empty query.")
        return
    found = manager.search(q)
    if not found:
        print("No matching expenses.")
        return
    print(f"Found {len(found)} result(s):")
    for e in found:
        print(e.formatted())


def _try_save_with_fallback(expenses: List[Expense], candidates: List[Path]) -> tuple[Path, List[tuple[Path, Exception]]]:
    """Try to save to each candidate path until one succeeds; return the successful Path and list of failures."""
    failures: List[tuple[Path, Exception]] = []
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            save_to_json(str(p), expenses)
            return p, failures
        except Exception as e:
            # Collect failure silently, try next location
            failures.append((p, e))
            continue
    # No candidate worked — raise the last error for the caller to handle
    if failures:
        raise failures[-1][1]
    raise OSError("Failed to save to any candidate location")


def save_prompt(expenses: List[Expense]) -> bool:
    if not expenses:
        print("No expenses to save.")
        return False
    default = Path.home() / ".sales_tracker" / "expenses.json"
    user_in = input(f"Enter filename to save [{default}]: ").strip()
    user_path = Path(user_in) if user_in else default

    candidates = [
        user_path,
        Path.home() / ".sales_tracker" / "expenses.json",
        Path.home() / "Documents" / "expenses.json",
        Path.cwd() / "expenses.json",
        Path(tempfile.gettempdir()) / "expenses.json",
    ]

    try:
        saved_path, failures = _try_save_with_fallback(expenses, candidates)
        if failures:
            failed_list = ", ".join(str(p.resolve()) for p, _ in failures)
            print(f"Saved {len(expenses)} expenses to {saved_path.resolve()} (note: could not write to: {failed_list})")
        else:
            print(f"Saved {len(expenses)} expenses to {saved_path.resolve()}")
        return True
    except PermissionError:
        print("Permission denied when saving. Try a different folder or run with appropriate permissions.")
        return False
    except Exception as exc:
        print("Failed to save. Last error:", type(exc).__name__, exc)
        print("Try specifying a different path (e.g., a folder you can write to).")
        return False


def load_prompt() -> List[Expense]:
    default = str(Path.home() / ".sales_tracker" / "expenses.json")
    path = input(f"Enter filename to load [{default}]: ").strip() or default
    p = Path(path)
    if not p.exists():
        print("File not found.")
        return []
    try:
        loaded = load_from_json(path)
        print(f"Loaded {len(loaded)} expenses from {path}")
        return loaded
    except Exception as exc:
        print("Error loading file:", exc)
        return []


def export_csv(expenses: List[Expense]) -> None:
    if not expenses:
        print("No expenses to export.")
        return
    default = Path.home() / ".sales_tracker" / "expenses_export.csv"
    user_in = input(f"Enter CSV filename [{default}]: ").strip()
    user_path = Path(user_in) if user_in else default

    candidates = [
        user_path,
        Path.home() / ".sales_tracker" / "expenses_export.csv",
        Path.home() / "Documents" / "expenses_export.csv",
        Path.cwd() / "expenses_export.csv",
        Path(tempfile.gettempdir()) / "expenses_export.csv",
    ]

    failures: List[tuple[Path, Exception]] = []
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["amount","description","category","date","notes"])
                for e in expenses:
                    writer.writerow([str(e.amount), e.description, e.category or '', e.date.isoformat(), e.notes or ''])
            if failures:
                failed_list = ", ".join(str(fp.resolve()) for fp, _ in failures)
                print(f"Exported to {p.resolve()} (note: could not write to: {failed_list})")
            else:
                print(f"Exported to {p.resolve()}")
            return
        except Exception as e:
            failures.append((p, e))
            continue

    # all attempts failed
    last = failures[-1][1] if failures else None
    print("Failed to export CSV. Last error:", type(last).__name__ if last else "Unknown", last)
    print("Try specifying a different path or running the app with appropriate permissions.")

def totals_menu(manager: 'ExpenseManager') -> None:
    totals = manager.totals_by_category()
    if not totals:
        print("No expenses to summarize.")
        return
    print("Totals by category:")
    for k, v in totals.items():
        print(f"{k}: ${v}")


def main_menu() -> None:
    manager = ExpenseManager()
    unsaved = False

    # Silent auto-load from per-user app folder (~/.sales_tracker/expenses.json).
    # If an older file exists in Documents, migrate it into the app folder.
    default_dir = Path.home() / ".sales_tracker"
    default_path = default_dir / "expenses.json"
    docs_path = Path.home() / "Documents" / "expenses.json"

    if default_path.exists():
        try:
            loaded = load_from_json(str(default_path))
            if loaded:
                manager = ExpenseManager(loaded)
                unsaved = False
                print(f"Loaded {len(manager.expenses)} expenses from {default_path.resolve()}")
        except Exception as exc:
            print("Failed to auto-load saved expenses:", exc)
    elif docs_path.exists():
        # migrate from Documents to the hidden app folder
        try:
            loaded = load_from_json(str(docs_path))
            if loaded:
                default_dir.mkdir(parents=True, exist_ok=True)
                save_to_json(str(default_path), loaded)
                manager = ExpenseManager(loaded)
                unsaved = False
                print(f"Loaded {len(manager.expenses)} expenses from {docs_path.resolve()} and migrated to {default_path.resolve()}")
        except Exception as exc:
            print("Failed to auto-load/migrate saved expenses:", exc)

    while True:
        print("\n--- Expenses Menu ---")
        print("1) Add expense")
        print("2) List expenses")
        print("3) View expense")
        print("4) Edit expense")
        print("5) Delete expense")
        print("6) Search")
        print("7) Filter by date range")
        print("8) Totals by category")
        print("9) Load from JSON")
        print("10) Save to JSON")
        print("11) Export CSV")
        print("0) Quit")
        choice = input("Choice: ").strip()
        if choice == '1':
            e = create_expense_interactive()
            manager.add(e)
            unsaved = True
            print("Expense added.")
        elif choice == '2':
            list_expenses(manager)
        elif choice == '3':
            view_expense(manager)
        elif choice == '4':
            if edit_expense(manager):
                unsaved = True
        elif choice == '5':
            if delete_expense(manager):
                unsaved = True
        elif choice == '6':
            search_expenses(manager)
        elif choice == '7':
            start = input("Start date (leave blank for earliest): ").strip()
            end = input("End date (leave blank for latest): ").strip()
            try:
                s = _parse_date(start) if start else None
                e = _parse_date(end) if end else None
                out = filter_by_date_range(manager.expenses, start=s, end=e)
                for it in out:
                    print(it.formatted())
            except Exception:
                print("Invalid date(s).")
        elif choice == '8':
            totals_menu(manager)
        elif choice == '9':
            if unsaved:
                confirm = input("Unsaved changes will be lost. Continue? [y/N]: ").strip().lower()
                if confirm != 'y':
                    continue
            loaded = load_prompt()
            if loaded:
                manager = ExpenseManager(loaded)
                unsaved = False
        elif choice == '10':
            if save_prompt(manager.expenses):
                unsaved = False
        elif choice == '11':
            export_csv(manager.expenses)
        elif choice == '0':
            if unsaved:
                confirm = input("You have unsaved changes. Save before exit? [y/N]: ").strip().lower()
                if confirm == 'y':
                    if save_prompt(manager.expenses):
                        print("Saved. Goodbye.")
                        break
                    else:
                        print("Save failed; aborting exit.")
                        continue
                else:
                    print("Exiting without saving.")
                    break
            else:
                print("Goodbye.")
                break
        else:
            print("Invalid option.")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nInterrupted. Exiting.")
