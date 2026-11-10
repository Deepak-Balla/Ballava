import React, { useState } from 'react';
import { getCatalog, WEEKDAYS } from '../catalog.js';
import { api } from '../lib.js';
import { Header, Empty, ingName } from '../ui.jsx';
import { t } from '../i18n.js';

const ALLERGIES = ['dairy', 'gluten', 'nuts', 'egg', 'seafood'];
const blank = { name: '', diet: 'nonveg', jain: false, noOnionGarlic: false, diabetic: false, fasting: false, allergies: [], spice: 2, age: 'adult', goals: [], fastWeekdays: [], tiffin: false, likes: [], dislikes: [] };
const toggle = (list, v) => (list.includes(v) ? list.filter(x => x !== v) : [...list, v]);

export default function Family({ members, setMembers, notify }) {
  const { goals: GOALS, ageGroups: AGE_GROUPS } = getCatalog();
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [likes, setLikes] = useState('');
  const [dislikes, setDislikes] = useState('');
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function save(e) {
    e.preventDefault();
    const name = form.name.trim();
    if (!name) { notify('Please enter a name'); return; }
    const parse = async text => (text.trim() ? (await api('parse', { text })).found : []);
    let liked, disliked;
    try { [liked, disliked] = await Promise.all([parse(likes), parse(dislikes)]); } catch (err) { notify(err.message); return; }
    const m = { ...form, name, likes: liked, dislikes: disliked };
    if (editing !== null) setMembers(members.map((x, i) => (i === editing ? m : x)));
    else setMembers([...members, m]);
    notify(editing !== null ? `Updated ${name}` : `Added ${name}. Dishes now suit them too.`);
    setForm(blank); setEditing(null); setLikes(''); setDislikes('');
  }

  function startEdit(m, i) {
    setForm({ ...blank, ...m }); setEditing(i);
    setLikes((m.likes || []).map(ingName).join(', ')); setDislikes((m.dislikes || []).map(ingName).join(', '));
  }

  const describe = m => [
    m.diet === 'veg' ? 'Vegetarian' : m.diet === 'egg' ? 'Eggetarian' : 'Eats everything',
    m.jain && 'Jain', m.noOnionGarlic && 'No onion/garlic', m.diabetic && 'Diabetic', m.fasting && 'Fasting today',
    m.allergies.length && 'Allergic: ' + m.allergies.join(', '), ['', 'Mild spice', 'Medium spice', 'Loves spice'][m.spice],
    m.age && m.age !== 'adult' && AGE_GROUPS.find(a => a[0] === m.age)?.[1],
    ...(m.goals || []).map(g => GOALS.find(x => x[0] === g)?.[1]), m.tiffin && 'Takes tiffin',
    m.fastWeekdays?.length && 'Fasts ' + m.fastWeekdays.map(d => WEEKDAYS[d]).join(', '),
    m.dislikes?.length && 'Dislikes ' + m.dislikes.map(ingName).join(', '),
  ].filter(Boolean).join(' · ');

  return (
    <div className="screen">
      <Header title={t('Family')} back="more" />
      <p className="muted">Add who you cook for. Ballava then only suggests dishes that work for everyone, and tells you when to take out a mild portion.</p>
      {members.length === 0 && <Empty title="No one added yet">Cooking just for yourself? You can skip this.</Empty>}
      <div className="members">
        {members.map((m, i) => (
          <div key={i} className="member card">
            <div><b>{m.name}</b><div className="muted small">{describe(m)}</div></div>
            <div className="row">
              <label className="switch small"><input type="checkbox" checked={m.fasting} onChange={e => setMembers(members.map((x, k) => (k === i ? { ...x, fasting: e.target.checked } : x)))} /> Fasting today</label>
              <button className="btn link" onClick={() => startEdit(m, i)}>Edit</button>
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
        <label>Age group
          <select value={form.age} onChange={e => set('age', e.target.value)}>
            {AGE_GROUPS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <fieldset><legend>Health goals</legend>
          <div className="chips wrap">
            {GOALS.map(([id, label]) => <button type="button" key={id} className={'chip' + (form.goals.includes(id) ? ' on' : '')} aria-pressed={form.goals.includes(id)} onClick={() => set('goals', toggle(form.goals, id))}>{label}</button>)}
          </div>
        </fieldset>
        <fieldset><legend>Fasts every week on</legend>
          <div className="chips wrap">
            {WEEKDAYS.map((d, i) => <button type="button" key={d} className={'chip' + (form.fastWeekdays.includes(i) ? ' on' : '')} aria-pressed={form.fastWeekdays.includes(i)} onClick={() => set('fastWeekdays', toggle(form.fastWeekdays, i))}>{d}</button>)}
          </div>
        </fieldset>
        <label className="check"><input type="checkbox" checked={form.tiffin} onChange={e => set('tiffin', e.target.checked)} /> Takes a tiffin on school or work days</label>
        <label>Loves<input value={likes} onChange={e => setLikes(e.target.value)} placeholder="e.g. paneer, aloo" /></label>
        <label>Doesn't like<input value={dislikes} onChange={e => setDislikes(e.target.value)} placeholder="e.g. karela, baingan" /></label>
        <div className="row">
          <button className="btn primary" type="submit">{editing !== null ? 'Save changes' : 'Add member'}</button>
          {editing !== null && <button type="button" className="btn link" onClick={() => { setForm(blank); setEditing(null); setLikes(''); setDislikes(''); }}>Cancel</button>}
        </div>
      </form>
      <p className="muted small">Allergy matching is a helper, not a guarantee. Always check packaged ingredients' labels. Health goals only guide suggestions and are not medical advice, so please follow your doctor or dietitian.</p>
    </div>
  );
}
