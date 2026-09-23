# SmartZakup — product spec (HackAlem AI 2026, case "Elektrokomplekt")

## 0. What we are building and how it will be judged

A web app for the purchasing manager of Elektrokomplekt LLP (ekt.kz, electrical products distributor, Almaty warehouse).
It calculates **recommended orders to suppliers** (Systeme Electric and IEK), shows **why** for every line,
lets the manager edit and **approve** lines, and **exports** the approved order for 1C.
**Nothing is ever sent to a supplier automatically.** Customer data must stay anonymous (the files contain none).

The jury will check these 5 things. The app (tab "✅ Проверка") and the automated tests must prove each one:

1. **Every input matters**: changing any input (e.g. goods in transit, stock, category, growth %) changes the result.
2. **Seasonality**: for a seasonal product the forecast follows the seasonal pattern, not a flat average.
3. **Stockouts**: for a product that was out of stock, the requirement is adjusted **up** vs. a calculation on raw sales.
4. **One-off orders**: a huge one-off order artificially added to the sales data does **not** significantly raise the recommended regular quantity.
5. **Explainability**: every output row has a reason; the list can be filtered by supplier.

Optional features we also cover: priority by stockout risk, supplier minimums/multiples, demand trends by category.
Deliverables: git repo + README (method, outlier algorithm, how to run).

## 1. Tech

- Python 3. Team laptops: one **Windows** (global python, no venv needed) and one **Mac** (global pip is blocked → use `./venv`, create with `python3 -m venv venv` if missing). Commands must work on both.
- UI: **Streamlit**. `app.py` holds the sidebar and the "📦 Заказ" tab; every other tab lives in its own file (see **INTERFACE.md**). All math in **`engine.py`** (pandas only, no Streamlit imports). Tests in `tests/`.
- Read Excel with `pd.read_excel(..., engine="calamine")` (package `python-calamine`, much faster); fall back to openpyxl if it fails.
- Cache parsed tables as parquet in `data/cache/` (rebuild when the source file is newer). Use `st.cache_data`.
- Charts: plotly. UI text, reasons and exports in **Russian**. Money in ₸ with thousand separators.
- Read all product codes and document numbers **as text** (`dtype=str`), strip spaces.

## 2. Data files (folder `data/`)

Product key everywhere = **1C code** (text like `030200201_`; a few look like `ATN000330` or `щт-0001952` — keep as is).

Month names in the monthly files: `янв. 2024, февр. 2024, март 2024, апр. 2024, май 2024, июнь 2024, июль 2024, авг. 2024, сент. 2024, окт. 2024, нояб. 2024, дек. 2024` … up to `сент. 2026`.

| File | Content | Layout |
|---|---|---|
| `se_sales_invoices.xlsx`, `iek_sales_invoices.xlsx` | Every sales invoice line | Header row 1: `Дата` (text `dd.mm.yyyy HH:MM:SS`), `Номер`, `Документ`, `Код` (1C code), `Номенклатура`, `Ед.`, `Склад`, `Количество`. Last row is a total `Итого`. |
| `se_sales_monthly.xlsx`, `iek_sales_monthly.xlsx` | Company's monthly sales report (units), Jan 2024 – Sep 2026 | Header row 1 (SE: `Номенклатура, Номенклатура.Код, Артикул, Кратность, <months>, Итого`; IEK: `Номенклатура, Номенклатура.Код, <months>, Итого`), row 2 = the word "Количество", data from row 3. Last row `Итого` (no code) — drop. |
| `se_stock_monthly.xlsx`, `iek_stock_monthly.xlsx` | Stock at the **start** of each month, Jan 2024 – Sep 2026 | SE: header row 1 `№, Номенклатура, Номенклатура.Код, Ед.изм, <months>`, rows 2–3 empty, data from row 4. IEK: header row 1 `Номенклатура, Ед., Номенклатура.Код, <months>, Итого`, rows 2–3 sub-headers, data from row 4, last row `Итого`. Empty = 0. |
| `se_manager_sheet.xlsx` | The SE purchasing manager's own working sheet (current stock, category, cost, in transit) | Row 1 empty, **header row 2**, data rows 3–499. Columns (strip spaces from names): `Артикул поставщика`, `Код 1с`, `Наименование`, `Категория 2026` (1/2/3/5/7), `СС реал` (unit cost ₸), monthly sales `Январь 2024 г.` … `Сентябрь 2026 г.`, `Витрина`, `Остаток ТЗ`, `РЦ ЕКТ  Рыскулова`, `Розничный склад`, `Остаток`, `Зарезервировано`, `Свободный остаток`, `Запас` (formula = months of cover), **`Заказ` (column BB, hidden and EMPTY — this is the column we fill)**, `СЭ в пути 24.09` (column BC, goods in transit arriving 24.09.2026; a few cells have comments like "20.10" = other arrival date). |
| `iek_in_transit.xlsx` | IEK goods in transit | Sheet `Лист4`, header row 1: `Код 1с`, `Артикул ИЭК`, ` Наименование`, then 6 order columns; each header contains the arrival date: `…(поступление до 10.10.2026)`. Parse it with a regex. Some codes appear more than once → sum. Cell comments contain notes like "замена …", "EOL", "под заказ". |
| `se_moq.xlsx` | SE order multiple | Header row 1: `№, Номенклатура, Номенклатура.Код, Артикул, Кратность`, row 2 empty. `Кратность` = order in multiples of this (5, 10, 20, …). |
| `iek_moq.xlsx` | IEK minimum shipment | Sheet `Лист7`: `№, Код 1с, Артикул поставщика, Наименование, Мин. разр. к отгр.` (treat as minimum AND multiple). The file has an external link to IEK's price list — ignore warnings. |
| `iek_catalog.xlsx` | **IEK price list** (extracted from a hidden cached copy inside `iek_moq.xlsx`) | `Код 1с, Артикул, Наименование, Категория, Группа, Подгруппа, ПодПодгруппа, Ед., Статус IEK, Кратность, Мин. отгрузка, Цена IEK, тенге с НДС`. Статус IEK: `Обязательный запас`, `Заказная` (made to order), `Регулярная`, `Новинка` (new), `Распродажа` (clearance / being discontinued). |
| `se_seasonality.xlsx`, `iek_seasonality.xlsx` | Company's seasonality, in **tenge**, by year and month | Row 3: `год, янв … дек, ИТОГО`; rows 4–6 = 2024, 2025, 2026. Use only full years 2024 and 2025. |

## 3. Data traps (must handle — most teams will miss these)

1. Invoices end with an `Итого` total row (6.8 M units for SE). Drop rows where `Дата` is not a date.
2. Invoices contain non-sales documents: keep only `Документ` starting with `Расходная накладная` (drop `Заказ покупателя`, `Приходная накладная`).
3. Old invoice rows (2023–2024) have **negative** quantities, 2025–2026 positive. Use only rows from **2025-01-01**, quantity = absolute value.
4. Data ends on **22.09.2026** → September 2026 is a partial month (22 days). Never treat it as a full month (the company's seasonality sheet shows a fake September drop because of this).
5. Monthly sales files have some negative months (returns) → clip to 0.
6. Units differ: `шт`, `м`, `упак`. Six IEK cables are **bought in 305 m coils but sold by the meter** (name contains `БУХТ` / `305м`) → order in coils.
7. Pack sizes: 485 of 554 SE products have `Кратность` > 1; 684 IEK products have minimum shipment > 1 → round up.
8. SE stock is split: available = `Свободный остаток` + `Остаток ТЗ` + `Розничный склад` + `Витрина` (exactly the manager's own `Запас` formula). `Зарезервировано` is already excluded from `Свободный остаток`.
9. Money ≠ units: seasonality files are in tenge (prices changed). IEK Jan–Aug 2026 vs 2025: +3% in tenge but −15% in units. Always measure growth in **units**.
10. For SE the company's monthly sales report is ~2× lower than the invoices (big bulk invoices seem excluded, e.g. boxes IMT35101 in Mar 2025: 15 620 in the report vs 58 857 in invoices). For IEK they match. → Setting "Источник спроса" (see 4.0).
11. SE `Категория 2026` looks like ABC classes: 1 = fast (~1 230 units/month), 2 = ~80, 3 = ~10, 5 = 11 products (~500/month), 7 = not selling. Names containing `!!!` look discontinued.

## 4. Calculation (engine.py) — per supplier, per product

### 4.0 Settings (sidebar, with defaults)
- Дата расчёта (today): 22.09.2026 (= last date in invoices).
- Источник спроса: **"Накладные (автоочистка разовых заказов)"** (default) or "Ежемесячный отчёт компании".
- Per supplier: lead time L (days): **IEK 35** (orders from Russia take 35–40 days in the in-transit file; local 12–24), **SE 30**; review period R (days until next order): **IEK 14, SE 30**.
- Service level by class: A 95% (z=1.65), B 90% (z=1.28), C 80% (z=0.84).
- План роста продаж, % (manager's growth forecast): default 0.

### 4.1 Regular demand history (monthly, units)
- Invoice mode: monthly sums of invoice lines from 2025-01 to 2026-08 (full months), **after removing one-off lines**:
  a line is **one-off** if the product has ≥ 10 invoice lines since 2025-01-01 AND `qty > 20 × median line qty of that product` AND `qty > 0.5 × median monthly volume of that product`.
  Keep a table of all one-off lines (date, document number, product, qty, typical line qty) — shown in the UI and used in reasons.
- Months before 2025 (for seasonality only) come from the monthly sales file.
- Monthly-report mode: use the monthly sales file for all months (no line-level filter; the trimmed mean in 4.4 still protects against spikes).

### 4.2 Seasonal factors (12 numbers per product, average = 1)
Hierarchy:
1. **Supplier level**: sum all products per month; for each full year (2024 from the monthly file, 2025 from the demand source) divide each month by that year's monthly average; average the years. Then average 50/50 with the factors from the company's seasonality file (full years 2024 and 2025 only).
2. **Category level** (IEK: `Категория` from `iek_catalog.xlsx`; SE: product series = text in quotes in the name, e.g. "ATLAS", "BLANCA", "Wessen 59"): same method, used if the group has ≥ 10 products, otherwise supplier level.
3. **Product's own factors** if they are real: the product sold ≥ 60 units in each year AND the 2024 and 2025 monthly shapes correlate ≥ 0.5 → final = 0.6 × own + 0.4 × category. Otherwise use category factors.
Clip factors to [0.3, 3.0] and re-normalize to average 1. Remember which level was used (for the reason text).

### 4.3 Stockouts → lost demand
- A month is a **stockout month** if (stock at the start of the month ≤ 0 OR stock at the start of the next month ≤ 0) AND sales that month < 70% of expected.
- Expected = preliminary base × seasonal factor; preliminary base = median of (monthly demand ÷ seasonal factor) over the last 12 full months that did NOT start with zero stock (if fewer than 3 such months, use all 12).
- Adjusted demand for a stockout month = expected. Lost units = expected − actual. Keep a table of stockout months.
- Must be switchable off via an override (used by check 3 to show "with vs without").

### 4.4 Base level, trend, forecast
- De-seasonalize each month: value ÷ seasonal factor.
- **Base** = trimmed mean of the last 6 full months (Mar–Aug 2026): drop the highest and lowest month, average the other 4 (if fewer than 4 months of history, plain average). This makes a single spike harmless.
- **Trend g** = (trimmed sum of last 6 full months) ÷ (trimmed sum of the same 6 months a year earlier) − 1, only if both ≥ 30 units; clip to [−40%, +60%]; else 0.
- **Forecast** for a future month M: `F(M) = base × season(M) × (1+g)^(t/12) × (1 + plan growth %)`, where t = months from the middle of the base window (≈ 1 June 2026) to M.
- Robust variability: σ = max(1.4826 × MAD of the last 12 de-seasonalized months, 0.2 × base). Never use plain std (one spike would blow up safety stock).

### 4.5 Stock position
- **SE**: available now = from `se_manager_sheet.xlsx` (trap 8). In transit = `СЭ в пути 24.09` (arrives 24.09.2026, or the date in the cell comment).
- **IEK**: no current stock file → available now = stock at 1 Sep 2026 (`сент. 2026` in the stock file) − regular (non-one-off) invoice sales 1–22 Sep 2026, minimum 0. If a one-off line happened in September, mention it in the reason ("если отгружено со склада — проверьте остаток в 1С"). In transit = sum of the 6 order columns, each with its arrival date.
- SE products missing from the manager sheet: same method as IEK.

### 4.6 Order quantity
- Effective lead time: IEK `Заказная` status → L × 1.5.
- Coverage window = from today to today + L + R. Window demand = sum over the days of F(month)/days_in_month.
- Safety stock = z(class) × σ × √((L+R)/30). Class: SE from `Категория 2026` (1→A, 2→B, 3→C, 5→B); IEK: ABC by last-12-months regular sales value (units × catalog price; units if no price): top 80% of value = A, next 15% = B, rest = C.
- Need = window demand + safety stock. Raw qty = max(0, Need − available − in transit).
- Rounding: multiple = SE `Кратность` / IEK `Мин. разр. к отгр.` (fallback catalog `Мин. отгрузка`, else 1): qty = ceil(raw / multiple) × multiple.
- Coils (IEK cables, trap 6): multiple = 305 m; show "N бухт (N×305 м)".

### 4.7 Do-not-reorder rules (qty = 0, reason explains, manager can override)
- SE `Категория 2026` = 7 or name contains `!!!` → "не продаётся / помечен !!! — вероятно выводится".
- IEK `Статус IEK` = `Распродажа` → "IEK выводит товар (распродажа)".
- No regular sales in the last 6 months and no stock problem → "нет продаж 6 мес".
- IEK `Новинка` with < 3 months of sales → calculate from what exists and flag "новинка — проверьте вручную".

### 4.8 Urgency and priority
- Daily demand d = window demand / (L+R). "Хватит до" date = today + (available + in transit) / d.
- 🔴 **Критично**: available + in transit < d × L (will run out before a new order can arrive).
- 🟡 **Заказать**: qty > 0.  🟢 **Не требуется**: qty = 0.
- Sort: 🔴 first, then 🟡, then by money at risk (d × price).
- Price: IEK = catalog price (list price, with VAT); SE = `СС реал` (cost). Line value = qty × price.

### 4.9 Reason text (every row, Russian, short, only the parts that apply)
Example:
> Регулярный спрос ≈ 310 шт/мес (мар–авг 2026, без лучшего и худшего месяца). Исключён разовый заказ 1 214 шт (накл. 20000038355 от 15.04.2026, обычно 4 шт). В мае 2026 был дефицит: продано 12 вместо ~95 — учтено 95. Сезонность: окт ×1.24, ноя ×1.04 (сезонность категории). Тренд −15% к прошлому году. Нужно на 49 дн. (поставка 35 + до следующего заказа 14): 520 шт + страховой запас 90 шт. Есть 350 шт, в пути 400 шт (до 10.10.2026). Округлено до кратности 10.

For qty = 0: "Запаса хватит до 28.11.2026 — заказ не нужен."

### 4.10 Engine API
The exact contract (function names, `Settings` fields, `plan_df` columns, `details` keys, `overrides`) is in **INTERFACE.md**. Follow it exactly: the two teammates build against it at the same time.

## 5. App screens (app.py + one file per extra tab, see INTERFACE.md)

- **Sidebar "Настройки"**: all settings from 4.0. Banner at top of the page: "Заказ не отправляется поставщику без утверждения ответственного сотрудника".
- **Tab "📦 Заказ"**: filters (Поставщик: Все / Systeme Electric / IEK; Срочность; Категория; поиск). KPI cards per supplier (позиций к заказу, сумма ₸, критичных). Table grouped/sorted by supplier and priority with columns: Поставщик, Код 1С, Артикул, Наименование, Класс, Срочность, Кол-во (editable), Ед., Кратность, Сумма ₸, Хватит до, Почему, ✔ Утвердить (checkbox). "Утвердить всё видимое" button, "Утвердил" name field. Download button "Заказ для 1С (Excel)".
- **Tab "✅ Проверка"** (the judges' 5 checks, each with ✅/❌ and before → after numbers, plus "Запустить все проверки"):
  1. Товар в пути: pick product (default: an urgent one), change in-transit qty → recommendation before → after.
  2. Сезонность: pick product (default: the most seasonal one, e.g. IEK 280300035_) → chart: history 2024–2026 + forecast next 12 months, factors table. Pass if forecast max/min ≥ 1.3 and it is not flat.
  3. Дефицит: pick product (default: most stockout months, e.g. IEK 130200032_) → qty with vs without lost-demand adjustment; chart raw vs adjusted. Pass if with > without.
  4. Разовый заказ: pick product; "Добавить фиктивный разовый заказ" of N units (default 20 × monthly demand, dated the 15th of the last full month) → recompute → change %. Pass if increase < 10% (after rounding to multiple).
  5. Объяснения: pass if every row has a non-empty reason and the supplier filter returns only that supplier (show counts).
- **Tab "📊 Аналитика"**: money KPIs (excess stock value = stock above 3 months of forecast × price; lost sales last 12 months = lost units × price; number of one-off orders found); demand trend by category (monthly, units, line chart with selector); tables: one-off orders, stockout months; product forecast chart (raw vs cleaned vs forecast).
- **Tab "🤖 AI помощник"** (phase 4): chat about the plan; "Объяснить проще" button for a row.

## 6. Exports

1. **Заказ для 1С (Excel)**: only approved rows; one sheet per supplier; columns: Код 1С, Артикул, Наименование, Количество, Ед., Цена, Сумма, Срочность, Почему; header lines "Поставщик", "Утвердил", "Дата". Also CSV (UTF-8 with BOM, `;` separator).
2. **Лист менеджера SE с заполненной колонкой «Заказ»** (function `fill_manager_sheet` in `export_manager_sheet.py`): open `data/se_manager_sheet.xlsx` with openpyxl (keep formulas), write the qty into column **BB "Заказ"** for each row by matching `Код 1с` (column C), unhide column BB, add a "Почему" column after the last used column, save to a new file for download. The manager's own `Запас` formula (column BA) then automatically includes our order.

## 7. Tests (`tests/test_acceptance.py`, pytest, use the real data + overrides)

- `test_in_transit_changes_result` — product with qty > 0; add in-transit = qty → new qty < old qty.
- `test_every_input_matters` — changing stock, class/category, growth %, lead time each changes the result for some product.
- `test_seasonality` — a synthetic product with a December peak (3× other months) in 2024 and 2025 → forecast(Dec) / forecast(Jun) ≥ 1.8; and real IEK 280300035_ forecast is not flat.
- `test_stockout_raises_requirement` — product with stockout months: qty with adjustment > qty without.
- `test_one_off_order_ignored` — active product; add a fake invoice line of 50 × its monthly demand (dated in the last full month, and separately in September 2026) → qty increases < 10% (+ one multiple).
- `test_every_row_explained_and_filterable`.

## 8. README.md (Russian, short English summary at top)
Problem → what the app does → **method** (4.1–4.9 in plain words, including the one-off filter and the stockout logic) → assumptions (section 10) → how to run on Windows and Mac (`pip install -r requirements.txt`; the case data is already in `data/`; `streamlit run app.py`; `pytest -q`) → screenshots → how we used Codex (two teammates, parallel Codex sessions, shared INTERFACE.md contract).

## 9. Work plan (two people in parallel — do ONLY the step you are asked for)
- **Person 1 — step 1**: `engine.py` (sections 2–4, exactly per INTERFACE.md) + `app.py` (sidebar, "📦 Заказ" tab, 1C export 6.1, placeholders for the other tabs).
- **Person 2 — step 1** (at the same time): `engine_stub.py` (temporary fake engine with the INTERFACE.md shapes), `tab_checks.py` ("✅ Проверка"), `tab_analytics.py` ("📊 Аналитика"), `export_manager_sheet.py` (6.2), `tests/test_acceptance.py` (section 7), `app_preview.py` (shows these tabs with the stub).
- **Person 1 — step 2 (merge)**: connect Person 2's files to the real engine, all tests green, all 5 checks ✅, delete the stub and preview.
- **Person 2 — step 2**: `tab_ai.py` — "🤖 AI помощник" using OpenAI API (`OPENAI_API_KEY` in `.env`, model in `OPENAI_MODEL`, default a small fast current model). Function calling with tools defined in tab_ai.py on top of the engine: `get_product(code)`, `top_urgent(supplier, n)`, `what_if(code, in_transit=None, lead_time_days=None, plan_growth_pct=None)` (calls `engine.build_plan` with overrides/settings). Quantities always come from the engine, never invented by the model. Works without a key (friendly message).
- **Person 1 — step 3** (at the same time): `README.md` (section 8).
- **Person 1 — step 4 (final)**: connect `tab_ai.py`, final checks, demo script.

## 10. Assumptions / questions for Elektrokomplekt (list in README)
1. SE monthly sales report ≈ half of the invoices (bulk invoices excluded?). Which one is "regular demand"? → switch in settings.
2. Real lead times and order frequency per supplier (defaults: IEK 35/14 days, SE 30/30).
3. No current IEK stock file → estimated from stock on 1 Sep 2026 − September sales.
4. Meaning of SE categories 5 and 7 and of "!!!" in names (we treat 7 and !!! as "do not reorder").

## 11. Demo examples (verified in the data)
- One-off orders: IEK `010300006_` УЗО АД12 — 1 214 pcs on 15.04.2026 (usual line 4); IEK `010500008_` ВА47-29 25А — 7 488 pcs on 02.09.2026 (usual 12); SE "ХИТ" S253 — 4 080 pcs on 26.03.2025 (usual 60, marked "!!!").
- Stockouts: IEK `130200032_` Розетка на DIN-рейку РАр10-3-ОП — 7 months started with zero stock in 2025–26. Across IEK ≈ 440 of ~1 050 regularly selling products had at least one such month; sales in those months ≈ ⅓ of normal.
- Seasonal: IEK `280300035_` Лоток перфорированный 100х300 (peaks in April both years), IEK `130300535_` Крюк КМ-1800 (April), SE `300200327_` Розетка 4-ная BLANCA (September).
- Overstock: 168 SE products have > 6 months of stock (≈ 24 M ₸ above a 3-month level, at cost).
- Bug in the manager's sheet: "Сумма последние 12 мес" (column AP) sums 13 months (Sep 2025 – Sep 2026).
