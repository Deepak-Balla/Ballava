import React, { useState } from 'react';
import { Header, ingName } from '../ui.jsx';
import { api, go, shrinkImage } from '../lib.js';

export default function AiChef({ aiStatus, pantry, members, aiRecipes, setAiRecipes, addToPantry, notify }) {
  const [wish, setWish] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [scan, setScan] = useState(null); // {found: [], unknown: []}
  const [pick, setPick] = useState(new Set());

  if (!aiStatus.ai) {
    return (
      <div className="screen">
        <Header title="✨ AI Chef" back />
        <div className="card">
          <h3>AI Chef is switched off</h3>
          <p>Everything else in Ballava works without AI. The AI Chef adds two extras:</p>
          <ul><li>Inventing brand-new dishes from exactly what's in your kitchen</li><li>Reading a photo of your fridge or shelf</li></ul>
          {aiStatus.server
            ? <p className="muted small">For the app owner: in the <code>.env</code> file, choose the AI with <code>AI_PROVIDER</code> (gemini or claude), add its key (<code>GEMINI_API_KEY</code> or <code>ANTHROPIC_API_KEY</code>), and restart the server. See the guide, step 8.</p>
            : <p className="muted small">This copy of Ballava is running without its server (for example, as an online demo), so AI features aren't available here.</p>}
        </div>
      </div>
    );
  }

  async function invent() {
    setBusy('invent'); setError('');
    try {
      const data = await api('ai/invent', {
        pantry: pantry.map(p => ingName(p.id)),
        household: members.map(m => ({ diet: m.diet, jain: m.jain, noOnionGarlic: m.noOnionGarlic, diabetic: m.diabetic, fasting: m.fasting, allergies: m.allergies, spice: m.spice })),
        wish,
      });
      const recipe = data.recipe; // already checked and cleaned by Python (engine.normalize_ai_recipe)
      setAiRecipes({ ...aiRecipes, [recipe.id]: recipe });
      go('recipe/' + recipe.id);
    } catch (e) { setError(e.message); }
    setBusy('');
  }

  async function onPhoto(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy('scan'); setError(''); setScan(null);
    try {
      const image = await shrinkImage(file);
      const data = await api('ai/scan', { image, mediaType: 'image/jpeg' });
      setScan(data); setPick(new Set(data.found));
    } catch (err) { setError(err.message); }
    setBusy(''); e.target.value = '';
  }

  return (
    <div className="screen">
      <Header title="✨ AI Chef" back />
      <div className="card">
        <h3>Invent a dish for me</h3>
        <p className="muted small">Uses your {pantry.length} kitchen items{members.length ? ' and your family\'s needs' : ''}.</p>
        <textarea value={wish} onChange={e => setWish(e.target.value)} rows={2} placeholder="Optional: 'something with paneer under 20 min', 'Chettinad style', 'kid's tiffin'…" />
        <button className="btn primary" onClick={invent} disabled={!!busy || !pantry.length}>{busy === 'invent' ? 'Thinking up something tasty…' : 'Create a recipe'}</button>
        {!pantry.length && <p className="muted small">Add a few things to your kitchen first.</p>}
      </div>

      <div className="card">
        <h3>Scan my fridge</h3>
        <p className="muted small">Take a photo of your fridge, shelf or vegetable basket. AI lists what it sees, and you confirm.</p>
        <label className="btn ghost file">{busy === 'scan' ? 'Looking at your photo…' : '📷 Take or choose a photo'}
          <input type="file" accept="image/*" capture="environment" onChange={onPhoto} disabled={!!busy} hidden />
        </label>
        {scan && (
          <div className="scan">
            {scan.found.length === 0 && <p>I couldn't spot any ingredients. Try a closer, brighter photo.</p>}
            <div className="chips wrap">
              {scan.found.map(id => (
                <button key={id} className={'chip' + (pick.has(id) ? ' on' : '')} onClick={() => { const n = new Set(pick); n.has(id) ? n.delete(id) : n.add(id); setPick(n); }}>
                  {pick.has(id) ? '✓ ' : ''}{ingName(id)}
                </button>
              ))}
            </div>
            {scan.unknown?.length > 0 && <p className="muted small">Also saw: {scan.unknown.join(', ')}</p>}
            {pick.size > 0 && <button className="btn primary" onClick={() => { const a = addToPantry([...pick]); notify(`Added ${a.length} item(s) to your kitchen`); setScan(null); }}>Add {pick.size} to my kitchen</button>}
          </div>
        )}
      </div>
      {error && <div className="note bad">{error}</div>}
      <p className="muted small">AI recipes are new and untested. Use your judgement, and always cook meat, eggs and seafood all the way through.</p>
    </div>
  );
}
