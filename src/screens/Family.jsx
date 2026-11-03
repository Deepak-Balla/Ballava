import React, { useState } from 'react';
import { Header, Empty } from '../ui.jsx';

const ALLERGIES = ['dairy', 'gluten', 'nuts', 'egg', 'seafood'];
const blank = { name: '', diet: 'nonveg', jain: false, noOnionGarlic: false, diabetic: false, fasting: false, allergies: [], spice: 2 };

export default function Family({ members, setMembers, notify }) {
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  function save(e) {
    e.preventDefault();
    const name = form.name.trim();
    if (!name) { notify('Please enter a name'); return; }
    const m = { ...form, name };
    if (editing !== null) setMembers(members.map((x, i) => (i === editing ? m : x)));
    else setMembers([...members, m]);
    notify(editing !== null ? `Updated ${name}` : `Added ${name}. Dishes now suit them too.`);
    setForm(blank); setEditing(null);
  }

  const describe = m => [
    m.diet === 'veg' ? 'Vegetarian' : m.diet === 'egg' ? 'Eggetarian' : 'Eats everything',
    m.jain && 'Jain', m.noOnionGarlic && 'No onion/garlic', m.diabetic && 'Diabetic', m.fasting && 'Fasting today',
    m.allergies.length && 'Allergic: ' + m.allergies.join(', '), ['', 'Mild spice', 'Medium spice', 'Loves spice'][m.spice],
  ].filter(Boolean).join(' · ');

  return (
    <div className="screen">
      <Header title="Family" />
      <p className="muted">Add who you cook for. Ballava then only suggests dishes that work for everyone, and tells you when to take out a mild portion.</p>
      {members.length === 0 && <Empty title="No one added yet">Cooking just for yourself? You can skip this.</Empty>}
      <div className="members">
        {members.map((m, i) => (
          <div key={i} className="member card">
            <div><b>{m.name}</b><div className="muted small">{describe(m)}</div></div>
            <div className="row">
              <label className="switch small"><input type="checkbox" checked={m.fasting} onChange={e => setMembers(members.map((x, k) => (k === i ? { ...x, fasting: e.target.checked } : x)))} /> Fasting today</label>
              <button className="btn link" onClick={() => { setForm(m); setEditing(i); }}>Edit</button>
              <button className="btn link danger" onClick={() => setMembers(members.filter((_, k) => k !== i))}>Remove</button>
            </div>
          </div>
        ))}
      </div>

      <form className="card form" onSubmit={save}>
        <h3>{editing !== null ? `Edit ${members[editing]?.name}` : 'Add a family member'}</h3>
        <label>Name<input value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Amma" /></label>
        <label>Food habit
          <select value={form.diet} onChange={e => set('diet', e.target.value)}>
            <option value="nonveg">Eats everything</option>
            <option value="egg">Vegetarian + egg</option>
            <option value="veg">Vegetarian</option>
          </select>
        </label>
        <div className="checks">
          <label className="check"><input type="checkbox" checked={form.jain} onChange={e => set('jain', e.target.checked)} /> Jain</label>
          <label className="check"><input type="checkbox" checked={form.noOnionGarlic} onChange={e => set('noOnionGarlic', e.target.checked)} /> No onion/garlic</label>
          <label className="check"><input type="checkbox" checked={form.diabetic} onChange={e => set('diabetic', e.target.checked)} /> Diabetic</label>
          <label className="check"><input type="checkbox" checked={form.fasting} onChange={e => set('fasting', e.target.checked)} /> Fasting today</label>
        </div>
        <fieldset><legend>Allergies</legend>
          <div className="chips wrap">
            {ALLERGIES.map(a => (
              <button type="button" key={a} className={'chip' + (form.allergies.includes(a) ? ' on' : '')} aria-pressed={form.allergies.includes(a)}
                onClick={() => set('allergies', form.allergies.includes(a) ? form.allergies.filter(x => x !== a) : [...form.allergies, a])}>{a}</button>
            ))}
          </div>
        </fieldset>
        <label>Spice level
          <select value={form.spice} onChange={e => set('spice', Number(e.target.value))}>
            <option value={1}>Mild</option><option value={2}>Medium</option><option value={3}>Loves spice</option>
          </select>
        </label>
        <div className="row">
          <button className="btn primary" type="submit">{editing !== null ? 'Save changes' : 'Add member'}</button>
          {editing !== null && <button type="button" className="btn link" onClick={() => { setForm(blank); setEditing(null); }}>Cancel</button>}
        </div>
      </form>
      <p className="muted small">Allergy matching is a helper, not a guarantee. Always check packaged ingredients' labels.</p>
    </div>
  );
}
