import React from 'react';

const ratios = [['current_ratio', 'Current ratio'], ['quick_ratio', 'Quick ratio'],
  ['debt_equity', 'Debt / equity'], ['interest_coverage', 'Interest coverage'],
  ['net_margin', 'Net margin'], ['ebitda_margin', 'EBITDA margin']];

export default function FinancialHistory({ rows = [] }) {
  if (!rows.length) return <p className="text-xs text-ink-500">Annual financial history unavailable. Obtain statements and audit opinions for review.</p>;
  return <div className="space-y-3">
    <h3 className="text-sm text-ink-200">Annual financial history</h3>
    <p className="text-xs text-ink-500">Retrieved aggregator statements; auditor opinions have not been verified. Missing ratios remain unassessed.</p>
    <div className="overflow-auto"><table className="w-full text-left text-xs text-ink-300">
      <thead><tr><th className="p-2">Ratio</th>{rows.map(row => <th key={row.fiscal_period_end} className="p-2">{row.fiscal_period_end}</th>)}</tr></thead>
      <tbody>{ratios.map(([key, label]) => <tr key={key} className="border-t border-border">
        <td className="p-2">{label}</td>{rows.map(row => <td key={row.fiscal_period_end} className="p-2 font-mono">{Number.isFinite(row[key]) ? row[key] : 'Not available'}</td>)}
      </tr>)}</tbody>
    </table></div>
    {rows.map(row => <p className="text-xs text-ink-500" key={row.fiscal_period_end}>
      {row.fiscal_period_end} · {row.source} · Retrieved {row.retrieved_at}
      {/^https:\/\//.test(row.source_url || '') && <> · <a className="text-accent-text" href={row.source_url} target="_blank" rel="noopener noreferrer">Source</a></>}
    </p>)}
  </div>;
}
