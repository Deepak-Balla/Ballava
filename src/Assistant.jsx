// The kitchen assistant: a chat that opens from the ✨ button on every screen (and full-page as "Ask Ballava").
// Python answers (kitchen/api.py -> ai_chat): with AI switched on it's the AI, which knows this family's kitchen,
// needs, diary, plan and recipe book; otherwise the built-in brain answers. The chat is kept on this phone only.
import React, { useEffect, useRef, useState } from 'react';
import { api, go, listenOnce, SpeechRec, speak, stopSpeaking, shrinkImage, useStored } from './lib.js';
import { ingName } from './catalog.js';
import { Header } from './ui.jsx';
import { t } from './i18n.js';

const HELLO = { from: 'bot', text: "Hi! I'm your kitchen helper. Ask me what to cook, how many calories a dish has, what to use instead of something, tiffin ideas, or how to fix a dish." };

// Quick questions that fit the screen you are on.
function starters(screen, recipe, ai) {
  if (recipe) {
    return [`Calories in ${recipe.name}?`, 'Make it healthier', 'Make it kid-friendly', 'What can I use instead of an ingredient?', 'How do I store leftovers?'];
  }
  const by = {
    home: ['What should I cook now?', ai && 'Invent a new dish from my kitchen', 'Quick 15-minute dinner', 'Healthy breakfast ideas'],
    pantry: ['What can I cook with what I have?', 'What should I use up first?', 'How do I store coriander longer?'],
    plan: ["What's planned for tomorrow?", 'What should I prep tonight?', 'Tiffin ideas', 'High protein dinner ideas'],
    track: ['Was our week balanced?', 'Ideas for more vegetables', 'Light dinner ideas'],
    list: ['Cheap protein ideas', 'What else should I buy this week?'],
    saved: ['Which saved dish should I make today?', 'Something new like my saved dishes'],
  };
  return (by[screen] || ['What should I cook tonight?', 'Tiffin ideas', "What's planned for tomorrow?", 'Calories in dal tadka?']).filter(Boolean);
}

function BotExtras({ m, close, findRecipe, isSaved, toggleSave, addToShopping, addToPantry, notify, done, setDone }) {
  const open = id => { go('recipe/' + id); close?.(); };
  const recipe = m.recipeId && findRecipe(m.recipeId);
  return (
    <>
      {m.dishes?.length > 0 && (
        <div className="chips wrap">
          {m.dishes.map(id => findRecipe(id) && (
            <button key={id} className="chip dish-chip" onClick={() => open(id)}>
              {findRecipe(id).name}{findRecipe(id).nutrition?.kcal ? <small> · {findRecipe(id).nutrition.kcal} kcal</small> : null}
            </button>
          ))}
        </div>
      )}
      {recipe && (
        <div className="chat-recipe">
          <div><b>✨ {recipe.name}</b><div className="muted small">{recipe.time} min{recipe.nutrition?.kcal ? ` · about ${recipe.nutrition.kcal} kcal a serving` : ''} · new AI recipe</div></div>
          <div className="row">
            <button className="btn primary sm" onClick={() => open(recipe.id)}>Open recipe</button>
            <button className="btn sm" onClick={() => toggleSave(recipe)}>{isSaved(recipe.id) ? '♥ Saved' : '♡ Save'}</button>
          </div>
        </div>
      )}
      {m.shopping?.length > 0 && (
        <button className="btn sm chat-action" disabled={done} onClick={() => { addToShopping(m.shopping); setDone(); notify(`Added ${m.shopping.length} item(s) to your shopping list`); }}>
          {done ? '✓ Added to shopping list' : `🛒 Add ${m.shopping.map(ingName).join(', ')} to the list`}
        </button>
      )}
      {m.found?.length > 0 && (
        <button className="btn sm chat-action" disabled={done} onClick={() => { const a = addToPantry(m.found); setDone(); notify(a.length ? `Added ${a.length} item(s) to your kitchen` : 'Already in your kitchen'); }}>
          {done ? '✓ Added to my kitchen' : `🧺 Add ${m.found.length} item(s) to my kitchen`}
        </button>
      )}
    </>
  );
}

export default function Assistant({ full = false, screen, param, onClose, ctx }) {
  const { family, plan, savedDishes, findRecipe, setAiRecipes, addToShopping, addToPantry, notify, aiStatus, isSaved, toggleSave } = ctx;
  const [messages, setMessages] = useStored('chat', [HELLO]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState('');
  const [listening, setListening] = useState(false);
  const [done, setDoneState] = useState({});
  const end = useRef(null);
  const recipe = ['recipe', 'cook'].includes(screen) ? findRecipe(param) : null;
  const ai = !!aiStatus.ai;

  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }); }, [messages, busy]);
  useEffect(() => {
    if (full) return undefined;
    const onKey = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); stopSpeaking(); };
  }, [full, onClose]);

  const add = msg => setMessages(m => [...m, msg].slice(-40));

  async function ask(question) {
    const q = question.trim();
    if (!q || busy) return;
    const before = messages.filter(m => m.text && !m.error).slice(-8).map(m => ({ from: m.from, text: m.text }));
    add({ from: 'me', text: q });
    setText('');
    setBusy('Thinking…');
    try {
      const data = await api('ai/chat', {
        ...family, history: family.history.slice(-60), plan, savedDishes, text: q, messages: before, screen, recipeId: recipe?.id,
      });
      if (data.recipe) setAiRecipes(r => ({ ...r, [data.recipe.id]: data.recipe }));
      add({ from: 'bot', text: data.reply, dishes: data.dishes || [], recipeId: data.recipe?.id, shopping: data.shopping || [], source: data.source, note: data.note, at: Date.now() });
    } catch (err) {
      add({ from: 'bot', text: err.message, error: true, at: Date.now() });
    }
    setBusy('');
  }

  async function onPhoto(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || busy) return;
    add({ from: 'me', text: '📷 What can you see in this photo?' });
    setBusy('Looking at your photo…');
    try {
      const image = await shrinkImage(file);
      const data = await api('ai/scan', { image, mediaType: 'image/jpeg' });
      const seen = [...data.found.map(ingName), ...(data.unknown || [])];
      add({ from: 'bot', text: seen.length ? `I can see: ${seen.join(', ')}.` : "I couldn't spot any ingredients. Try a closer, brighter photo.", found: data.found, at: Date.now() });
    } catch (err) {
      add({ from: 'bot', text: err.message, error: true, at: Date.now() });
    }
    setBusy('');
  }

  const close = full ? null : onClose;
  const clear = () => { stopSpeaking(); setMessages([HELLO]); setDoneState({}); };
  const subtitle = recipe ? `About: ${recipe.name}` : ai ? 'Ask anything about cooking and food' : 'Quick answers (AI is off)';

  const body = (
    <>
      <div className="chat" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={'bubble ' + m.from + (m.error ? ' error' : '')}>
            {m.text}
            {m.from === 'bot' && (
              <BotExtras m={m} close={close} findRecipe={findRecipe} isSaved={isSaved} toggleSave={toggleSave} addToShopping={addToShopping}
                addToPantry={addToPantry} notify={notify} done={done[i]} setDone={() => setDoneState(d => ({ ...d, [i]: true }))} />
            )}
            {m.from === 'bot' && m.note && <div className="bubble-note">{m.note} Here's a quick answer instead.</div>}
            {m.from === 'bot' && i > 0 && !m.error && (
              <button className="speak-btn" onClick={() => speak(m.text)} aria-label="Read this answer aloud">🔊</button>
            )}
          </div>
        ))}
        {busy && <div className="bubble bot typing" role="status"><span className="dots" aria-hidden="true"><i /><i /><i /></span> {busy}</div>}
        <div ref={end} />
      </div>
      <div className="chips scroll starters">{starters(screen, recipe, ai).map(s => <button key={s} className="chip" onClick={() => ask(s)} disabled={!!busy}>{s}</button>)}</div>
      <form className="row nowrap chat-form" onSubmit={e => { e.preventDefault(); ask(text); }}>
        <input aria-label="Your question" value={text} onChange={e => setText(e.target.value)} placeholder={recipe ? `Ask about ${recipe.name}…` : 'Ask anything about food…'} autoFocus={!full} />
        {ai && (
          <label className="icon-btn chat-photo" aria-label="Send a photo of your fridge or shelf" title="Photo of your fridge">📷
            <input type="file" accept="image/*" capture="environment" onChange={onPhoto} hidden />
          </label>
        )}
        {SpeechRec && <button type="button" className={'icon-btn mic' + (listening ? ' live' : '')} aria-label="Speak" onClick={() => { setListening(true); listenOnce(ask, () => setListening(false)); }}>🎤</button>}
        <button className="btn primary" type="submit" disabled={!!busy}>Send</button>
      </form>
    </>
  );

  if (full) {
    return (
      <div className="screen assistant-page">
        <Header title={t('Ask Ballava')} back="more" right={<button className="btn link" onClick={clear}>New chat</button>} />
        <p className="muted small assistant-sub">{subtitle}</p>
        {body}
      </div>
    );
  }
  return (
    <div className="sheet assistant-sheet" role="dialog" aria-modal="true" aria-label="Ballava assistant" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet-inner assistant">
        <div className="assistant-head">
          <span className="assistant-mark" aria-hidden="true">✨</span>
          <div className="assistant-title"><b>Ballava assistant</b><span className="muted small">{subtitle}</span></div>
          <button className="btn link sm" onClick={clear}>New chat</button>
          <button className="icon-btn" onClick={onClose} aria-label="Close assistant">✕</button>
        </div>
        {body}
      </div>
    </div>
  );
}

export function AssistantButton({ onOpen }) {
  return (
    <button className="fab" onClick={onOpen} aria-label="Open the Ballava assistant" title="Ask Ballava">
      <span aria-hidden="true">✨</span><span className="fab-label">Ask</span>
    </button>
  );
}
