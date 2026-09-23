"""SPEC §7: acceptance checks against the REAL engine and supplied data."""
from dataclasses import replace
from pathlib import Path
import sys
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if not (ROOT / 'engine.py').is_file():
    pytest.skip('Реальный engine.py ещё не добавлен Person 1; stub не используется.', allow_module_level=True)
import engine

@pytest.fixture(scope='module')
def baseline():
    data = engine.load_all(str(ROOT / 'data'))
    settings = engine.Settings()
    plan, details = engine.build_plan(data, settings)
    return data, settings, plan, details


def _quantities(plan):
    return plan.set_index(['supplier', 'code'])['qty'].sort_index()


def _active(baseline):
    data, _, plan, _ = baseline
    counts = data['invoices'].groupby(['supplier','code']).size()
    active = plan.loc[plan['qty'].gt(0) & ~plan['do_not_reorder'] & plan['base_monthly'].gt(0)]
    active = active.loc[[counts.get((r.supplier,r.code),0) >= 10 for r in active.itertuples()]]
    assert not active.empty, 'В реальных данных должен быть активный товар с >=10 строками накладных'
    return active.iloc[0]


def test_in_transit_changes_result(baseline):
    data, settings, _, _ = baseline
    row = _active(baseline)
    changed, _ = engine.build_plan(data, settings, {'in_transit': {row.code: float(row.in_transit+row.qty)}})
    assert changed.set_index('code').loc[row.code,'qty'] < row.qty


@pytest.mark.parametrize('input_name', ['stock','class','growth','lead_time'])
def test_every_input_matters(baseline, input_name):
    data, settings, plan, _ = baseline
    overrides = {}
    if input_name == 'stock':
        overrides = {'stock': dict(zip(plan['code'], plan['available']+plan['qty']+100))}
    elif input_name == 'class':
        overrides = {'abc_class': {r.code: ('C' if r.abc_class == 'A' else 'A') for r in plan.itertuples()}}
    elif input_name == 'growth':
        settings = replace(settings, plan_growth_pct=40.)
    else:
        settings = replace(settings, lead_time_days={k:v+40 for k,v in settings.lead_time_days.items()})
    changed, _ = engine.build_plan(data, settings, overrides)
    assert (_quantities(changed) != _quantities(plan)).any(), input_name+' не влияет на рекомендации'


def _synthetic_seasonal_data():
    months = pd.period_range('2024-01','2026-09',freq='M')
    code, supplier = 'SYNTHETIC-DECEMBER', 'IEK'
    sales = pd.DataFrame([[supplier,code,m,300. if m.month == 12 else 100.] for m in months],
                         columns=['supplier','code','month','qty'])
    invoices = []
    for row in sales.loc[sales['month'].map(lambda m:m.year>=2025)].itertuples():
        for n in range(10):
            invoices.append([supplier,row.month.start_time+pd.Timedelta(days=n),f'SYN-{row.month}-{n}',code,'Сезонный товар','шт',row.qty/10])
    return {'sales_monthly':sales,
            'stock_monthly':pd.DataFrame([[supplier,code,m,1000.] for m in months],columns=['supplier','code','month','stock_start']),
            'invoices':pd.DataFrame(invoices,columns=['supplier','date','doc','code','name','unit','qty']),
            'in_transit':pd.DataFrame(columns=['supplier','code','qty','arrival_date']),
            'moq':pd.DataFrame([[supplier,code,1]],columns=['supplier','code','multiple']),
            'catalog':pd.DataFrame([[supplier,code,'SYN','Сезонный товар','Тестовая категория','шт','Регулярная',100.]],
                                   columns=['supplier','code','article','name','category','unit','status','price'])}


def test_seasonality(baseline):
    _, settings, _, details = baseline
    _, synthetic = engine.build_plan(_synthetic_seasonal_data(), settings)
    forecast = synthetic['SYNTHETIC-DECEMBER']['forecast']
    december = forecast.loc[forecast['month'].map(lambda m:m.month==12),'forecast'].iloc[0]
    june = forecast.loc[forecast['month'].map(lambda m:m.month==6),'forecast'].iloc[0]
    assert june > 0 and december/june >= 1.8
    real = details['280300035_']['forecast']['forecast']
    assert real.max() > real.min() and real.nunique() > 1


def test_stockout_raises_requirement(baseline):
    data, settings, plan, details = baseline
    without, _ = engine.build_plan(data, settings, {'disable_stockout_adjustment':True})
    affected = [c for c,d in details.items() if not d['stockouts'].empty]
    before = without.set_index('code').loc[affected,'qty']
    after = plan.set_index('code').loc[affected,'qty']
    assert (after > before).any(), 'Ни один товар с дефицитом не получил повышенный заказ'


@pytest.mark.parametrize('invoice_date', ['2026-08-15','2026-09-15'])
def test_one_off_order_ignored(baseline, invoice_date):
    data, settings, _, _ = baseline
    row = _active(baseline)
    changed, details = engine.build_plan(data, settings, {'extra_invoice_lines':[
        {'supplier':row.supplier,'code':row.code,'date':invoice_date,'qty':50*float(row.base_monthly)}]})
    after = changed.set_index('code').loc[row.code,'qty']
    assert after-row.qty < .1*row.qty+row.multiple
    # Prove the injected line was actually detected, not merely masked by stock.
    one_offs = details[row.code]['one_offs']
    assert ((one_offs['date'] == pd.Timestamp(invoice_date)) & (one_offs['doc'] == 'Проверка')).any()


def test_every_row_explained_and_filterable(baseline):
    _, _, plan, _ = baseline
    assert not plan.empty
    assert plan['reason'].fillna('').astype(str).str.strip().ne('').all()
    counts = []
    for supplier in engine.SUPPLIERS:
        filtered = plan.loc[plan['supplier'].eq(supplier)]
        assert not filtered.empty and filtered['supplier'].eq(supplier).all()
        counts.append(len(filtered))
    assert sum(counts) == len(plan)
