import React, { useEffect, useRef, useState } from 'react';
import { BY_ID } from '../../shared/ingredients.mjs';
import { useSoon } from '../../shared/engine.mjs';
import { Empty, Stars, ingName } from '../ui.jsx';
import { speak, stopSpeaking, beep, keepAwake, fmtTime, go, SpeechRec } from '../lib.js';
import { BachaoList } from './Bachao.jsx';

export default function Cook(props) {
  if (!props.recipe) return <div className="screen"><Empty title="Recipe not found"><a href="#/home">Go home</a></Empty></div>;
  return <CookMode key={props.recipe.id} {...props} />;
}

function CookMode({ recipe, pantry, setPantry, setHistory, notify }) {
  const [i, setI] = useState(0);
  const [timers, setTimers] = useState([]); // {id, label, endsAt, done}
  const [now, setNow] = useState(Date.now());
  const [readAloud, setReadAloud] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [whistles, setWhistles] = useState({}); // step index -> count
  const [listenWhistle, setListenWhistle] = useState(false);
  const [showBachao, setShowBachao] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const recRef = useRef(null);
  const stateRef = useRef({});

  // Keep the screen on and tick the timers.
  useEffect(() => {
    let lock; keepAwake().then(l => { lock = l; });
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => { clearInterval(t); try { lock && lock.release(); } catch { /* */ } stopSpeaking(); };
  }, []);

  useEffect(() => {
    const due = timers.filter(t => !t.done && now >= t.endsAt);
    if (!due.length) return;
    beep();
    notify(`⏰ Timer done: ${due.map(t => t.label).join(', ')}`);
    setTimers(ts => ts.map(t => (due.some(d => d.id === t.id) ? { ...t, done: true } : t)));
  }, [now]);
  const steps = recipe.steps;
  const step = steps[i];
  const last = i === steps.length - 1;

  const startTimer = (minutes, label) => setTimers(ts => [...ts, { id: Date.now(), label, endsAt: Date.now() + minutes * 60000, done: false }]);
  const goTo = n => { const k = Math.max(0, Math.min(steps.length - 1, n)); setI(k); if (readAloud) speak(`Step ${k + 1}. ${steps[k].text}`); };
  stateRef.current = { i, goTo, step, startTimer, last };

  useEffect(() => { if (readAloud) speak(`Step ${i + 1}. ${step.text}`); else stopSpeaking(); }, [readAloud]);

  // Hands-free: say "next", "back", "repeat" or "start timer".
  useEffect(() => {
    if (!handsFree || !SpeechRec) return;
    let stopped = false;
    const rec = new SpeechRec();
    rec.lang = 'en-IN'; rec.continuous = true; rec.interimResults = false;
    rec.onresult = e => {
      const said = e.results[e.results.length - 1][0].transcript.toLowerCase();
      const s = stateRef.current;
      if (/\b(next|aage|agla)\b/.test(said)) s.goTo(s.i + 1);
      else if (/\b(back|previous|peeche|pichla)\b/.test(said)) s.goTo(s.i - 1);
      else if (/\b(repeat|again|dobara)\b/.test(said)) speak(`Step ${s.i + 1}. ${s.step.text}`);
      else if (/timer/.test(said) && s.step.minutes) { s.startTimer(s.step.minutes, `Step ${s.i + 1}`); speak(`Timer started for ${s.step.minutes} minutes`); }
    };
    rec.onend = () => { if (!stopped) { try { rec.start(); } catch { /* */ } } };
    try { rec.start(); } catch { /* */ }
    recRef.current = rec;
    return () => { stopped = true; try { rec.stop(); } catch { /* */ } };
  }, [handsFree]);

  // Whistle listening (beta): counts loud, high-pitched sounds lasting over half a second.
  useEffect(() => {
    if (!listenWhistle) return;
    let stream, ctx, raf, loudSince = 0, cooldownUntil = 0, cancelled = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) return;
        ctx = new (window.AudioContext || window.webkitAudioContext)();
        const an = ctx.createAnalyser(); an.fftSize = 2048;
        ctx.createMediaStreamSource(stream).connect(an);
        const freq = new Uint8Array(an.frequencyBinCount);
        const binHz = ctx.sampleRate / an.fftSize;
        const loop = () => {
          an.getByteFrequencyData(freq);
          let hi = 0, all = 0;
          freq.forEach((v, k) => { all += v; if (k * binHz > 1500) hi += v; });
          const loud = all / freq.length > 40 && hi / Math.max(1, all) > 0.55;
          const t = performance.now();
          if (loud && t > cooldownUntil) {
            if (!loudSince) loudSince = t;
            if (t - loudSince > 600) {
              cooldownUntil = t + 5000; loudSince = 0;
              const k = stateRef.current.i;
              setWhistles(w => ({ ...w, [k]: (w[k] || 0) + 1 }));
            }
          } else if (!loud) loudSince = 0;
          raf = requestAnimationFrame(loop);
        };
        loop();
      } catch {
        notify('Microphone not available. Tap the button for each whistle instead.');
        setListenWhistle(false);
      }
    })();
    return () => { cancelled = true; cancelAnimationFrame(raf); stream && stream.getTracks().forEach(t => t.stop()); ctx && ctx.close(); };
  }, [listenWhistle]);

  // Alert when the whistle count is reached.
  const wCount = whistles[i] || 0;
  const wTarget = step.whistles;
  const alerted = useRef({});
  useEffect(() => {
    if (wTarget && wCount >= wTarget && !alerted.current[i]) {
      alerted.current[i] = true; beep(4);
      notify('That\'s enough whistles! Turn off the stove and let the pressure drop on its own.');
      if (readAloud) speak('Turn off the stove now.');
    }
  }, [wCount, wTarget, i]);

  if (finishing) return <Finish recipe={recipe} pantry={pantry} setPantry={setPantry} setHistory={setHistory} notify={notify} />;

  return (
    <div className="screen cook">
      <div className="cook-top">
        <button className="icon-btn" onClick={() => go('recipe/' + recipe.id)} aria-label="Exit cook mode">✕</button>
        <div className="cook-title">{recipe.name}</div>
        <button className="btn bachao sm" onClick={() => setShowBachao(true)}>🛟 Bachao!</button>
      </div>
      <div className="progress" aria-label={`Step ${i + 1} of ${steps.length}`}><div style={{ width: `${((i + 1) / steps.length) * 100}%` }} /></div>

      <div className="step-num">Step {i + 1} of {steps.length}</div>
      <p className="step-text" aria-live="polite">{step.text}</p>

      {step.minutes && (
        <button className="btn timer-btn" onClick={() => startTimer(step.minutes, `Step ${i + 1}`)}>⏱ Start {step.minutes}-minute timer</button>
      )}

      {wTarget && (
        <div className="whistle card">
          <div className="whistle-count"><b>{wCount}</b> / {wTarget} whistles</div>
          <button className="btn primary big" onClick={() => setWhistles(w => ({ ...w, [i]: (w[i] || 0) + 1 }))}>I heard a whistle (+1)</button>
          <div className="row">
            <button className="btn link" onClick={() => setWhistles(w => ({ ...w, [i]: Math.max(0, (w[i] || 0) - 1) }))}>Undo</button>
            <label className="switch"><input type="checkbox" checked={listenWhistle} onChange={e => setListenWhistle(e.target.checked)} /> Listen for whistles (beta)</label>
          </div>
        </div>
      )}

      {timers.length > 0 && (
        <div className="timers">
          {timers.map(t => {
            const left = Math.max(0, Math.round((t.endsAt - now) / 1000));
            return (
              <div key={t.id} className={'timer' + (t.done ? ' done' : '')}>
                <span>{t.label}</span><b>{t.done ? 'Done!' : fmtTime(left)}</b>
                <button className="icon-btn sm" onClick={() => setTimers(ts => ts.filter(x => x.id !== t.id))} aria-label="Remove timer">✕</button>
              </div>
            );
          })}
        </div>
      )}

      <div className="cook-tools">
        <label className="switch"><input type="checkbox" checked={readAloud} onChange={e => setReadAloud(e.target.checked)} /> 🔊 Read steps aloud</label>
        {SpeechRec && <label className="switch"><input type="checkbox" checked={handsFree} onChange={e => setHandsFree(e.target.checked)} /> 🎤 Hands-free ("next", "back", "repeat", "timer")</label>}
      </div>

      <div className="cook-nav">
        <button className="btn ghost big" onClick={() => goTo(i - 1)} disabled={i === 0}>‹ Back</button>
        {last
          ? <button className="btn primary big" onClick={() => { stopSpeaking(); setFinishing(true); }}>Done cooking ✓</button>
          : <button className="btn primary big" onClick={() => goTo(i + 1)}>Next ›</button>}
      </div>

      {showBachao && (
        <div className="sheet" role="dialog" aria-label="Bachao: kitchen rescue">
          <div className="sheet-inner">
            <div className="row between"><h3>What went wrong?</h3><button className="icon-btn" onClick={() => setShowBachao(false)} aria-label="Close">✕</button></div>
            <BachaoList />
          </div>
        </div>
      )}
    </div>
  );
}

function Finish({ recipe, pantry, setPantry, setHistory, notify }) {
  const [rating, setRating] = useState(0);
  const soonIds = new Set(useSoon(pantry).map(p => p.id));
  // Perishable items from this recipe that are in the kitchen: offer to mark them used up.
  const usable = pantry.filter(p => BY_ID[p.id]?.shelfDays && BY_ID[p.id].shelfDays <= 7 && recipe.ingredients.some(it => it.options.includes(p.id)));
  const [used, setUsed] = useState(() => new Set(usable.filter(p => soonIds.has(p.id)).map(p => p.id)));

  function save() {
    const saved = [...used].filter(id => soonIds.has(id));
    setHistory(h => [...h, { recipeId: recipe.id, name: recipe.name, at: Date.now(), rating: rating || null, saved }]);
    if (used.size) setPantry(pantry.filter(p => !used.has(p.id)));
    notify(saved.length ? `Saved! You rescued ${saved.length} item(s) from going to waste.` : 'Saved! Enjoy your meal.');
    go('home');
  }

  return (
    <div className="screen finish">
      <h2>Bon appétit! 🎉</h2>
      <p>How did <b>{recipe.name}</b> turn out?</p>
      <Stars value={rating} onChange={setRating} size="lg" />
      <p className="muted small">Your ratings teach Ballava your taste (your "andaaz").</p>
      {usable.length > 0 && (
        <div className="card">
          <h3>Did you use these up?</h3>
          {usable.map(p => (
            <label key={p.id} className="check">
              <input type="checkbox" checked={used.has(p.id)} onChange={e => { const n = new Set(used); e.target.checked ? n.add(p.id) : n.delete(p.id); setUsed(n); }} />
              {ingName(p.id)} {soonIds.has(p.id) && <span className="pill warn">was about to spoil</span>}
            </label>
          ))}
          <p className="muted small">Ticked items are removed from your kitchen.</p>
        </div>
      )}
      <button className="btn primary big" onClick={save}>Save and finish</button>
    </div>
  );
}
