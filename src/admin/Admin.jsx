// The admin portal, served at /admin. A separate page, login and cookie from the user app.
// Every action here is also checked on the server, so this page cannot grant any access itself.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CATEGORIES } from '../../shared/ingredients.mjs';

async function call(path, body) {
  const res = await fetch('/api/admin/' + path, body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { status: res.status, data });
  return data;
}

const when = t => (t ? new Date(t).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '–');
const MEALS = ['breakfast', 'lunch', 'dinner', 'snack', 'side', 'dessert'];

function SignIn({ onDone }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  return (
    <div className="admin" style={{ maxWidth: 420 }}>
      <form className="card form" onSubmit={async e => {
        e.preventDefault(); setError('');
        try { const r = await call('login', { email, password }); onDone(r.admin); } catch (err) { setError(err.message); }
      }}>
        <h2>Ballava Admin</h2>
        <label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" required /></label>
        <label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required /></label>
        {error && <div className="note bad" role="alert">{error}</div>}
        <button className="btn primary big" type="submit">Sign in</button>
      </form>
    </div>
  );
}

function Overview() {
  const [s, setS] = useState(null);
  useEffect(() => { call('stats').then(setS).catch(() => {}); }, []);
  if (!s) return <p>Loading…</p>;
  const tiles = [['Users', s.users], ['Active in 7 days', s.activeWeek], ['Families', s.households], ['Meals logged', s.mealsLogged],
    ['Built-in recipes', s.recipesBuiltIn], ['Custom recipes live', s.recipesCustom], ['Waiting for review', s.recipesWaiting], ['AI calls, 30 days', s.aiCalls30d]];
  return (
    <>
      <div className="admin-grid">{tiles.map(([l, v]) => <div key={l} className="admin-tile"><b>{v}</b>{l}</div>)}</div>
      {s.aiByDay.length > 0 && (
        <div className="card"><h3>AI use by day</h3>
          <div className="table-wrap"><table><thead><tr><th>Day</th><th>Calls</th></tr></thead><tbody>
            {s.aiByDay.map(d => <tr key={d.day}><td>{d.day}</td><td>{d.calls}</td></tr>)}
          </tbody></table></div>
        </div>
      )}
    </>
  );
}

const blankRecipe = { id: '', name: '', alt: '', cuisine: '', meal: ['lunch', 'dinner'], time: 30, serves: 3, spice: 2, tags: [], ing: [], steps: [], prep: '', safety: '', tip: '' };

function RecipeEditor({ start, row, onClose, onSaved, say }) {
  const [r, setR] = useState({ ...blankRecipe, ...start });
  const [ing, setIng] = useState((start.ing || []).join('\n'));
  const [steps, setSteps] = useState((start.steps || []).join('\n'));
  const [tags, setTags] = useState((start.tags || []).join(', '));
  const [errors, setErrors] = useState([]);
  const [status, setStatus] = useState(row?.source === 'custom' || row?.status !== 'published' ? row?.status : null);
  const set = (k, v) => setR(x => ({ ...x, [k]: v }));
  const lines = s => s.split('\n').map(x => x.trim()).filter(Boolean);

  async function save() {
    const recipe = { ...r, time: Number(r.time), serves: Number(r.serves), spice: Number(r.spice), ing: lines(ing), steps: lines(steps), tags: tags.split(',').map(x => x.trim()).filter(Boolean) };
    for (const k of ['alt', 'prep', 'safety', 'tip']) if (!recipe[k]) delete recipe[k];
    try {
      const out = await call('recipes', { recipe });
      setErrors(out.errors); setStatus('draft'); say(out.errors.length ? 'Saved as a draft, with problems to fix' : 'Saved as a draft'); onSaved();
      return true;
    } catch (e) { say(e.message); return false; }
  }

  async function move(next) {
    try { await call(`recipes/${r.id}/status`, { status: next }); setStatus(next); setErrors([]); say(next === 'published' ? 'Published. Users see it now.' : 'Sent for review'); onSaved(); } catch (e) { setErrors(e.data?.errors || [e.message]); }
  }

  return (
    <div className="card form">
      <div className="row between"><h3>{start.id ? `Edit ${start.name}` : 'New recipe'}</h3><button className="btn link" onClick={onClose}>Close</button></div>
      {status && <p>Status: <span className={'status ' + status}>{status}</span></p>}
      <label>Id (lowercase, no spaces)<input value={r.id} disabled={!!start.id} onChange={e => set('id', e.target.value)} /></label>
      <label>Name<input value={r.name} onChange={e => set('name', e.target.value)} /></label>
      <label>Other name<input value={r.alt || ''} onChange={e => set('alt', e.target.value)} /></label>
      <label>Cuisine<input value={r.cuisine || ''} onChange={e => set('cuisine', e.target.value)} /></label>
      <div className="row">
        <label>Minutes<input type="number" value={r.time} onChange={e => set('time', e.target.value)} /></label>
        <label>Serves<input type="number" value={r.serves} onChange={e => set('serves', e.target.value)} /></label>
        <label>Spice (1-3)<input type="number" min="1" max="3" value={r.spice} onChange={e => set('spice', e.target.value)} /></label>
      </div>
      <fieldset><legend>Meals</legend><div className="chips wrap">
        {MEALS.map(m => <button type="button" key={m} className={'chip' + (r.meal.includes(m) ? ' on' : '')} onClick={() => set('meal', r.meal.includes(m) ? r.meal.filter(x => x !== m) : [...r.meal, m])}>{m}</button>)}
      </div></fieldset>
      <label>Tags, comma separated (gluten-free, diabetic-friendly, high-protein, kid-friendly, tiffin, vrat, quick, sweet)<input value={tags} onChange={e => setTags(e.target.value)} /></label>
      <label>Ingredients, one per line. Format id:quantity. Add ? for optional, | for "any of"<textarea aria-label="Ingredients" value={ing} onChange={e => setIng(e.target.value)} placeholder={'rice:1 cup\nmoong_dal|masoor_dal:1/2 cup\nghee?:1 tbsp'} /></label>
      <label>Steps, one per line. End with |5m for a timer, |3w for whistles<textarea aria-label="Steps" value={steps} onChange={e => setSteps(e.target.value)} /></label>
      <label>Plan ahead (night before)<input value={r.prep || ''} onChange={e => set('prep', e.target.value)} /></label>
      <label>Food safety note<input value={r.safety || ''} onChange={e => set('safety', e.target.value)} /></label>
      <label>Tip<input value={r.tip || ''} onChange={e => set('tip', e.target.value)} /></label>
      {errors.length > 0 && <div className="note bad" role="alert"><b>Fix before publishing:</b><ul>{errors.map(e => <li key={e}>{e}</li>)}</ul></div>}
      <div className="row">
        <button className="btn primary" onClick={save}>Save draft</button>
        {status === 'draft' && <button className="btn" onClick={() => move('review')}>Send to review</button>}
        {status === 'review' && <button className="btn primary" onClick={() => move('published')}>Publish</button>}
      </div>
    </div>
  );
}

function Recipes({ say }) {
  const [rows, setRows] = useState([]);
  const [q, setQ] = useState('');
  const [editing, setEditing] = useState(null);
  const load = useCallback(() => call('recipes').then(d => setRows(d.recipes)).catch(e => say(e.message)), [say]);
  useEffect(() => { load(); }, [load]);
  const shown = useMemo(() => rows.filter(r => r.name.toLowerCase().includes(q.toLowerCase())), [rows, q]);
  const hide = async r => { await call(`recipes/${r.id}/hide`, { hidden: !r.hidden }); say(r.hidden ? `${r.name} is visible again` : `${r.name} is hidden from users`); load(); };
  if (editing) {
    const row = rows.find(x => x.id === editing.id);
    return <RecipeEditor key={editing.id || 'new'} start={editing} row={row} say={say} onSaved={load} onClose={() => setEditing(null)} />;
  }
  return (
    <>
      <div className="row between">
        <input aria-label="Search recipes" placeholder={`Search ${rows.length} recipes`} value={q} onChange={e => setQ(e.target.value)} />
        <button className="btn primary" onClick={() => setEditing({})}>+ New recipe</button>
      </div>
      <div className="table-wrap"><table>
        <thead><tr><th>Recipe</th><th>Cuisine</th><th>Source</th><th>Status</th><th /></tr></thead>
        <tbody>{shown.map(r => (
          <tr key={r.id}>
            <td>{r.name}{r.hidden && <span className="muted small"> (hidden)</span>}</td><td>{r.cuisine}</td><td>{r.source}</td>
            <td><span className={'status ' + r.status}>{r.status}</span></td>
            <td className="row"><button className="btn link" onClick={() => setEditing(r.data)}>Edit</button><button className="btn link" onClick={() => hide(r)}>{r.hidden ? 'Show' : 'Hide'}</button></td>
          </tr>
        ))}</tbody>
      </table></div>
    </>
  );
}

const CONTENT = {
  ingredient: { label: 'Ingredients', fields: [['id', 'Id'], ['name', 'Name'], ['category', 'Category', CATEGORIES], ['shelfDays', 'Keeps for (days)'], ['aliases', 'Other names, comma separated'], ['allergens', 'Allergens, comma separated'], ['diet', 'Diet', ['veg', 'egg', 'nonveg']]], title: x => x.name },
  rescue: { label: 'Bachao fixes', fields: [['id', 'Id'], ['title', 'Problem'], ['keywords', 'Search words'], ['fixes', 'Fixes, one per line', 'area'], ['myth', 'Myth check']], title: x => x.title },
  announcement: { label: 'Announcements', fields: [['id', 'Id'], ['text', 'Message'], ['active', 'Show to users', 'bool']], title: x => `${x.text}${x.active ? '' : ' (off)'}` },
  festival: { label: 'Festival calendar', hint: 'Dates change every year and vary by region, so please check them against your panchang.', fields: [['id', 'Id'], ['name', 'Name'], ['date', 'Date (YYYY-MM-DD)'], ['fast', 'Fasting day', 'bool']], title: x => `${x.date} ${x.name}${x.fast ? ' (fast)' : ''}` },
};

function Content({ kind, say }) {
  const spec = CONTENT[kind];
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({});
  const load = useCallback(() => call('content/' + kind).then(d => setItems(d.items)).catch(e => say(e.message)), [kind, say]);
  useEffect(() => { load(); setForm({}); }, [load]);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  return (
    <>
      {spec.hint && <div className="note info">{spec.hint}</div>}
      <form className="card form" onSubmit={async e => {
        e.preventDefault();
        try { await call('content/' + kind, { data: form }); say('Saved. Users get this on their next visit.'); setForm({}); load(); } catch (err) { say(err.message); }
      }}>
        <h3>Add to {spec.label.toLowerCase()}</h3>
        {spec.fields.map(([k, label, type]) => (
          type === 'bool' ? <label key={k} className="check"><input type="checkbox" checked={!!form[k]} onChange={e => set(k, e.target.checked)} /> {label}</label>
            : type === 'area' ? <label key={k}>{label}<textarea value={form[k] || ''} onChange={e => set(k, e.target.value)} /></label>
              : Array.isArray(type) ? <label key={k}>{label}<select value={form[k] || ''} onChange={e => set(k, e.target.value)}><option value="">Choose…</option>{type.map(o => <option key={o}>{o}</option>)}</select></label>
                : <label key={k}>{label}<input value={form[k] ?? ''} onChange={e => set(k, e.target.value)} /></label>
        ))}
        <button className="btn primary" type="submit">Save</button>
      </form>
      <div className="table-wrap"><table><tbody>
        {items.length === 0 && <tr><td className="muted">Nothing here yet.</td></tr>}
        {items.map(x => (
          <tr key={x.id}><td>{spec.title(x)}</td><td className="row">
            <button className="btn link" onClick={() => setForm({ ...x, aliases: x.aliases?.join(', '), allergens: x.allergens?.join(', '), fixes: x.fixes?.join('\n') })}>Edit</button>
            <button className="btn link danger" onClick={async () => { await call(`content/${kind}/delete`, { id: x.id }); load(); }}>Delete</button>
          </td></tr>
        ))}
      </tbody></table></div>
    </>
  );
}

function Users({ say }) {
  const [users, setUsers] = useState([]);
  const load = useCallback(() => call('users').then(d => setUsers(d.users)).catch(e => say(e.message)), [say]);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <p className="muted small">Family, diet and health details are private and are not available here.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Name</th><th>Contact</th><th>Family size</th><th>Joined</th><th>Last seen</th><th /></tr></thead>
        <tbody>{users.map(u => (
          <tr key={u.id}><td>{u.name}{u.disabled && <span className="danger small"> (disabled)</span>}</td><td>{u.contact}</td><td>{u.householdSize}</td><td>{when(u.joined)}</td><td>{when(u.lastSeen)}</td>
            <td><button className={'btn link' + (u.disabled ? '' : ' danger')} onClick={async () => { await call(`users/${u.id}/disable`, { disabled: !u.disabled }); load(); }}>{u.disabled ? 'Enable' : 'Disable'}</button></td></tr>
        ))}</tbody>
      </table></div>
    </>
  );
}

function Audit() {
  const [rows, setRows] = useState([]);
  useEffect(() => { call('audit').then(d => setRows(d.entries)).catch(() => {}); }, []);
  return (
    <div className="table-wrap"><table>
      <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Item</th></tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}><td>{new Date(r.at).toLocaleString('en-IN')}</td><td>{r.name}</td><td>{r.action}</td><td>{r.target}</td></tr>)}</tbody>
    </table></div>
  );
}

export default function Admin() {
  const [admin, setAdmin] = useState(undefined);
  const [tab, setTab] = useState('overview');
  const [message, setMessage] = useState('');
  const say = useCallback(m => { setMessage(m); setTimeout(() => setMessage(''), 3500); }, []);
  useEffect(() => { call('me').then(d => setAdmin(d.admin)).catch(() => setAdmin(null)); }, []);

  if (admin === undefined) return null;
  if (!admin) return <SignIn onDone={setAdmin} />;

  const tabs = [['overview', 'Overview'], ['recipes', 'Recipes'], ...Object.entries(CONTENT).map(([k, v]) => [k, v.label]), ['users', 'Users'], ['audit', 'Audit log']];
  return (
    <div className="admin">
      <header className="admin-head">
        <span className="brand-mark">B</span><h1>Ballava Admin</h1>
        <span className="muted small">{admin.email}</span>
        <button className="btn ghost sm" onClick={async () => { await call('logout', {}); setAdmin(null); }}>Sign out</button>
      </header>
      <nav className="admin-nav" aria-label="Admin">
        {tabs.map(([id, label]) => <button key={id} className={'chip' + (tab === id ? ' on' : '')} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}
      </nav>
      {tab === 'overview' && <Overview />}
      {tab === 'recipes' && <Recipes say={say} />}
      {CONTENT[tab] && <Content key={tab} kind={tab} say={say} />}
      {tab === 'users' && <Users say={say} />}
      {tab === 'audit' && <Audit />}
      {message && <div className="toast" role="status">{message}</div>}
    </div>
  );
}
