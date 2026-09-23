"""Russian analytics built from the shared engine's returned details."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def _events(plan, details, key):
    frames = []
    for row in plan.itertuples():
        frame = details[row.code][key].copy()
        if not frame.empty:
            frame['supplier'], frame['code'], frame['name'] = row.supplier, row.code, row.name
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _kpis(plan, details, today):
    first = pd.Period(today, freq='M')
    excess = lost = 0.
    count = 0
    for row in plan.itertuples():
        detail = details[row.code]
        forecast = detail['forecast'].sort_values('month').head(3)['forecast'].sum()
        excess += max(0., row.available-float(forecast))*row.price
        stockouts = detail['stockouts']
        if not stockouts.empty:
            recent = stockouts['month'].map(lambda m: first-12 <= pd.Period(m, freq='M') < first)
            lost += float(stockouts.loc[recent, 'lost'].sum())*row.price
        count += len(detail['one_offs'])
    return excess, lost, count


def render_analytics_tab(engine, data, settings, plan_df, details):
    st.subheader('Аналитика закупок')
    if plan_df.empty:
        st.info('Нет данных для аналитики.')
        return
    supplier = st.selectbox('Поставщик', ['Все']+sorted(plan_df['supplier'].unique()), key='analytics_supplier')
    plan = plan_df if supplier == 'Все' else plan_df.loc[plan_df['supplier'].eq(supplier)]
    excess, lost, count = _kpis(plan, details, settings.today)
    a,b,c = st.columns(3)
    money = lambda value: f'{value:,.0f} ₸'.replace(',', ' ')
    a.metric('Избыточный запас', money(excess))
    b.metric('Потерянные продажи за 12 мес.', money(lost))
    c.metric('Разовых заказов найдено', count)
    st.caption('Избыток: остаток сверх суммы ближайших трёх месячных прогнозов × цена. Потери: восстановленные единицы за 12 полных месяцев × цена. SE — себестоимость; IEK — прайс с НДС, это оценка, а не прибыль.')

    st.markdown('#### Спрос по категории')
    category = st.selectbox('Категория', sorted(plan['category'].fillna('Прочее').unique()), key='analytics_category')
    category_plan = plan.loc[plan['category'].fillna('Прочее').eq(category)]
    # Do not add meters to pieces: keep each unit as a separate series.
    frames = []
    for row in category_plan.itertuples():
        series = details[row.code]['history'][['cleaned']].reset_index()
        series.columns = ['month','qty']
        series['unit'] = row.unit
        frames.append(series)
    if frames:
        trend = pd.concat(frames).groupby(['month','unit'], as_index=False)['qty'].sum()
        trend['month'] = trend['month'].astype(str)
        trend = trend.rename(columns={'month':'Месяц','unit':'Ед.','qty':'Регулярный спрос'})
        st.plotly_chart(px.line(trend, x='Месяц', y='Регулярный спрос', color='Ед.'), use_container_width=True, key='analytics_category_chart')

    st.markdown('#### Прогноз товара')
    labels = {r.code: f'{r.code} · {r.name}' for r in plan.itertuples()}
    code = st.selectbox('Товар', list(labels), format_func=labels.get, key='analytics_product')
    detail = details[code]
    fig = go.Figure()
    for column, label in [('raw','Исходные продажи'),('cleaned','Без разовых заказов')]:
        fig.add_scatter(x=detail['history'].index.astype(str), y=detail['history'][column], name=label, mode='lines')
    fig.add_scatter(x=detail['forecast']['month'].astype(str), y=detail['forecast']['forecast'],
                    name='Прогноз с учётом дефицита', mode='lines', line={'dash':'dash'})
    unit = plan.loc[plan['code'].eq(code),'unit'].iloc[0]
    fig.update_layout(xaxis_title='Месяц', yaxis_title=f'Количество, {unit}', legend={'orientation':'h'})
    st.plotly_chart(fig, use_container_width=True, key='analytics_product_chart')

    labels = {'supplier':'Поставщик','code':'Код 1С','name':'Наименование','date':'Дата','doc':'Накладная',
              'qty':'Количество','typical_qty':'Обычно в строке','month':'Месяц','actual':'Продано',
              'expected':'Ожидалось','lost':'Потерянный спрос'}
    for key, title in [('one_offs','Исключённые разовые заказы'),('stockouts','Месяцы с дефицитом')]:
        st.markdown('#### '+title)
        events = _events(plan, details, key)
        if events.empty:
            st.info('Не обнаружены.')
        else:
            if 'month' in events:
                events['month'] = events['month'].astype(str)
            st.dataframe(events.rename(columns=labels), hide_index=True, use_container_width=True)
