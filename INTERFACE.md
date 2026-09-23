# INTERFACE.md — the contract between the two teammates

Person 1 builds `engine.py` + `app.py`. Person 2 builds the tab files against **this contract** at the same time.
Do not rename anything here. If a change is truly needed, update this file in the same commit and write why in `NOTES_FOR_TEAMMATE.md`.

## 1. engine.py

```python
from dataclasses import dataclass, field
from datetime import date
import pandas as pd

SUPPLIERS = ["Systeme Electric", "IEK"]

@dataclass
class Settings:
    today: date = date(2026, 9, 22)
    demand_source: str = "invoices"            # "invoices" | "monthly_report"
    lead_time_days: dict = field(default_factory=lambda: {"IEK": 35, "Systeme Electric": 30})
    review_days: dict = field(default_factory=lambda: {"IEK": 14, "Systeme Electric": 30})
    service_z: dict = field(default_factory=lambda: {"A": 1.65, "B": 1.28, "C": 0.84})
    plan_growth_pct: float = 0.0               # manager's growth plan in %, e.g. 10 = +10 %

def load_all(data_dir: str = "data") -> dict: ...
def build_plan(data: dict, settings: Settings, overrides: dict | None = None) -> tuple[pd.DataFrame, dict]: ...
```

### `load_all()` returns a dict of cleaned DataFrames
Tabs may rely on these keys and columns (engine may add more keys for itself):

| key | columns |
|---|---|
| `invoices` | supplier, date (datetime), doc (str), code (str), name, unit, qty (float > 0) — sales lines only, from 2025-01-01, traps from SPEC section 3 already handled |
| `sales_monthly` | supplier, code, month (`pd.Period`, freq "M"), qty |
| `stock_monthly` | supplier, code, month (`pd.Period`), stock_start |
| `in_transit` | supplier, code, qty, arrival_date (date) |
| `moq` | supplier, code, multiple (int ≥ 1) |
| `catalog` | supplier, code, article, name, category, unit, status, price |

### `build_plan()` returns `(plan_df, details)`

`plan_df` — one row per product, exactly these columns:

| column | type | meaning |
|---|---|---|
| supplier | str | "Systeme Electric" or "IEK" |
| code | str | 1C code, e.g. "010300006_" |
| article | str | supplier article |
| name | str | product name |
| category | str | IEK catalog category / SE product series |
| abc_class | str | "A" / "B" / "C" |
| unit | str | "шт", "м", "упак" |
| available | float | stock available now |
| in_transit | float | total in transit |
| next_arrival | date or None | earliest in-transit arrival |
| base_monthly | float | regular monthly demand (de-seasonalized) |
| trend | float | yearly trend, −0.15 = −15 % |
| window_days | int | lead time + review period |
| window_demand | float | forecast demand in the window |
| safety_stock | float | |
| raw_qty | float | before rounding |
| multiple | int | order multiple / minimum |
| qty | int | **final recommended order quantity** |
| urgency | str | "🔴 Критично" / "🟡 Заказать" / "🟢 Не требуется" |
| enough_until | date or None | when current stock + in transit runs out |
| price | float | ₸ per unit (IEK: catalog price; SE: cost "СС реал") |
| value | float | qty × price |
| do_not_reorder | bool | discontinued / clearance / no sales |
| reason | str | Russian explanation (SPEC 4.9) — never empty |

`details` — `dict[code] -> dict` with:

| key | content |
|---|---|
| "history" | DataFrame, index = month (`pd.Period`), columns: raw, cleaned (after one-off removal), adjusted (after stockout adjustment), stock_start |
| "season_factors" | list of 12 floats (Jan … Dec), mean = 1 |
| "season_level" | "product" / "category" / "supplier" |
| "forecast" | DataFrame, columns: month (`pd.Period`), forecast — next 12 months |
| "one_offs" | DataFrame, columns: date, doc, qty, typical_qty |
| "stockouts" | DataFrame, columns: month, actual, expected, lost |

### `overrides` (all keys optional) — used by the checks tab and the tests
```python
{
  "in_transit": {"010300006_": 500},          # replace in-transit qty for a product
  "stock": {"010300006_": 0},                 # replace available stock
  "extra_invoice_lines": [                    # add fake sales lines before the calculation
      {"supplier": "IEK", "code": "010300006_", "date": "2026-08-15", "qty": 5000}
  ],
  "disable_stockout_adjustment": False,
  "disable_one_off_filter": False,
  "abc_class": {"010300006_": "A"},
}
```

## 2. Tab files — each exposes ONE function that app.py calls inside its tab

| file | function | owner |
|---|---|---|
| `tab_checks.py` | `render_checks_tab(engine, data, settings, plan_df, details)` | Person 2 |
| `tab_analytics.py` | `render_analytics_tab(engine, data, settings, plan_df, details)` | Person 2 |
| `tab_ai.py` | `render_ai_tab(engine, data, settings, plan_df, details)` | Person 2 |
| `export_manager_sheet.py` | `fill_manager_sheet(template_path: str, plan_df) -> bytes` (xlsx file content) | Person 2 |

`engine` is the imported engine module, so a tab can call `engine.build_plan(data, settings, overrides=...)` itself.

## 3. app.py
Tabs in this order: "📦 Заказ", "✅ Проверка", "📊 Аналитика", "🤖 AI помощник".
For the last three, app.py imports the render function inside `try/except ImportError` and shows "Вкладка в разработке" if the file does not exist yet — so the app always runs, and a teammate's tab appears automatically once its file is pulled.
The "📦 Заказ" tab offers the manager-sheet download via `fill_manager_sheet` the same way (only if the file exists).

## 4. File ownership (prevents Git conflicts)
- **Person 1**: `engine.py`, `app.py`, `README.md`
- **Person 2**: `tab_checks.py`, `tab_analytics.py`, `tab_ai.py`, `export_manager_sheet.py`, `tests/`, `engine_stub.py`, `app_preview.py`
- Shared, change only when asked: `INTERFACE.md`, `SPEC.md`, `AGENTS.md`, `requirements.txt`, `.gitignore`
Never edit the other person's files. Need a change there? Write it in `NOTES_FOR_TEAMMATE.md`.
