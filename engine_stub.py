"""Small deterministic fixture engine for preview only, not purchasing decisions."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
import math
import pandas as pd

SUPPLIERS = ['Systeme Electric', 'IEK']
IS_STUB = True

@dataclass
class Settings:
    today: date = date(2026, 9, 22)
    demand_source: str = 'invoices'
    lead_time_days: dict = field(default_factory=lambda: {'IEK': 35, 'Systeme Electric': 30})
    review_days: dict = field(default_factory=lambda: {'IEK': 14, 'Systeme Electric': 30})
    service_z: dict = field(default_factory=lambda: {'A': 1.65, 'B': 1.28, 'C': .84})
    plan_growth_pct: float = 0.0


def load_all(data_dir: str = 'data') -> dict:
    catalog = pd.DataFrame([
        ['IEK', '280300035_', 'CLP-100', 'Лоток перфорированный', 'Лотки', 'шт', 'Регулярная', 2500],
        ['IEK', '130200032_', 'RAr10', 'Розетка на DIN-рейку', 'Розетки', 'шт', 'Регулярная', 1200],
        ['Systeme Electric', '300200327_', 'BLN-4', 'Розетка BLANCA', 'BLANCA', 'шт', '', 1800],
    ], columns=['supplier', 'code', 'article', 'name', 'category', 'unit', 'status', 'price'])
    sales, stocks, invoices = [], [], []
    for product in catalog.itertuples():
        for month in pd.period_range('2024-01', '2026-09', freq='M'):
            qty = 240 if month.month == 4 else 100
            stock = 0 if product.code == '130200032_' and month in pd.period_range('2026-03', '2026-06', freq='M') else 200
            qty = 20 if stock == 0 else qty
            sales.append([product.supplier, product.code, month, qty])
            stocks.append([product.supplier, product.code, month, stock])
            if month.year >= 2025:
                for n in range(10):
                    invoices.append([product.supplier, month.start_time + pd.Timedelta(days=n),
                                     f'ДЕМО-{month}-{n}', product.code, product.name, product.unit, qty / 10])
    return {'catalog': catalog,
            'sales_monthly': pd.DataFrame(sales, columns=['supplier', 'code', 'month', 'qty']),
            'stock_monthly': pd.DataFrame(stocks, columns=['supplier', 'code', 'month', 'stock_start']),
            'invoices': pd.DataFrame(invoices, columns=['supplier', 'date', 'doc', 'code', 'name', 'unit', 'qty']),
            'in_transit': pd.DataFrame([[r.supplier, r.code, 20., date(2026, 9, 24)] for r in catalog.itertuples()],
                                       columns=['supplier', 'code', 'qty', 'arrival_date']),
            'moq': pd.DataFrame([[r.supplier, r.code, 10] for r in catalog.itertuples()], columns=['supplier', 'code', 'multiple'])}


def build_plan(data: dict, settings: Settings, overrides: dict | None = None):
    overrides = overrides or {}
    rows, details = [], {}
    for product in data['catalog'].itertuples():
        code = product.code
        history = data['sales_monthly'].loc[data['sales_monthly']['code'].eq(code)].set_index('month')['qty']
        history = history[history.index < pd.Period(settings.today, freq='M')]
        history = pd.DataFrame({'raw': history, 'cleaned': history, 'adjusted': history}, dtype=float)
        history['stock_start'] = data['stock_monthly'].loc[data['stock_monthly']['code'].eq(code)].set_index('month')['stock_start']
        stockouts = []
        for month in history.tail(12).index:
            if history.loc[month, 'stock_start'] == 0:
                actual = float(history.loc[month, 'cleaned'])
                stockouts.append([month, actual, 100., 100.-actual])
                if not overrides.get('disable_stockout_adjustment', False):
                    history.loc[month, 'adjusted'] = 100.
        one_offs = []
        for line in overrides.get('extra_invoice_lines', []):
            if line['code'] != code or line.get('supplier', product.supplier) != product.supplier:
                continue
            timestamp = pd.Timestamp(line['date'])
            month = timestamp.to_period('M')
            if month in history.index:
                history.loc[month, 'raw'] += line['qty']
            if line['qty'] > 200 and not overrides.get('disable_one_off_filter', False):
                one_offs.append([timestamp, 'ДЕМО-ПРОВЕРКА', float(line['qty']), 10.])
            elif month in history.index:
                history.loc[month, ['cleaned', 'adjusted']] += line['qty']
        factors = [1.] * 12
        factors[3] = 2.4
        factors = [x / (sum(factors) / 12) for x in factors]
        base = float(history['adjusted'].tail(6).mean())
        forecast = pd.DataFrame({'month': pd.period_range(pd.Period(settings.today, freq='M'), periods=12, freq='M')})
        forecast['forecast'] = [base * factors[m.month-1] * (1+settings.plan_growth_pct/100) for m in forecast['month']]
        available = float(overrides.get('stock', {}).get(code, 30.))
        transit = float(overrides.get('in_transit', {}).get(code, 20.))
        cls = overrides.get('abc_class', {}).get(code, 'A')
        window = settings.lead_time_days[product.supplier] + settings.review_days[product.supplier]
        demand = base * window / 30 * (1+settings.plan_growth_pct/100)
        safety = settings.service_z[cls] * base * .2 * math.sqrt(window/30)
        raw = max(0., demand+safety-available-transit)
        qty = int(math.ceil(raw/10)*10)
        urgency = '🔴 Критично' if available+transit < demand/window*settings.lead_time_days[product.supplier] else ('🟡 Заказать' if qty else '🟢 Не требуется')
        rows.append(dict(supplier=product.supplier, code=code, article=product.article, name=product.name,
                         category=product.category, abc_class=cls, unit=product.unit, available=available,
                         in_transit=transit, next_arrival=date(2026,9,24), base_monthly=base, trend=0.,
                         window_days=window, window_demand=demand, safety_stock=safety, raw_qty=raw,
                         multiple=10, qty=qty, urgency=urgency,
                         enough_until=settings.today+timedelta(days=int((available+transit)/(demand/window))) if demand else None,
                         price=product.price, value=qty*product.price, do_not_reorder=False,
                         reason=f'ДЕМОДАННЫЕ. Спрос {base:.0f} шт/мес; запас {available:g}, в пути {transit:g}; кратность 10.'))
        details[code] = dict(history=history, season_factors=factors, season_level='product', forecast=forecast,
                             one_offs=pd.DataFrame(one_offs,columns=['date','doc','qty','typical_qty']),
                             stockouts=pd.DataFrame(stockouts,columns=['month','actual','expected','lost']))
    return pd.DataFrame(rows), details
