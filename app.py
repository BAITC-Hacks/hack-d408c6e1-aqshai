"""Streamlit interface for the Person 1 SmartZakup milestone."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

import engine


st.set_page_config(page_title="SmartZakup", page_icon="📦", layout="wide")


@st.cache_data(show_spinner="Читаем и очищаем данные…")
def get_data():
    return engine.load_all("data")


@st.cache_data(show_spinner="Рассчитываем план заказа…")
def get_plan(data, settings):
    return engine.build_plan(data, settings)


def make_excel(approved: pd.DataFrame, approved_by: str, calculation_date: date) -> bytes:
    output = BytesIO()
    columns = {
        "code": "Код 1С", "article": "Артикул", "name": "Наименование",
        "qty": "Количество", "unit": "Ед.", "price": "Цена", "value": "Сумма",
        "urgency": "Срочность", "reason": "Почему",
    }
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for supplier in engine.SUPPLIERS:
            subset = approved[approved["supplier"].eq(supplier)][list(columns)].rename(columns=columns)
            sheet_name = "SE" if supplier == "Systeme Electric" else "IEK"
            subset.to_excel(writer, sheet_name=sheet_name, index=False, startrow=3)
            sheet = writer.book[sheet_name]
            sheet["A1"] = f"Поставщик: {supplier}"
            sheet["A2"] = f"Утвердил: {approved_by or 'не указан'}"
            sheet["A3"] = f"Дата: {calculation_date:%d.%m.%Y}"
            sheet.freeze_panes = "A5"
            for column in sheet.columns:
                width = min(80, max(len(str(cell.value or "")) for cell in column) + 2)
                sheet.column_dimensions[column[0].column_letter].width = width
    return output.getvalue()


def make_csv(approved: pd.DataFrame) -> bytes:
    columns = {
        "supplier": "Поставщик", "code": "Код 1С", "article": "Артикул",
        "name": "Наименование", "qty": "Количество", "unit": "Ед.",
        "price": "Цена", "value": "Сумма", "urgency": "Срочность", "reason": "Почему",
    }
    return approved[list(columns)].rename(columns=columns).to_csv(index=False, sep=";").encode("utf-8-sig")


st.title("SmartZakup — план закупок")
st.warning("Заказ не отправляется поставщику без утверждения ответственного сотрудника")

with st.sidebar:
    st.header("Настройки")
    calculation_date = st.date_input("Дата расчёта", value=date(2026, 9, 22))
    source_label = st.selectbox(
        "Источник спроса",
        ["Накладные (автоочистка разовых заказов)", "Ежемесячный отчёт компании"],
    )
    st.subheader("Systeme Electric")
    se_lead = st.number_input("Срок поставки SE, дней", min_value=1, value=30)
    se_review = st.number_input("До следующего заказа SE, дней", min_value=1, value=30)
    st.subheader("IEK")
    iek_lead = st.number_input("Срок поставки IEK, дней", min_value=1, value=35)
    iek_review = st.number_input("До следующего заказа IEK, дней", min_value=1, value=14)
    growth = st.number_input("План роста продаж, %", min_value=-50.0, max_value=200.0, value=0.0, step=1.0)
    with st.expander("Уровень сервиса по классам"):
        z_a = st.number_input("A (z)", value=1.65, step=0.01)
        z_b = st.number_input("B (z)", value=1.28, step=0.01)
        z_c = st.number_input("C (z)", value=0.84, step=0.01)

settings = engine.Settings(
    today=calculation_date,
    demand_source="invoices" if source_label.startswith("Накладные") else "monthly_report",
    lead_time_days={"IEK": int(iek_lead), "Systeme Electric": int(se_lead)},
    review_days={"IEK": int(iek_review), "Systeme Electric": int(se_review)},
    service_z={"A": float(z_a), "B": float(z_b), "C": float(z_c)},
    plan_growth_pct=float(growth),
)

try:
    data = get_data()
    plan_df, details = get_plan(data, settings)
except Exception as error:
    st.error(f"Не удалось построить план: {error}")
    st.exception(error)
    st.stop()

tab_order, tab_checks, tab_analytics, tab_ai = st.tabs(
    ["📦 Заказ", "✅ Проверка", "📊 Аналитика", "🤖 AI помощник"]
)

with tab_order:
    st.subheader("Рекомендованный заказ")
    filter_1, filter_2, filter_3, filter_4 = st.columns(4)
    supplier_filter = filter_1.selectbox("Поставщик", ["Все", *engine.SUPPLIERS])
    urgency_filter = filter_2.multiselect(
        "Срочность", ["🔴 Критично", "🟡 Заказать", "🟢 Не требуется"],
        default=["🔴 Критично", "🟡 Заказать"],
    )
    available_categories = sorted(value for value in plan_df["category"].dropna().unique() if value)
    category_filter = filter_3.multiselect("Категория", available_categories)
    search = filter_4.text_input("Поиск", placeholder="Код, артикул или название")

    visible = plan_df.copy()
    if supplier_filter != "Все":
        visible = visible[visible["supplier"].eq(supplier_filter)]
    if urgency_filter:
        visible = visible[visible["urgency"].isin(urgency_filter)]
    else:
        visible = visible.iloc[0:0]
    if category_filter:
        visible = visible[visible["category"].isin(category_filter)]
    if search.strip():
        needle = search.strip().casefold()
        visible = visible[
            visible[["code", "article", "name"]].fillna("").astype(str)
            .apply(lambda column: column.str.casefold().str.contains(needle, regex=False)).any(axis=1)
        ]

    for supplier in engine.SUPPLIERS:
        subset = visible[visible["supplier"].eq(supplier)]
        to_order = subset[subset["qty"].gt(0)]
        st.markdown(f"**{supplier}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Позиций к заказу", f"{len(to_order):,}".replace(",", " "))
        c2.metric("Сумма", f"{to_order['value'].sum():,.0f} ₸".replace(",", " "))
        c3.metric("Критичных", int(subset["urgency"].eq("🔴 Критично").sum()))

    state_key = "approval_codes"
    if state_key not in st.session_state:
        st.session_state[state_key] = set()
    qty_state_key = "order_qty_overrides"
    if qty_state_key not in st.session_state:
        st.session_state[qty_state_key] = {}
    if st.button("Утвердить всё видимое", disabled=visible.empty):
        st.session_state[state_key].update(visible.loc[visible["qty"].gt(0), "code"])
        st.session_state.pop("order_editor", None)

    display = visible.copy()
    display["qty"] = display.apply(
        lambda row: st.session_state[qty_state_key].get(row["code"], row["qty"]), axis=1
    )
    display["approved"] = display["code"].isin(st.session_state[state_key])
    display = display.rename(columns={
        "supplier": "Поставщик", "code": "Код 1С", "article": "Артикул",
        "name": "Наименование", "abc_class": "Класс", "urgency": "Срочность",
        "qty": "Кол-во", "unit": "Ед.", "multiple": "Кратность", "value": "Сумма ₸",
        "enough_until": "Хватит до", "reason": "Почему", "approved": "✔ Утвердить",
    })
    shown_columns = [
        "Поставщик", "Код 1С", "Артикул", "Наименование", "Класс", "Срочность",
        "Кол-во", "Ед.", "Кратность", "Сумма ₸", "Хватит до", "Почему", "✔ Утвердить",
    ]
    edited = st.data_editor(
        display[shown_columns], hide_index=True, width="stretch", num_rows="fixed",
        disabled=[c for c in shown_columns if c not in ["Кол-во", "✔ Утвердить"]],
        column_config={
            "Кол-во": st.column_config.NumberColumn(min_value=0, step=1),
            "Сумма ₸": st.column_config.NumberColumn(format="%.0f ₸"),
            "✔ Утвердить": st.column_config.CheckboxColumn(),
            "Почему": st.column_config.TextColumn(width="large"),
        },
        key="order_editor",
    )
    edited_codes = set(edited.loc[edited["✔ Утвердить"], "Код 1С"])
    visible_codes = set(edited["Код 1С"])
    st.session_state[state_key] = (st.session_state[state_key] - visible_codes) | edited_codes
    qty_updates = edited.set_index("Код 1С")["Кол-во"].to_dict()
    st.session_state[qty_state_key].update(qty_updates)
    approved = plan_df[plan_df["code"].isin(st.session_state[state_key])].copy()
    approved["qty"] = approved.apply(
        lambda row: st.session_state[qty_state_key].get(row["code"], row["qty"]), axis=1
    )
    approved["qty"] = pd.to_numeric(approved["qty"], errors="coerce").fillna(0).clip(lower=0).round().astype(int)
    approved["value"] = approved["qty"] * approved["price"]
    approved = approved[approved["qty"].gt(0)]

    approved_by = st.text_input("Утвердил", placeholder="Имя ответственного сотрудника")
    xlsx_data = make_excel(approved, approved_by, calculation_date)
    csv_data = make_csv(approved)
    d1, d2 = st.columns(2)
    d1.download_button(
        "Заказ для 1С (Excel)", data=xlsx_data, file_name=f"zakaz_1c_{calculation_date:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=approved.empty,
    )
    d2.download_button(
        "Заказ для 1С (CSV)", data=csv_data, file_name=f"zakaz_1c_{calculation_date:%Y%m%d}.csv",
        mime="text/csv", disabled=approved.empty,
    )
    try:
        from export_manager_sheet import fill_manager_sheet

        manager_bytes = fill_manager_sheet("data/se_manager_sheet.xlsx", approved)
        st.download_button(
            "Лист менеджера SE", data=manager_bytes, file_name="se_manager_order.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=approved[approved["supplier"].eq("Systeme Electric")].empty,
        )
    except ImportError:
        pass

with tab_checks:
    try:
        from tab_checks import render_checks_tab

        render_checks_tab(engine, data, settings, plan_df, details)
    except ImportError:
        st.info("Вкладка в разработке")

with tab_analytics:
    try:
        from tab_analytics import render_analytics_tab

        render_analytics_tab(engine, data, settings, plan_df, details)
    except ImportError:
        st.info("Вкладка в разработке")

with tab_ai:
    try:
        from tab_ai import render_ai_tab

        render_ai_tab(engine, data, settings, plan_df, details)
    except ImportError:
        st.info("Вкладка в разработке")
