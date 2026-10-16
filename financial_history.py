"""Three-year ratio history from retrieved annual statements, with explicit provenance.

Aggregator statements are not represented as an auditor's opinion or an audited filing.
"""
import math
from urllib.parse import quote
from evidence import now_utc


def annual_history(income, balance, ticker):
    def number(frame, names, period):
        for name in names:
            try:
                value = float(frame.loc[name, period])
                if math.isfinite(value):
                    return value
            except (KeyError, TypeError, ValueError):
                continue
        return None

    def ratio(numerator, denominator):
        return round(numerator / denominator, 4) if numerator is not None and denominator not in (None, 0) else None

    result = []
    for period in sorted(income.columns, reverse=True)[:3]:
        revenue = number(income, ['Total Revenue', 'Operating Revenue'], period)
        net_income = number(income, ['Net Income'], period)
        ebitda = number(income, ['EBITDA', 'Normalized EBITDA'], period)
        interest = number(income, ['Interest Expense', 'Interest Expense Non Operating'], period)
        ebit = number(income, ['EBIT', 'Operating Income'], period)
        assets = number(balance, ['Current Assets'], period)
        liabilities = number(balance, ['Current Liabilities'], period)
        inventory = number(balance, ['Inventory'], period)
        debt = number(balance, ['Total Debt'], period)
        equity = number(balance, ['Stockholders Equity', 'Common Stock Equity'], period)
        result.append({
            'fiscal_period_end': period.date().isoformat(), 'revenue': revenue, 'net_income': net_income,
            'ebitda': ebitda, 'retained_earnings': number(balance, ['Retained Earnings'], period),
            'equity': equity, 'current_ratio': ratio(assets, liabilities),
            'quick_ratio': ratio(assets - inventory if assets is not None and inventory is not None else None, liabilities),
            'debt_equity': ratio(debt, equity), 'interest_coverage': ratio(ebit, abs(interest) if interest is not None else None),
            'net_margin': ratio(net_income, revenue), 'ebitda_margin': ratio(ebitda, revenue),
            'source': 'Yahoo Finance annual statements (via yfinance)',
            'source_url': f'https://finance.yahoo.com/quote/{quote(ticker, safe="")}/financials/',
            'retrieved_at': now_utc().isoformat(), 'audit_status': 'auditor_opinion_not_verified',
        })
    return result


def history_signals(history):
    """Only observations supported by the required fiscal periods generate signals."""
    from evidence import source_id
    events = []
    rows = sorted(history, key=lambda r: r['fiscal_period_end'], reverse=True)
    def add(row, indicator, severity):
        events.append({'event_id': source_id(row['source_url'] + indicator), 'category': 'Financial ratio',
                       'indicator': indicator, 'severity': severity, 'event_date': row['fiscal_period_end'],
                       'sources': [row['source_url']], 'url': row['source_url'], 'source': row['source'],
                       'retrieved_at': row['retrieved_at'], 'verification_status': 'source_linked',
                       'review_required': True, 'resolution': 'unknown'})
    if not rows:
        return events
    current = rows[0]
    for field, threshold, severity, lower in [('current_ratio', 1, 'Elevated', True),
                                             ('quick_ratio', 0.5, 'High', True), ('debt_equity', 3, 'High', False)]:
        value = current.get(field)
        if value is not None and ((value < threshold) if lower else (value > threshold)):
            add(current, f'{field}: {value} at {current["fiscal_period_end"]}; threshold {threshold}.', severity)
    if len(rows) >= 2:
        # Require adjacent fiscal years; two nonconsecutive negative periods are insufficient.
        from datetime import date
        days = (date.fromisoformat(rows[0]['fiscal_period_end']) - date.fromisoformat(rows[1]['fiscal_period_end'])).days
        consecutive = 330 <= days <= 400
        if consecutive and all(r.get('ebitda') is not None and r['ebitda'] < 0 for r in rows[:2]):
            add(current, 'Negative EBITDA in two consecutive annual periods: ' + ', '.join(r['fiscal_period_end'] for r in rows[:2]), 'Critical')
        if consecutive and all(r.get('retained_earnings') is not None and r['retained_earnings'] < 0 for r in rows[:2]):
            add(current, 'Negative retained earnings in two consecutive annual periods.', 'High')
        old, new = rows[1].get('net_margin'), current.get('net_margin')
        if consecutive and old is not None and new is not None and old > 0 and (old - new) / old > .5:
            add(current, 'Net margin declined by more than 50% year-on-year.', 'Elevated')
    return events
