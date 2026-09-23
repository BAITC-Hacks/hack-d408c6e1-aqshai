"""SmartZakup: real-data ordering, checks and analytics."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import math

import pandas as pd
import streamlit as st
import engine

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="SmartZakup", page_icon="📦", layout="wide")
st.html('<style>[class*="st-key-order_editor_"] button[aria-label="Download as CSV"] {display: none;}</style>')


@st.cache_data(show_spinner="Читаем и очищаем данные…")
def get_data(source_signature):
    # A changed workbook invalidates both Streamlit and the engine's parquet cache.
    return engine.load_all(str(ROOT / "data"))


@st.cache_data(show_spinner="Рассчитываем план заказа…")
def get_plan(data, settings, source_signature):
    return engine.build_plan(data, settings)


def _export_rows(approved):
    result = approved.copy()
    numbers = pd.to_numeric(result["qty"], errors="coerce")
    if not numbers.map(lambda n: pd.notna(n) and math.isfinite(n) and n >= 0 and float(n).is_integer()).all():
        raise ValueError("Количество должно быть целым неотрицательным числом.")
    result["qty"] = numbers.astype("int64")
    result["value"] = result["qty"] * result["price"]
    return result.loc[result["qty"].gt(0)]


@st.cache_data(show_spinner=False)
def make_excel(approved: pd.DataFrame, approved_by: str, calculation_date: date) -> bytes:
    approved = _export_rows(approved)
    output = BytesIO()
    columns = {
        "code": "Код 1С", "article": "Артикул", "name": "Наименование",
        "qty": "Количество", "unit": "Ед.", "price": "Цена", "value": "Сумма",
        "urgency": "Срочность", "reason": "Почему",
    }
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for supplier in engine.SUPPLIERS:
            subset = approved.loc[approved["supplier"].eq(supplier), list(columns)].rename(columns=columns)
            sheet_name = "SE" if supplier == "Systeme Electric" else "IEK"
            subset.to_excel(writer, sheet_name=sheet_name, index=False, startrow=3)
            sheet = writer.book[sheet_name]
            sheet["A1"] = f"Поставщик: {supplier}"
            sheet["A2"] = f"Утвердил: {approved_by or 'не указан'}"
            sheet["A3"] = f"Дата: {calculation_date:%d.%m.%Y}"
            sheet.freeze_panes = "A5"
            # Codes and explanations must stay text, including leading zeros or '='.
            for row in sheet.iter_rows(min_row=5):
                for col in (0, 1, 2, 4, 7, 8):
                    row[col].data_type = "s"
                for col in (5, 6):
                    row[col].number_format = '#,##0.00'
            for column in sheet.columns:
                width = min(70, max(len(str(cell.value or "")) for cell in column) + 2)
                sheet.column_dimensions[column[0].column_letter].width = width
    return output.getvalue()


@st.cache_data(show_spinner=False)
def make_csv(approved: pd.DataFrame) -> bytes:
    approved = _export_rows(approved)
    columns = {
        "supplier": "Поставщик", "code": "Код 1С", "article": "Артикул",
        "name": "Наименование", "qty": "Количество", "unit": "Ед.",
        "price": "Цена", "value": "Сумма", "urgency": "Срочность", "reason": "Почему",
    }
    return approved[list(columns)].rename(columns=columns).to_csv(index=False, sep=";").encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def make_manager_export(approved, template_mtime):
    from export_manager_sheet import fill_manager_sheet
    return fill_manager_sheet(str(ROOT / "data" / "se_manager_sheet.xlsx"), approved)


def save_order_edits(widget_key, row_ids):
    """Apply editor deltas to product IDs, never positions from a different filter."""
    for index, changes in st.session_state[widget_key].get("edited_rows", {}).items():
        position = int(index)
        if not 0 <= position < len(row_ids):
            continue
        identity = row_ids[position]
        if "Кол-во" in changes:
            value = changes["Кол-во"]
            try:
                quantity = float(value) if value is not None else 0.0
                if not math.isfinite(quantity) or quantity < 0 or not quantity.is_integer():
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                st.session_state["order_edit_error"] = "Введите целое неотрицательное количество."
                st.session_state["order_approvals"].discard(identity)
                continue
            st.session_state["order_quantities"][identity] = int(quantity)
            # Changing the number revokes the earlier approval of that number.
            st.session_state["order_approvals"].discard(identity)
        if "✔ Утвердить" in changes:
            if changes["✔ Утвердить"]:
                st.session_state["order_approvals"].add(identity)
            else:
                st.session_state["order_approvals"].discard(identity)
    # A fresh widget consumes the new canonical values without replaying old deltas.
    st.session_state["order_revision"] += 1


def approve_visible(row_ids):
    st.session_state["order_approvals"].update(row_ids)
    st.session_state["order_revision"] += 1


def clear_approvals():
    st.session_state["order_approvals"].clear()
    st.session_state["order_revision"] += 1


st.title("SmartZakup — план закупок")
st.warning("Заказ не отправляется поставщику без утверждения ответственного сотрудника")

with st.sidebar:
    st.header("Настройки")
    calculation_date = st.date_input("Дата расчёта", value=date(2026, 9, 22))
    st.caption("Данные кейса: по 22.09.2026. Историческое окно: март–август 2026.")
    source_label = st.selectbox(
        "Источник спроса",
        ["Накладные (автоочистка разовых заказов)", "Ежемесячный отчёт компании"],
    )
    st.subheader("Systeme Electric")
    se_lead = st.number_input("Срок поставки SE, дней", min_value=1, max_value=365, value=30)
    se_review = st.number_input("До следующего заказа SE, дней", min_value=1, max_value=365, value=30)
    st.subheader("IEK")
    iek_lead = st.number_input("Срок поставки IEK, дней", min_value=1, max_value=365, value=35)
    iek_review = st.number_input("До следующего заказа IEK, дней", min_value=1, max_value=365, value=14)
    growth = st.number_input("План роста продаж, %", min_value=-50.0, max_value=200.0, value=0.0, step=1.0)
    with st.expander("Уровень сервиса по классам"):
        z_a = st.number_input("A (z)", min_value=0.0, max_value=5.0, value=1.65, step=0.01)
        z_b = st.number_input("B (z)", min_value=0.0, max_value=5.0, value=1.28, step=0.01)
        z_c = st.number_input("C (z)", min_value=0.0, max_value=5.0, value=0.84, step=0.01)

settings = engine.Settings(
    today=calculation_date,
    demand_source="invoices" if source_label.startswith("Накладные") else "monthly_report",
    lead_time_days={"IEK": int(iek_lead), "Systeme Electric": int(se_lead)},
    review_days={"IEK": int(iek_review), "Systeme Electric": int(se_review)},
    service_z={"A": float(z_a), "B": float(z_b), "C": float(z_c)},
    plan_growth_pct=float(growth),
)
source_paths = [ROOT / "engine.py", *sorted((ROOT / "data").glob("*.xlsx"))]
source_signature = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in source_paths)
try:
    data = get_data(source_signature)
    plan_df, details = get_plan(data, settings, source_signature)
except Exception as error:
    st.error(f"Не удалось построить план: {error}")
    st.exception(error)
    st.stop()

plan_signature = sha256(json.dumps([asdict(settings), source_signature], sort_keys=True, default=str).encode()).hexdigest()
if st.session_state.get("order_plan_signature") != plan_signature:
    had_approvals = bool(st.session_state.get("order_approvals"))
    st.session_state["order_plan_signature"] = plan_signature
    st.session_state["order_quantities"] = {}
    st.session_state["order_approvals"] = set()
    st.session_state["order_revision"] = st.session_state.get("order_revision", 0) + 1
    if had_approvals:
        st.info("Параметры расчёта изменились: проверьте новый план и утвердите позиции заново.")

tab_order, tab_checks, tab_analytics, tab_ai = st.tabs(
    ["📦 Заказ", "✅ Проверка", "📊 Аналитика", "🤖 AI помощник"]
)

with tab_order:
    st.subheader("Рекомендованный заказ")
    working = plan_df.copy()
    working["_identity"] = list(zip(working["supplier"], working["code"]))
    working["qty"] = pd.Series(
        [st.session_state["order_quantities"].get(key, qty) for key, qty in zip(working["_identity"], working["qty"])],
        index=working.index, dtype="int64",
    )
    working["value"] = working["qty"] * working["price"]
    working["approved"] = working["_identity"].isin(st.session_state["order_approvals"])
    filter_1, filter_2, filter_3, filter_4 = st.columns(4)
    supplier_filter = filter_1.selectbox("Поставщик", ["Все", *engine.SUPPLIERS], key="order_supplier")
    urgency_filter = filter_2.multiselect(
        "Срочность", ["🔴 Критично", "🟡 Заказать", "🟢 Не требуется"],
        default=["🔴 Критично", "🟡 Заказать"], key="order_urgency",
    )
    available_categories = sorted(value for value in plan_df["category"].dropna().unique() if value)
    category_filter = filter_3.multiselect("Категория", available_categories, key="order_category")
    search = filter_4.text_input("Поиск", placeholder="Код, артикул или название", key="order_search")
    visible = working.copy()
    if supplier_filter != "Все":
        visible = visible[visible["supplier"].eq(supplier_filter)]
    visible = visible[visible["urgency"].isin(urgency_filter)]
    if category_filter:
        visible = visible[visible["category"].isin(category_filter)]
    if search.strip():
        needle = search.strip().casefold()
        mask = visible[["code", "article", "name"]].fillna("").astype(str).apply(
            lambda column: column.str.casefold().str.contains(needle, regex=False)
        ).any(axis=1)
        visible = visible[mask]

    st.caption("Количество и суммы учитывают ваши правки. Срочность и «Почему» — исходный расчёт; изменение количества снимает утверждение строки.")
    for supplier in engine.SUPPLIERS:
        if supplier_filter != "Все" and supplier_filter != supplier:
            continue
        subset = visible[visible["supplier"].eq(supplier)]
        to_order = subset[subset["qty"].gt(0)]
        st.markdown(f"**{supplier}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Позиций к заказу", f"{len(to_order):,}".replace(",", " "))
        c2.metric("Сумма", f"{to_order['value'].sum():,.0f} ₸".replace(",", " "))
        c3.metric("Критичных", int(subset["urgency"].eq("🔴 Критично").sum()))

    valid_visible = visible.loc[visible["qty"].gt(0) & visible["qty"].mod(visible["multiple"]).eq(0)]
    a1, a2 = st.columns(2)
    a1.button(
        "Утвердить всё видимое", disabled=valid_visible.empty,
        on_click=approve_visible, args=(tuple(valid_visible["_identity"]),),
        help="Только положительные количества, кратные упаковке поставщика.",
    )
    a2.button("Снять все утверждения", disabled=not st.session_state["order_approvals"], on_click=clear_approvals)

    if visible.empty:
        st.info("По выбранным фильтрам ничего не найдено. Измените поиск, категорию или срочность.")
    else:
        names = {
            "supplier": "Поставщик", "code": "Код 1С", "article": "Артикул",
            "name": "Наименование", "abc_class": "Класс", "urgency": "Срочность",
            "qty": "Кол-во", "unit": "Ед.", "multiple": "Кратность", "value": "Сумма ₸",
            "enough_until": "Хватит до", "reason": "Почему", "approved": "✔ Утвердить",
        }
        shown_columns = [
            "✔ Утвердить", "Кол-во", "Поставщик", "Код 1С", "Артикул", "Наименование",
            "Класс", "Срочность", "Ед.", "Кратность", "Сумма ₸", "Хватит до", "Почему",
        ]
        row_ids = tuple(visible["_identity"])
        view_hash = sha256(repr(row_ids).encode()).hexdigest()[:12]
        editor_key = f"order_editor_{st.session_state['order_revision']}_{view_hash}"
        st.data_editor(
            visible.rename(columns=names)[shown_columns].reset_index(drop=True),
            hide_index=True, width="stretch", num_rows="fixed",
            disabled=[c for c in shown_columns if c not in ["Кол-во", "✔ Утвердить"]],
            column_config={
                "Кол-во": st.column_config.NumberColumn(min_value=0, step=1, required=True),
                "Сумма ₸": st.column_config.NumberColumn(format="localized"),
                "Код 1С": st.column_config.TextColumn(),
                "Наименование": st.column_config.TextColumn(width="large"),
                "Хватит до": st.column_config.DateColumn(format="DD.MM.YYYY"),
                "✔ Утвердить": st.column_config.CheckboxColumn(),
                "Почему": st.column_config.TextColumn(width="large"),
            },
            key=editor_key, on_change=save_order_edits, args=(editor_key, row_ids),
        )
        invalid = visible.loc[visible["qty"].mod(visible["multiple"]).ne(0)]
        if not invalid.empty:
            st.warning("Количество должно быть кратно упаковке. Исправьте: " + ", ".join(
                f"{r.code} (кратность {r.multiple})" for r in invalid.head(5).itertuples()
            ))
    if "order_edit_error" in st.session_state:
        st.error(st.session_state.pop("order_edit_error"))

    approved = working.loc[working["approved"] & working["qty"].gt(0)].drop(columns=["_identity", "approved"]).copy()
    # Keep the audit reason honest after the manager overrides the recommendation.
    recommended = plan_df.set_index(["supplier", "code"])["qty"].to_dict()
    approved["reason"] = [
        row.reason + (f" Количество изменено менеджером: {recommended[(row.supplier, row.code)]} → {row.qty} {row.unit}."
                      if recommended[(row.supplier, row.code)] != row.qty else "")
        for row in approved.itertuples()
    ]
    invalid_approved = approved["qty"].mod(approved["multiple"]).ne(0).any()
    can_download = not approved.empty and not invalid_approved
    hidden_count = len(approved) - int(approved.set_index(["supplier", "code"]).index.isin(row_ids if not visible.empty else ()).sum())
    st.caption(f"Утверждено к выгрузке: {len(approved)} поз. · {approved['value'].sum():,.0f} ₸ · вне текущего фильтра: {hidden_count}".replace(",", " "))
    if invalid_approved:
        st.error("В утверждённом заказе есть количество, не кратное упаковке. Исправьте его перед выгрузкой.")
    approved_by = st.text_input("Утвердил", placeholder="Имя ответственного сотрудника", key="order_approved_by")
    xlsx_data = make_excel(approved, approved_by, calculation_date) if can_download else b""
    csv_data = make_csv(approved) if can_download else b""
    d1, d2 = st.columns(2)
    d1.download_button(
        "Заказ для 1С (Excel)", data=xlsx_data, file_name=f"zakaz_1c_{calculation_date:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled=not can_download,
    )
    d2.download_button(
        "Заказ для 1С (CSV)", data=csv_data, file_name=f"zakaz_1c_{calculation_date:%Y%m%d}.csv",
        mime="text/csv", disabled=not can_download,
    )
    try:
        from export_manager_sheet import fill_manager_sheet
    except ImportError:
        fill_manager_sheet = None
    if fill_manager_sheet is not None:
        se_approved = approved[approved["supplier"].eq("Systeme Electric")]
        manager_ready = can_download and not se_approved.empty
        manager_bytes = make_manager_export(se_approved, (ROOT / "data" / "se_manager_sheet.xlsx").stat().st_mtime_ns) if manager_ready else b""
        st.download_button(
            "Лист менеджера SE", data=manager_bytes, file_name="se_manager_order.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", disabled=not manager_ready,
        )

with tab_checks:
    try:
        from tab_checks import render_checks_tab
    except ImportError:
        st.info("Вкладка в разработке")
    else:
        render_checks_tab(engine, data, settings, plan_df, details)

with tab_analytics:
    try:
        from tab_analytics import render_analytics_tab
    except ImportError:
        st.info("Вкладка в разработке")
    else:
        render_analytics_tab(engine, data, settings, plan_df, details)

with tab_ai:
    try:
        from tab_ai import render_ai_tab
    except ImportError:
        st.info("Вкладка в разработке")
    else:
        render_ai_tab(engine, data, settings, plan_df, details)
