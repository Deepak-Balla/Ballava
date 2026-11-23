// Ballava Chef: the chat window that opens from the 🧑‍🍳 Chef button in the navigation, on every screen.
// Python answers (kitchen/api.py -> ai_chat): with AI switched on it's the real AI (Gemini or Claude), which knows this
// family's kitchen, needs, diary, plan and recipe book; otherwise the built-in brain answers.
// Every conversation is kept: on this phone, and when you're signed in also in your account (kitchen/api.py -> chats),
// private to you, so your chats survive signing out and follow you to your other devices.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api, go, listenOnce, SpeechRec, speak, stopSpeaking } from './lib.js';
import { ingName, missingFor, lineName, slotFor, dayKey, addDays, SLOTS, SLOT_LABEL } from './catalog.js';
import PhotoScan from './PhotoScan.jsx';

const hello = name => ({ from: 'bot', text: `Hi${name ? ' ' + name : ''}! I'm Ballava Chef 🧑‍🍳 Ask me for any recipe by name, what to cook with what you have, calories, swaps, tiffin ideas, or how to fix a dish.` });
const KEY = 'ballava.chats';
const MAX_CHATS = 50;
const MAX_MESSAGES = 100;
const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
const titleOf = messages => (messages.find(m => m.from === 'me')?.text || 'New chat').slice(0, 60);
const byNewest = (a, b) => (b.at || 0) - (a.at || 0);

// ---- All chats: { list: [{ id, title, at, messages }], current }
function loadChats() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (saved?.list) return saved;
  } catch { /* nothing saved */ }
  let old = null; // the single chat kept by an earlier version
  try { old = JSON.parse(localStorage.getItem('ballava.chat') || 'null'); } catch { /* none */ }
  const list = Array.isArray(old) && old.some(m => m.from === 'me') ? [{ id: newId(), title: titleOf(old), at: Date.now(), messages: old }] : [];
  return { list, current: list[0]?.id || null };
}

function useChats(signedIn, name) {
  const [store, setStore] = useState(loadChats);
  const latest = useRef(store);
  latest.current = store;
  const pending = useRef(new Set()); // chats changed here that the server hasn't got yet
  const timer = useRef(null);
  const [synced, setSynced] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(store)); localStorage.removeItem('ballava.chat'); } catch { /* storage full */ }
  }, [store]);

  const flush = useCallback(async () => {
    if (!signedIn) { pending.current.clear(); return; }
    for (const id of [...pending.current]) {
      const c = latest.current.list.find(x => x.id === id);
      pending.current.delete(id);
      if (!c) continue;
      try { await api('chats', { id: c.id, title: c.title, at: c.at, messages: c.messages }); } catch { pending.current.add(id); return; }
    }
  }, [signedIn]);
  const queue = id => { pending.current.add(id); clearTimeout(timer.current); timer.current = setTimeout(flush, 700); };

  // Signed in: bring in the chats saved in your account, and send up any that only this phone has.
  useEffect(() => {
    if (!signedIn) return undefined;
    let live = true;
    api('chats').then(({ chats }) => {
      if (!live) return;
      const server = new Map(chats.map(c => [c.id, c]));
      for (const c of latest.current.list) if (!server.has(c.id) || (c.at || 0) > (server.get(c.id).at || 0)) pending.current.add(c.id);
      setStore(s => {
        const merged = new Map(s.list.map(c => [c.id, c]));
        for (const c of chats) if (!merged.has(c.id) || (c.at || 0) > (merged.get(c.id).at || 0)) merged.set(c.id, c);
        return { ...s, list: [...merged.values()].sort(byNewest).slice(0, MAX_CHATS) };
      });
      setSynced(true);
      setTimeout(flush, 0);
    }).catch(() => {});
    return () => { live = false; clearTimeout(timer.current); flush(); };
  }, [signedIn, flush]);

  const chat = store.list.find(c => c.id === store.current) || null;
  return {
    list: store.list,
    chat,
    synced,
    messages: chat ? chat.messages : [hello(name)],
    add(msg) {
      const s0 = latest.current;
      const id = s0.list.some(c => c.id === s0.current) ? s0.current : newId();
      setStore(s => {
        let list = s.list;
        if (!list.some(c => c.id === id)) list = [{ id, title: 'New chat', at: Date.now(), messages: [hello(name)] }, ...list].slice(0, MAX_CHATS);
        list = list.map(c => {
          if (c.id !== id) return c;
          const messages = [...c.messages, msg].slice(-MAX_MESSAGES);
          return { ...c, messages, at: Date.now(), title: titleOf(messages) };
        });
        return { current: id, list: [list.find(c => c.id === id), ...list.filter(c => c.id !== id)] };
      });
      queue(id);
    },
    update(index, change) {
      const id = latest.current.current;
      setStore(s => ({ ...s, list: s.list.map(c => (c.id === s.current ? { ...c, messages: c.messages.map((m, i) => (i === index ? { ...m, ...change } : m)) } : c)) }));
      if (id) queue(id);
    },
    open: id => setStore(s => ({ ...s, current: id })),
    startNew: () => setStore(s => ({ ...s, current: null })),
    remove: id => {
      setStore(s => ({ list: s.list.filter(c => c.id !== id), current: s.current === id ? null : s.current }));
      if (signedIn) api('chats/delete', { id }).catch(() => {});
    },
    clearAll: () => {
      setStore({ list: [], current: null });
      if (signedIn) api('chats/delete', { all: true }).catch(() => {});
    },
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
    home: ['What should I cook now?', 'Plan my day', ai && 'Give me the chicken biryani recipe', 'Quick 15-minute dinner'],
    dashboard: ['Plan my day', 'Plan my week', 'Was our week balanced?', 'Light dinner ideas'],
    pantry: ['What can I cook with what I have?', 'What should I use up first?', 'How do I store coriander longer?'],
    plan: ["What's planned for tomorrow?", 'Plan my day', 'Plan my week', 'What should I prep tonight?', 'Tiffin ideas'],
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

const planDate = (date, today) => (date === today ? 'Today' : date === addDays(today, 1) ? 'Tomorrow'
  : new Date(date + 'T12:00:00').toLocaleDateString('en', { weekday: 'short', day: 'numeric' }));

// A plan Chef made ("plan my day" / "plan my week"): every meal, the calories, and one tap to put it in the Plan.
function PlanCard({ m, i, ctx, close, update }) {
  const { findRecipe, setPlan, notify } = ctx;
  const today = dayKey();
  const days = Object.entries(m.plan.days);
  function apply() {
    setPlan(p => {
      const next = { ...p };
      for (const [date, day] of days) {
        const old = p[date] || {};
        const locked = old.locked || [];
        const merged = { ...old };
        for (const s of SLOTS) if (day[s] && !locked.includes(s)) merged[s] = day[s]; // your locked meals stay
        if (day.tiffins && Object.keys(day.tiffins).length) merged.tiffins = day.tiffins;
        for (const k of ['vrat', 'fastFor', 'festival', 'fast', 'usual']) delete merged[k];
        for (const k of ['vrat', 'fastFor', 'festival']) if (day[k]) merged[k] = day[k];
        next[date] = merged;
      }
      return next;
    });
    update(i, { planned: true });
    notify(m.plan.kind === 'week' ? 'Your week is in the plan.' : `${planDate(days[0][0], today)}'s meals are in your plan.`);
  }
  return (
    <div className="chat-plan">
      <b>📅 {m.plan.kind === 'week' ? 'Your week' : `${planDate(days[0][0], today)}'s plan`}</b>
      {days.map(([date, day]) => {
        const meals = SLOTS.map(s => [s, day[s] && findRecipe(day[s])]).filter(([, r]) => r);
        const kcal = meals.reduce((n, [, r]) => n + (r.nutrition?.kcal || 0), 0);
        return (
          <div key={date} className="chat-plan-day">
            {m.plan.kind === 'week' && <span className="chat-plan-date">{planDate(date, today)}</span>}
            {meals.map(([s, r]) => (
              <button key={s} className="chat-plan-row" onClick={() => { go('recipe/' + r.id); close?.(); }}>
                <span className="muted small">{SLOT_LABEL[s]}</span><span>{r.name}</span>{r.nutrition?.kcal != null && <small className="muted">{r.nutrition.kcal} kcal</small>}
              </button>
            ))}
            {SLOTS.filter(s => day.vrat?.[s] && findRecipe(day.vrat[s])).map(s => (
              <button key={'v' + s} className="chat-plan-row" onClick={() => { go('recipe/' + day.vrat[s]); close?.(); }}>
                <span className="muted small">🪔 {SLOT_LABEL[s]}</span><span>{findRecipe(day.vrat[s]).name}</span><small className="muted">{day.fastFor}</small>
              </button>
            ))}
            {day.fastFor === 'all' && <span className="muted small">🪔 Fasting day{day.festival ? `: ${day.festival}` : ''}</span>}
            {kcal > 0 && <span className="muted small chat-plan-total">≈ {kcal} kcal for the day, one serving each</span>}
          </div>
        );
      })}
      <div className="chat-dish-actions">
        <button className="btn primary sm" disabled={m.planned} onClick={apply}>{m.planned ? '✓ In your plan' : '📅 Add to my plan'}</button>
        <button className="btn sm" onClick={() => { go('plan'); close?.(); }}>Open Plan</button>
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
      {m.plan?.days && <PlanCard m={m} i={i} ctx={ctx} close={close} update={update} />}
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
      {m.added?.length > 0 && (
        <button className="btn sm chat-action" disabled={m.undone} onClick={() => { ctx.setPantry(p => p.filter(x => !m.added.includes(x.id))); update(i, { undone: true }); notify('Undone. Those items were removed from your kitchen.'); }}>
          {m.undone ? '↩ Removed again' : `↩ Undo (remove ${m.added.length} item${m.added.length > 1 ? 's' : ''})`}
        </button>
      )}
      {m.found?.length > 0 && !m.added && (
        <button className="btn sm chat-action" disabled={m.done} onClick={() => { const a = addToPantry(m.found); update(i, { done: true }); notify(a.length ? `Added ${a.length} item(s) to your kitchen` : 'Already in your kitchen'); }}>
          {m.done ? '✓ Added to my kitchen' : `🧺 Add ${m.found.length} item(s) to my kitchen`}
        </button>
      )}
    </>
  );
}

export const firstName = (auth, prefs) => ((auth?.user?.name || prefs?.name || '').trim().split(/\s+/)[0] || '');

export default function Assistant({ screen, param, onClose, ctx }) {
  const { family, plan, savedDishes, findRecipe, setAiRecipes, aiStatus, auth, prefs } = ctx;
  const signedIn = !!auth?.user;
  const chats = useChats(signedIn, firstName(auth, prefs));
  const { messages } = chats;
  const [text, setText] = useState('');
  const [busy, setBusy] = useState('');
  const [listening, setListening] = useState(false);
  const [showChats, setShowChats] = useState(false);
  const end = useRef(null);
  const recipe = ['recipe', 'cook'].includes(screen) ? findRecipe(param) : null;
  const ai = !!aiStatus.ai;

  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }); }, [messages, busy, showChats]);
  useEffect(() => { ctx.refreshAi?.(); }, []); // the AI may have been switched on (or the server restarted) since the page opened
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
        chefStyle: { length: prefs?.chefLength, language: prefs?.chefLanguage },
      });
      if (data.recipe) setAiRecipes(r => ({ ...r, [data.recipe.id]: data.recipe }));
      chats.add({ from: 'bot', text: data.reply, dishes: data.dishes || [], recipeId: data.recipe?.id, warning: data.recipe?.warning,
        shopping: data.shopping || [], followups: data.followups || [], plan: data.plan || undefined,
        source: data.source, note: data.note, at: Date.now() });
    } catch (err) {
      chats.add({ from: 'bot', text: err.message, error: true, at: Date.now() });
    }
    setBusy('');
  }

  // 📷 A photo of the fridge: the items go straight into the kitchen (with Undo), and Chef says what it saw.
  const photoStart = () => { chats.add({ from: 'me', text: '📷 Add what you can see in this photo to my kitchen', at: Date.now() }); setBusy('Looking at your photo…'); };
  const photoDone = data => {
    setBusy('');
    if (data.error) { chats.add({ from: 'bot', text: data.error, error: true, at: Date.now() }); return; }
    const already = data.found.filter(id => !data.added.includes(id));
    const text = !data.found.length && !data.unknown?.length ? "I couldn't spot any ingredients. Try a closer, brighter photo."
      : [data.added.length ? `I added ${data.added.map(ingName).join(', ')} to your kitchen.` : '',
        already.length ? `You already had ${already.map(ingName).join(', ')}.` : '',
        data.unknown?.length ? `I also saw ${data.unknown.join(', ')} (not in Ballava's list yet).` : ''].filter(Boolean).join('\n');
    chats.add({ from: 'bot', text, found: data.found, added: data.added, followups: data.found.length ? ['What can I cook with these?', 'Something quick with these'] : [], at: Date.now() });
  };

  const last = messages[messages.length - 1];
  const chips = last?.from === 'bot' && last.followups?.length && !busy ? last.followups : starters(screen, recipe, ai);

  return (
    <div className="sheet assistant-sheet" role="dialog" aria-modal="true" aria-label="Ballava Chef" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet-inner assistant">
        <div className="assistant-head">
          <span className="assistant-mark" aria-hidden="true">🧑‍🍳</span>
          <div className="assistant-title">
            <b>Ballava Chef</b>
            <span className={'ai-status ' + (ai ? 'on' : 'off')}>{ai ? `Connected to ${aiStatus.provider || 'AI'}` : 'AI is off · quick answers'}</span>
          </div>
          <button className={'icon-btn sm head-btn' + (showChats ? ' on' : '')} onClick={() => setShowChats(v => !v)} aria-label={`Your chats (${chats.list.length})`} aria-pressed={showChats} title="Your chats">🕘</button>
          <button className="icon-btn sm head-btn" onClick={() => { chats.startNew(); setShowChats(false); stopSpeaking(); }} aria-label="New chat" title="New chat">＋</button>
          <button className="icon-btn sm head-btn" onClick={onClose} aria-label="Close Ballava Chef">✕</button>
        </div>

        {showChats ? (
          <div className="chat-list" aria-label="Your chats">
            <div className="row between"><b>Your chats</b><span className="muted small">{signedIn ? 'Saved in your account' : 'Saved on this phone · sign in to keep them everywhere'}</span></div>
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
            {!chats.chat && chats.list.length > 0 && (
              <div className="recent-chats" aria-label="Your recent chats">
                <span className="muted small">Pick up where you left off</span>
                {chats.list.slice(0, 3).map(c => (
                  <button key={c.id} className="recent-chat" onClick={() => chats.open(c.id)}>🕘 {c.title} <small className="muted">· {ago(c.at)}</small></button>
                ))}
                {chats.list.length > 3 && <button className="btn link sm" onClick={() => setShowChats(true)}>All {chats.list.length} chats</button>}
              </div>
            )}
            <div ref={end} />
          </div>
        )}

        {!showChats && (
          <>
            <div className="chips scroll starters">{chips.map(s => <button key={s} className="chip" onClick={() => ask(s)} disabled={!!busy}>{s}</button>)}</div>
            <form className="row nowrap chat-form" onSubmit={e => { e.preventDefault(); ask(text); }}>
              <input aria-label="Your question" value={text} onChange={e => setText(e.target.value)} placeholder={recipe ? `Ask about ${recipe.name}…` : 'Ask for any recipe or food question…'} autoFocus />
              <PhotoScan compact addToPantry={ctx.addToPantry} notify={ctx.notify} onStart={photoStart} onScanned={photoDone} />
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
    <button className="fab" onClick={onOpen} aria-label="Open Ballava Chef" title="Ballava Chef">
      <span aria-hidden="true">🧑‍🍳</span><span className="fab-label">Chef</span>
    </button>
  );
}
