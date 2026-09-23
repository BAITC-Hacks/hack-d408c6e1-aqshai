"""Person 2's independent preview; no real purchasing engine is imported."""
import streamlit as st
import engine_stub as engine
from tab_checks import render_checks_tab
from tab_analytics import render_analytics_tab

st.set_page_config(page_title='SmartZakup — предварительный просмотр', layout='wide')
st.title('SmartZakup · Проверка и аналитика')
st.warning('ДЕМОДАННЫЕ: временный движок для проверки интерфейса. Для реальных расчётов запустите app.py.')
st.info('Заказ не отправляется поставщику без утверждения ответственного сотрудника')
settings = engine.Settings()
settings.plan_growth_pct = st.sidebar.number_input('План роста продаж, %', min_value=-90., max_value=200., value=0.)

@st.cache_data
def preview_data():
    return engine.load_all()

data = preview_data()
plan_df, details = engine.build_plan(data, settings)
checks, analytics = st.tabs(['✅ Проверка', '📊 Аналитика'])
with checks:
    render_checks_tab(engine, data, settings, plan_df, details)
with analytics:
    render_analytics_tab(engine, data, settings, plan_df, details)
