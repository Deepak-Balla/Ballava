// Ballava AI: the chat window that opens from the ✨ AI button in the navigation, on every screen.
// Python answers (kitchen/api.py -> ai_chat): with AI switched on it's the real AI (Gemini or Claude), which knows this
// family's kitchen, needs, diary, plan and recipe book; otherwise the built-in brain answers.
// Every conversation is kept on this phone (they can be personal), so you can go back to any of them.
import React, { useEffect, useRef, useState } from 'react';
import { api, go, listenOnce, SpeechRec, speak, stopSpeaking, shrinkImage } from './lib.js';
import { ingName, missingFor, lineName, slotFor, dayKey, addDays, SLOT_LABEL } from './catalog.js';

const HELLO = { from: 'bot', text: "Hi! I'm Ballava AI. Ask me for any recipe by name, what to cook with what you have, calories, swaps, tiffin ideas, or how to fix a dish." };
const KEY = 'ballava.chats';
const MAX_CHATS = 30;
const MAX_MESSAGES = 80;
const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const titleOf = messages => (messages.find(m => m.from === 'me')?.text || 'New chat').slice(0, 48);

// ---- All chats, saved on this device: { list: [{ id, title, at, messages }], current }
function loadChats() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (saved?.list) return saved;
  } catch { /* nothing saved */ }
  let old = null; // the single chat kept by the earlier version
  try { old = JSON.parse(localStorage.getItem('ballava.chat') || 'null'); } catch { /* none */ }
  const list = Array.isArray(old) && old.some(m => m.from === 'me') ? [{ id: newId(), title: titleOf(old), at: Date.now(), messages: old }] : [];
  return { list, current: list[0]?.id || null };
}

function useChats() {
  const [store, setStore] = useState(loadChats);
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(store)); localStorage.removeItem('ballava.chat'); } catch { /* storage full */ }
  }, [store]);
  const chat = store.list.find(c => c.id === store.current) || null;
  return {
    list: store.list,
    chat,
    messages: chat ? chat.messages : [HELLO],
    add(msg) {
      setStore(s => {
        let { list, current } = s;
        if (!list.some(c => c.id === current)) {
          current = newId();
          list = [{ id: current, title: 'New chat', at: Date.now(), messages: [HELLO] }, ...list].slice(0, MAX_CHATS);
        }
        list = list.map(c => {
          if (c.id !== current) return c;
          const messages = [...c.messages, msg].slice(-MAX_MESSAGES);
          return { ...c, messages, at: Date.now(), title: titleOf(messages) };
        });
        return { current, list: [list.find(c => c.id === current), ...list.filter(c => c.id !== current)] };
      });
    },
    update(index, change) {
      setStore(s => ({ ...s, list: s.list.map(c => (c.id === s.current ? { ...c, messages: c.messages.map((m, i) => (i === index ? { ...m, ...change } : m)) } : c)) }));
    },
    open: id => setStore(s => ({ ...s, current: id })),
    startNew: () => setStore(s => ({ ...s, current: null })),
    remove: id => setStore(s => ({ list: s.list.filter(c => c.id !== id), current: s.current === id ? null : s.current })),
    clearAll: () => setStore({ list: [], current: null }),
  };
}

const ago = t => {
  const m = Math.round((Date.now() - t) / 60000);
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

// Quick questions that fit the screen you are on.
function starters(screen, recipe, ai) {
  if (recipe) return [`Calories in ${recipe.name}?`, 'Make it healthier', 'Make it kid-friendly', 'What can I use instead?'];
  const by = {
    home: ['What should I cook now?', ai && 'Give me the chicken biryani recipe', 'Quick 15-minute dinner', 'Healthy breakfast ideas'],
    pantry: ['What can I cook with what I have?', 'What should I use up first?', 'How do I store coriander longer?'],
    plan: ["What's planned for tomorrow?", 'What should I prep tonight?', 'Tiffin ideas', 'High protein dinner ideas'],
    dashboard: ['Was our week balanced?', 'How can we eat fewer calories?', 'Light dinner ideas'],
    track: ['Was our week balanced?', 'Ideas for more vegetables', 'Light dinner ideas'],
    list: ['Cheap protein ideas', 'What else should I buy this week?'],
    saved: ['Which saved dish should I make today?', 'Something new like my saved dishes'],
  };
  return (by[screen] || ['What should I cook tonight?', 'Tiffin ideas', "What's planned for tomorrow?", 'Calories in dal tadka?']).filter(Boolean);
}

// One dish in an answer: what it is, what's missing, and one-tap actions.
function DishCard({ recipe, ctx, close, isNew }) {
  const { pantry, addToShopping, notify, isSaved, toggleSave, setPlan } = ctx;
  const [done, setDone] = useState({});
  const miss = missingFor(recipe, pantry);
  const tomorrow = addDays(dayKey(), 1);
  const slot = slotFor(recipe);
  return (
    <div className={'chat-dish' + (isNew ? ' new' : '')}>
      <div className="chat-dish-head">
        <b>{isNew ? '✨ ' : ''}{recipe.name}</b>
        <span className="muted small">{recipe.time} min{recipe.nutrition?.kcal != null ? ` · ${recipe.nutrition.kcal} kcal a serving` : ''}{isNew ? ' · new AI recipe' : ''}</span>
      </div>
      {recipe.warning && <div className="chat-warn">⚠️ {recipe.warning}</div>}
      <div className={'chat-missing ' + (miss.length ? 'need' : 'have')}>
        {miss.length ? <>Missing {miss.length}: {miss.map(lineName).join(', ')}</> : '✓ You have everything for this'}
      </div>
      <div className="chat-dish-actions">
        <button className="btn primary sm" onClick={() => { go('recipe/' + recipe.id); close?.(); }}>Open recipe</button>
        {miss.length > 0 && (
          <button className="btn sm" disabled={done.shop} onClick={() => { addToShopping(miss.map(it => it.options[0])); setDone(d => ({ ...d, shop: true })); notify(`Added ${miss.length} item(s) to your shopping list`); }}>
            {done.shop ? '✓ On your list' : '🛒 Add missing'}
          </button>
        )}
        <button className="btn sm" disabled={done.plan} onClick={() => { setPlan(p => ({ ...p, [tomorrow]: { ...(p[tomorrow] || {}), [slot]: recipe.id } })); setDone(d => ({ ...d, plan: true })); notify(`Planned ${recipe.name} for tomorrow's ${SLOT_LABEL[slot].toLowerCase()}`); }}>
          {done.plan ? '✓ Planned' : '📅 Tomorrow'}
        </button>
        <button className="btn sm" onClick={() => toggleSave(recipe)} aria-label={isSaved(recipe.id) ? `Remove ${recipe.name} from saved dishes` : `Save ${recipe.name}`}>{isSaved(recipe.id) ? '♥' : '♡'}</button>
      </div>
    </div>
  );
}

function BotExtras({ m, i, ctx, close, update }) {
  const { findRecipe, addToShopping, addToPantry, notify } = ctx;
  const recipe = m.recipeId && findRecipe(m.recipeId);
  const dishes = (m.dishes || []).map(findRecipe).filter(Boolean);
  return (
    <>
      {recipe && <DishCard recipe={{ ...recipe, warning: m.warning || recipe.warning }} ctx={ctx} close={close} isNew />}
      {dishes.slice(0, 3).map(r => <DishCard key={r.id} recipe={r} ctx={ctx} close={close} />)}
      {dishes.length > 3 && (
        <div className="chips wrap">{dishes.slice(3).map(r => <button key={r.id} className="chip dish-chip" onClick={() => { go('recipe/' + r.id); close?.(); }}>{r.name}</button>)}</div>
      )}
      {m.shopping?.length > 0 && (
        <button className="btn sm chat-action" disabled={m.done} onClick={() => { addToShopping(m.shopping); update(i, { done: true }); notify(`Added ${m.shopping.length} item(s) to your shopping list`); }}>
          {m.done ? '✓ Added to shopping list' : `🛒 Add ${m.shopping.map(ingName).join(', ')} to the list`}
        </button>
      )}
      {m.found?.length > 0 && (
        <button className="btn sm chat-action" disabled={m.done} onClick={() => { const a = addToPantry(m.found); update(i, { done: true }); notify(a.length ? `Added ${a.length} item(s) to your kitchen` : 'Already in your kitchen'); }}>
          {m.done ? '✓ Added to my kitchen' : `🧺 Add ${m.found.length} item(s) to my kitchen`}
        </button>
      )}
    </>
  );
}

export default function Assistant({ screen, param, onClose, ctx }) {
  const { family, plan, savedDishes, findRecipe, setAiRecipes, aiStatus } = ctx;
  const chats = useChats();
  const { messages } = chats;
  const [text, setText] = useState('');
  const [busy, setBusy] = useState('');
  const [listening, setListening] = useState(false);
  const [showChats, setShowChats] = useState(false);
  const end = useRef(null);
  const recipe = ['recipe', 'cook'].includes(screen) ? findRecipe(param) : null;
  const ai = !!aiStatus.ai;

  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }); }, [messages, busy, showChats]);
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('keydown', onKey); stopSpeaking(); };
  }, [onClose]);

  async function ask(question) {
    const q = question.trim();
    if (!q || busy) return;
    const before = messages.filter(m => m.text && !m.error).slice(-8).map(m => ({ from: m.from, text: m.text }));
    chats.add({ from: 'me', text: q, at: Date.now() });
    setText('');
    setBusy('Thinking…');
    try {
      const data = await api('ai/chat', {
        ...family, history: family.history.slice(-60), plan, savedDishes, text: q, messages: before, screen, recipeId: recipe?.id,
      });
      if (data.recipe) setAiRecipes(r => ({ ...r, [data.recipe.id]: data.recipe }));
      chats.add({ from: 'bot', text: data.reply, dishes: data.dishes || [], recipeId: data.recipe?.id, warning: data.recipe?.warning,
        shopping: data.shopping || [], followups: data.followups || [], source: data.source, note: data.note, at: Date.now() });
    } catch (err) {
      chats.add({ from: 'bot', text: err.message, error: true, at: Date.now() });
    }
    setBusy('');
  }

  async function onPhoto(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || busy) return;
    chats.add({ from: 'me', text: '📷 What can you see in this photo?', at: Date.now() });
    setBusy('Looking at your photo…');
    try {
      const image = await shrinkImage(file);
      const data = await api('ai/scan', { image, mediaType: 'image/jpeg' });
      const seen = [...data.found.map(ingName), ...(data.unknown || [])];
      chats.add({ from: 'bot', text: seen.length ? `I can see: ${seen.join(', ')}.` : "I couldn't spot any ingredients. Try a closer, brighter photo.", found: data.found, at: Date.now() });
    } catch (err) {
      chats.add({ from: 'bot', text: err.message, error: true, at: Date.now() });
    }
    setBusy('');
  }

  const last = messages[messages.length - 1];
  const chips = last?.from === 'bot' && last.followups?.length && !busy ? last.followups : starters(screen, recipe, ai);

  return (
    <div className="sheet assistant-sheet" role="dialog" aria-modal="true" aria-label="Ballava AI" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet-inner assistant">
        <div className="assistant-head">
          <span className="assistant-mark" aria-hidden="true">✨</span>
          <div className="assistant-title">
            <b>Ballava AI</b>
            <span className={'ai-status ' + (ai ? 'on' : 'off')}>{ai ? `Connected to ${aiStatus.provider || 'AI'}` : 'AI is off · quick answers'}</span>
          </div>
          <button className={'icon-btn sm head-btn' + (showChats ? ' on' : '')} onClick={() => setShowChats(v => !v)} aria-label={`Your chats (${chats.list.length})`} aria-pressed={showChats} title="Your chats">🕘</button>
          <button className="icon-btn sm head-btn" onClick={() => { chats.startNew(); setShowChats(false); stopSpeaking(); }} aria-label="New chat" title="New chat">＋</button>
          <button className="icon-btn sm head-btn" onClick={onClose} aria-label="Close Ballava AI">✕</button>
        </div>

        {showChats ? (
          <div className="chat-list" aria-label="Your chats">
            <div className="row between"><b>Your chats</b><span className="muted small">Kept on this phone only</span></div>
            {chats.list.length === 0 && <p className="muted">No chats yet. Ask me anything and it'll be saved here.</p>}
            {chats.list.map(c => (
              <div key={c.id} className={'chat-list-item' + (c.id === chats.chat?.id ? ' on' : '')}>
                <button className="chat-list-open" onClick={() => { chats.open(c.id); setShowChats(false); }}>
                  <b>{c.title}</b>
                  <span className="muted small">{c.messages.filter(m => m.from === 'me').length} question{c.messages.filter(m => m.from === 'me').length === 1 ? '' : 's'} · {ago(c.at)}</span>
                </button>
                <button className="icon-btn sm" onClick={() => chats.remove(c.id)} aria-label={`Delete chat: ${c.title}`}>🗑</button>
              </div>
            ))}
            {chats.list.length > 1 && <button className="btn link danger" onClick={() => chats.clearAll()}>Delete all chats</button>}
          </div>
        ) : (
          <div className="chat" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={'bubble ' + m.from + (m.error ? ' error' : '')}>
                {m.text}
                {m.from === 'bot' && <BotExtras m={m} i={i} ctx={ctx} close={onClose} update={chats.update} />}
                {m.from === 'bot' && m.note && <div className="bubble-note">{m.note} Here's a quick answer instead.</div>}
                {m.from === 'bot' && i > 0 && !m.error && <button className="speak-btn" onClick={() => speak(m.text)} aria-label="Read this answer aloud">🔊</button>}
              </div>
            ))}
            {busy && <div className="bubble bot typing" role="status"><span className="dots" aria-hidden="true"><i /><i /><i /></span> {busy}</div>}
            <div ref={end} />
          </div>
        )}

        {!showChats && (
          <>
            <div className="chips scroll starters">{chips.map(s => <button key={s} className="chip" onClick={() => ask(s)} disabled={!!busy}>{s}</button>)}</div>
            <form className="row nowrap chat-form" onSubmit={e => { e.preventDefault(); ask(text); }}>
              <input aria-label="Your question" value={text} onChange={e => setText(e.target.value)} placeholder={recipe ? `Ask about ${recipe.name}…` : 'Ask for any recipe or food question…'} autoFocus />
              {ai && (
                <label className="icon-btn chat-photo" aria-label="Send a photo of your fridge or shelf" title="Photo of your fridge">📷
                  <input type="file" accept="image/*" capture="environment" onChange={onPhoto} hidden />
                </label>
              )}
              {SpeechRec && <button type="button" className={'icon-btn mic' + (listening ? ' live' : '')} aria-label="Speak" onClick={() => { setListening(true); listenOnce(ask, () => setListening(false)); }}>🎤</button>}
              <button className="btn primary" type="submit" disabled={!!busy}>Send</button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// Only in cook mode, where the navigation bar is hidden.
export function AssistantButton({ onOpen }) {
  return (
    <button className="fab" onClick={onOpen} aria-label="Open Ballava AI" title="Ballava AI">
      <span aria-hidden="true">✨</span><span className="fab-label">AI</span>
    </button>
  );
}
