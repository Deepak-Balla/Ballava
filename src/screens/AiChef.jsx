import React, { useEffect, useState } from 'react';
import { Header, ingName } from '../ui.jsx';
import { api, go } from '../lib.js';
import PhotoScan from '../PhotoScan.jsx';

// Recipe Studio: a simple form for when you know what you want. Type a dish (or nothing), pick a meal, get one full
// recipe card to cook, save and plan. Ballava Chef (the chat) does the same and more by conversation; this is the
// one-tap version, plus the fridge-photo scanner.
export default function AiChef({ aiStatus, refreshAi, pantry, setPantry, members, aiRecipes, setAiRecipes, addToPantry, notify }) {
  const [wish, setWish] = useState('');
  const [meal, setMeal] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [scan, setScan] = useState(null); // what the last photo added
  useEffect(() => { refreshAi?.(); }, []);

  if (!aiStatus.ai) {
    return (
      <div className="screen">
        <Header title="✨ Recipe Studio" back="more" />
        <div className="card">
          <h3>Recipe Studio needs AI</h3>
          <p>Everything else in Ballava works without AI. Recipe Studio adds:</p>
          <ul><li>The full recipe for any dish you name, with what you're missing</li><li>Inventing new dishes from exactly what's in your kitchen</li><li>Reading a photo of your fridge or shelf</li></ul>
          <button className="btn sm" onClick={() => refreshAi?.()}>Check again</button>
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
        household: members.map(m => ({ diet: m.diet, jain: m.jain, noOnionGarlic: m.noOnionGarlic, diabetic: m.diabetic, fasting: m.fasting, allergies: m.allergies, spice: m.spice, age: m.age, goals: m.goals })),
        wish, meal,
      });
      const recipe = data.recipe; // already checked and cleaned by Python (engine.normalize_ai_recipe)
      if (data.fromBook) {
        notify(`${recipe.name} is already in your recipe book. Here it is!`);
      } else {
        setAiRecipes({ ...aiRecipes, [recipe.id]: recipe });
        if (data.warning) notify(`Here's ${recipe.name}, as you asked. Please note: ${data.warning}.`);
      }
      go('recipe/' + recipe.id);
    } catch (e) { setError(e.message); }
    setBusy('');
  }

  return (
    <div className="screen">
      <Header title="✨ Recipe Studio" back="more" />
      <div className="card">
        <h3>Get any recipe, or invent one</h3>
        <p className="muted small">The quick way to one full recipe card: name a dish ("chicken biryani") and you get exactly that recipe, with what you're missing. Or leave it empty to invent something from your kitchen. For questions and back-and-forth, use 🧑‍🍳 Chef.</p>
        <p className="muted small">Uses your {pantry.length} kitchen items{members.length ? ' and your family\'s needs' : ''}. Calories are worked out for you.</p>
        <div className="chips wrap" role="group" aria-label="Meal">
          {[['', 'Any meal'], ['breakfast', 'Breakfast'], ['lunch', 'Lunch'], ['dinner', 'Dinner'], ['snack', 'Snack']].map(([id, label]) => (
            <button key={id || 'any'} type="button" className={'chip' + (meal === id ? ' on' : '')} aria-pressed={meal === id} onClick={() => setMeal(id)}>{label}</button>
          ))}
        </div>
        <textarea value={wish} onChange={e => setWish(e.target.value)} rows={2} placeholder="e.g. 'chicken biryani', 'something with paneer under 20 min', 'kid's tiffin'…" aria-label="Dish or wish" />
        <button className="btn primary" onClick={invent} disabled={!!busy || (!pantry.length && !wish.trim())}>
          {busy === 'invent' ? 'Cooking up your recipe…' : wish.trim() ? 'Get this recipe' : 'Invent a dish from my kitchen'}
        </button>
        {!pantry.length && !wish.trim() && <p className="muted small">Name a dish above, or add a few things to your kitchen first.</p>}
      </div>

      <div className="card">
        <h3>📷 Scan my fridge</h3>
        <p className="muted small">Take a photo of your fridge, shelf or vegetable basket. AI spots the items and adds them to your kitchen (you can undo).</p>
        <PhotoScan label="📷 Take or choose a photo" addToPantry={addToPantry} notify={notify} onStart={() => setScan({ busy: true })} onScanned={setScan} />
        {scan && (
          <div className="scan" role="status">
            {scan.busy ? <p className="muted">Looking at your photo…</p> : scan.error ? <p className="note bad">{scan.error}</p> : (
              <>
                <p>{scan.added.length ? <>Added <b>{scan.added.map(ingName).join(', ')}</b> to your kitchen.</> : scan.found.length ? 'You already had everything I could see.' : "I couldn't spot any ingredients. Try a closer, brighter photo."}</p>
                {scan.unknown?.length > 0 && <p className="muted small">Also saw: {scan.unknown.join(', ')}</p>}
                <div className="row">
                  {scan.added.length > 0 && <button className="btn sm" onClick={() => { setPantry(p => p.filter(x => !scan.added.includes(x.id))); setScan(null); notify('Undone.'); }}>Undo</button>}
                  {scan.found.length > 0 && <button className="btn primary sm" onClick={() => { setWish(''); invent(); }}>Invent a dish with these</button>}
                </div>
              </>
            )}
          </div>
        )}
      </div>
      {error && <div className="note bad">{error}</div>}
      <p className="muted small">AI recipes are new and untested. Use your judgement, and always cook meat, eggs and seafood all the way through.</p>
    </div>
  );
}
