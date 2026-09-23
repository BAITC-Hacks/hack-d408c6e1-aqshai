"""Judge-facing checks using only the public engine contract."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _row(plan, code):
    return plan.loc[plan['code'].eq(code)].iloc[0]


def _choose(plan, label, key, preferred=None):
    codes = plan['code'].tolist()
    labels = {r.code: f'{r.supplier} · {r.code} · {r.name}' for r in plan.itertuples()}
    index = codes.index(preferred) if preferred in codes else 0
    return st.selectbox(label, codes, index=index, format_func=labels.get, key=key)


def _verdict(passed, text):
    (st.success if passed else st.error)(('✅ ' if passed else '❌ ') + text)


def _history_chart(detail, columns, forecast=False):
    fig = go.Figure()
    names = {'raw': 'Исходные продажи', 'cleaned': 'Без разовых заказов', 'adjusted': 'С учётом дефицита'}
    for column in columns:
        fig.add_scatter(x=detail['history'].index.astype(str), y=detail['history'][column],
                        name=names[column], mode='lines')
    if forecast:
        future = detail['forecast']
        fig.add_scatter(x=future['month'].astype(str), y=future['forecast'], name='Прогноз',
                        mode='lines', line={'dash': 'dash'})
    fig.update_layout(xaxis_title='Месяц', yaxis_title='Количество, в единицах товара', legend={'orientation': 'h'})
    return fig


def render_checks_tab(engine, data, settings, plan_df, details):
    st.subheader('Пять проверок расчёта')
    if plan_df.empty:
        st.info('Нет товаров для проверки.')
        return
    if getattr(engine, 'IS_STUB', False):
        st.warning('Демонстрационный движок: эти результаты не подтверждают работу реального расчёта.')
    st.caption('Проверки используют копии параметров и не меняют исходные файлы или утверждённый заказ. Результаты выводятся для текущего запуска.')
    run_all = st.button('Запустить все проверки', key='checks_all')
    active = plan_df.loc[(plan_df['qty'] > 0) & ~plan_df['do_not_reorder']]

    with st.expander('1. Товар в пути', expanded=True):
        if active.empty:
            st.warning('Нет товара с положительным заказом: проверка недоступна.')
        else:
            code = _choose(active, 'Товар для проверки поставки', 'checks_transit_code')
            old = _row(plan_df, code)
            amount = st.number_input('Добавить в путь, единиц', min_value=0., value=float(old.qty), key=f'checks_transit_{code}')
            run = st.button('Проверить товар в пути', key='checks_transit_run')
            if run_all or run:
                with st.spinner('Пересчёт с дополнительной поставкой…'):
                    after, _ = engine.build_plan(data, settings, overrides={'in_transit': {code: float(old.in_transit)+amount}})
                new = _row(after, code)
                _verdict(new.qty < old.qty, f'Заказ: {old.qty:g} → {new.qty:g}; в пути: {old.in_transit:g} → {new.in_transit:g}.')

    with st.expander('2. Сезонность', expanded=True):
        def seasonal_range(code):
            values = details[code]['forecast']['forecast']
            return float(values.max()-values.min()) / max(float(values.mean()), 1e-9)
        default = max(plan_df['code'], key=seasonal_range)
        code = _choose(plan_df, 'Сезонный товар', 'checks_season_code', default)
        detail = details[code]
        st.plotly_chart(_history_chart(detail, ['raw'], forecast=True), use_container_width=True, key='checks_season_chart')
        st.dataframe(pd.DataFrame({'Месяц': ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'],
                                   'Коэффициент': detail['season_factors']}), hide_index=True)
        run = st.button('Проверить сезонность', key='checks_season_run')
        if run_all or run:
            lo, hi = float(detail['forecast']['forecast'].min()), float(detail['forecast']['forecast'].max())
            ratio = hi/lo if lo > 0 else (float('inf') if hi > 0 else 1.)
            _verdict(hi > lo and ratio >= 1.3, f'Минимум → максимум прогноза: {lo:.1f} → {hi:.1f}; отношение {ratio:.2f} (порог 1,30).')

    with st.expander('3. Восстановление спроса при дефиците', expanded=True):
        candidates = plan_df.loc[~plan_df['do_not_reorder'] & plan_df['code'].map(lambda c: not details[c]['stockouts'].empty)]
        if candidates.empty:
            st.warning('Нет товаров с выявленным дефицитом: проверка недоступна.')
        else:
            default = max(candidates['code'], key=lambda c: len(details[c]['stockouts']))
            code = _choose(candidates, 'Товар с дефицитом', 'checks_stockout_code', default)
            st.plotly_chart(_history_chart(details[code], ['raw', 'adjusted']), use_container_width=True, key='checks_stockout_chart')
            run = st.button('Проверить влияние дефицита', key='checks_stockout_run')
            if run_all or run:
                with st.spinner('Расчёт без восстановления потерянного спроса…'):
                    without, _ = engine.build_plan(data, settings, overrides={'disable_stockout_adjustment': True})
                before, after = _row(without, code), _row(plan_df, code)
                _verdict(after.qty > before.qty, f'Заказ без поправки → с поправкой: {before.qty:g} → {after.qty:g}.')
                if after.qty == before.qty:
                    st.caption('Запас или округление могут скрыть изменение потребности. Выберите другой товар; равенство не считается успешной проверкой.')

    with st.expander('4. Разовый крупный заказ', expanded=True):
        if active.empty:
            st.warning('Нет активных товаров с заказом: проверка недоступна.')
        else:
            invoice_counts = data['invoices'].groupby('code').size()
            preferred = active.loc[active['code'].map(invoice_counts).fillna(0).ge(10)]
            code = _choose(active, 'Товар для разового заказа', 'checks_spike_code', preferred.iloc[0]['code'] if not preferred.empty else None)
            old = _row(plan_df, code)
            fake_qty = st.number_input('Размер фиктивного заказа, единиц', min_value=1., value=max(1.,20*float(old.base_monthly)), key=f'checks_spike_{code}')
            last_month = pd.Period(settings.today, freq='M')-1
            st.caption(f'Фиктивная накладная: 15.{last_month.month:02d}.{last_month.year}. Успех: рост рекомендации менее 10% после округления.')
            run = st.button('Добавить фиктивный разовый заказ', key='checks_spike_run')
            if run_all or run:
                with st.spinner('Проверка устойчивости к всплеску…'):
                    after, _ = engine.build_plan(data, settings, overrides={'extra_invoice_lines': [
                        {'supplier': old.supplier, 'code': code, 'date': f'{last_month}-15', 'qty': fake_qty}]})
                new = _row(after, code)
                increase = 100*(new.qty-old.qty)/old.qty
                _verdict(increase < 10, f'Заказ: {old.qty:g} → {new.qty:g}; изменение {increase:+.2f}%.')
                if settings.demand_source == 'monthly_report':
                    st.info('Выбран месячный отчёт: добавленная накладная не проверяет очистку спроса. Для проверки фильтра переключитесь на накладные.')

    with st.expander('5. Объяснения и фильтр поставщика', expanded=True):
        supplier = st.selectbox('Поставщик для проверки', sorted(plan_df['supplier'].unique()), key='checks_supplier')
        selected = plan_df.loc[plan_df['supplier'].eq(supplier)]
        st.dataframe(selected[['supplier','code','qty','reason']].rename(columns={
            'supplier':'Поставщик','code':'Код 1С','qty':'Заказ','reason':'Почему'}), hide_index=True)
        run = st.button('Проверить объяснения', key='checks_reasons_run')
        if run_all or run:
            explained = plan_df['reason'].fillna('').astype(str).str.strip().ne('')
            _verdict(bool(explained.all() and not selected.empty and selected['supplier'].eq(supplier).all()),
                     f'С объяснениями: {int(explained.sum())}/{len(plan_df)}. До фильтра → после: {len(plan_df)} → {len(selected)}; только {supplier}.')
