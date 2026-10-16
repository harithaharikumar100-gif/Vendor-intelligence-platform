import React, { useEffect, useState } from 'react';

export default function ReviewPanel({ apiFetch, result, onLoad }) {
  const [queue, setQueue] = useState([]);
  const [notes, setNotes] = useState('');
  const [decision, setDecision] = useState('needs_information');
  const [history, setHistory] = useState([]);
  const [settings, setSettings] = useState(null);
  const [message, setMessage] = useState('');
  useEffect(() => {setHistory([]); setNotes(''); setDecision('needs_information'); setMessage('');}, [result?.run_id]);
  async function request(path, options) {
    const response = await apiFetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request could not be completed.');
    return data;
  }
  async function run(action) {
    try {setMessage(''); await action();} catch (error) {setMessage(error.message);}
  }
  return <section className="panel p-6 my-6 space-y-4">
    <div className="flex flex-wrap gap-4 items-center">
      <h2 className="text-sm text-ink-50 font-medium">Review workspace</h2>
      <button className="text-xs text-accent-text" onClick={() => run(async () => setQueue(await request('/api/reviews')))}>Refresh review queue</button>
      <button className="text-xs text-accent-text" onClick={() => run(async () => {
        const data = await request('/api/admin/settings'); setSettings({...data, edited: {...data.active, ...data.pending}});
      })}>Administrator settings</button>
    </div>
    {message && <p role="status" className="text-sm text-amber-400">{message}</p>}
    {queue.length > 0 && <ul className="space-y-2 text-xs">
      {queue.map(item => <li key={item.run_id}>
        <button className="text-accent-text" onClick={() => run(async () => {
          onLoad(await request(`/api/runs/${item.run_id}`));
          setHistory(await request(`/api/runs/${item.run_id}/reviews`));
        })}>{item.vendor_name} · {item.run_status?.replaceAll('_', ' ')} · {item.review_status?.replaceAll('_', ' ')} · {item.query_date}</button>
      </li>)}
    </ul>}
    {result?.run_id && <>
      <p className="text-xs text-ink-500">Assessment {result.run_id}</p>
      <h3 className="text-sm text-ink-200">Source health for this assessment</h3>
      <div className="overflow-auto"><table className="w-full text-left text-xs text-ink-300">
        <thead><tr><th className="p-2">Source</th><th>Status</th><th>Retrieved</th></tr></thead>
        <tbody>{(result.source_ledger || []).map((source, i) => <tr key={i} className="border-t border-border">
          <td className="p-2">{source.source}</td><td>{(source.status || 'unknown').replaceAll('_', ' ')}</td><td>{source.retrieved_at || 'Not retrieved'}</td>
        </tr>)}</tbody>
      </table></div>
      <label className="block text-xs text-ink-400">Reviewer notes
        <textarea value={notes} onChange={e => setNotes(e.target.value)} minLength={10} maxLength={10000}
          className="block w-full mt-2 p-3 bg-surface border border-border rounded text-ink-200" rows={3} />
      </label>
      <div className="flex gap-3">
        <select value={decision} onChange={e => setDecision(e.target.value)} className="bg-surface text-xs text-ink-200 p-2 border border-border rounded">
          <option value="needs_information">Needs more information</option>
          <option value="reviewed">Reviewed — observations recorded</option>
          <option value="approve" disabled={!!result.completion_blockers?.length || !Number.isFinite(result.overall_score)}>Approve completed assessment</option>
        </select>
        <button disabled={notes.trim().length < 10} className="text-xs text-accent-text disabled:opacity-40" onClick={() => run(async () => {
          await request(`/api/runs/${result.run_id}/reviews`, {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({decision, notes})});
          setHistory(await request(`/api/runs/${result.run_id}/reviews`));
          setNotes(''); setMessage('Review saved. The original assessment and report remain available.');
        })}>Save review</button>
      </div>
      {history.map(event => <article key={event.review_id} className="text-xs border-t border-border pt-2 text-ink-300">
        <p>{event.created_at} · {event.reviewer} · {event.decision.replaceAll('_', ' ')}</p><p>{event.notes}</p>
      </article>)}
    </>}
    {settings && <div className="border-t border-border pt-4 space-y-3">
      <p className="text-xs text-ink-400">Changes are saved for application restart. Existing reports retain their original assessment.</p>
      <div className="grid md:grid-cols-2 gap-3">{Object.entries(settings.edited).map(([key, value]) => <label key={key} className="text-xs text-ink-400">
        {key.toLowerCase().replaceAll('_', ' ')}
        <input type="number" min={settings.ranges[key][0]} max={settings.ranges[key][1]} step={['RECENCY_MULTIPLIER_12M', 'MIN_CVSS_SCORE'].includes(key) ? '0.1' : '1'} value={value}
          onChange={e => setSettings({...settings, edited: {...settings.edited, [key]: Number(e.target.value)}})}
          className="ml-2 w-24 p-2 border border-border bg-surface rounded text-ink-200" />
      </label>)}</div>
      <button className="text-xs text-accent-text" onClick={() => run(async () => {
        await request('/api/admin/settings', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(settings.edited)});
        setMessage('Settings saved. Restart the application to apply them.');
      })}>Save settings</button>
    </div>}
  </section>;
}
