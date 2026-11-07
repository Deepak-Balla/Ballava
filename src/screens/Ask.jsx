import React, { useEffect, useRef, useState } from 'react';
import { assistantReply } from '../../shared/planner.mjs';
import { Header } from '../ui.jsx';
import { go, listenOnce, SpeechRec } from '../lib.js';
import { t } from '../i18n.js';

const STARTERS = ['What should I cook tonight?', 'Tiffin ideas', "What's planned for tomorrow?", 'What should I prep tonight?'];

export default function Ask({ pantry, members, ratings, log, pins, plan, extraRecipes, hidden, extra, findRecipe }) {
  const [messages, setMessages] = useState([{ from: 'bot', text: 'Hi! Ask me what to cook, or tell me what you have.' }]);
  const [text, setText] = useState('');
  const [listening, setListening] = useState(false);
  const end = useRef(null);

  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }); }, [messages]);

  function ask(question) {
    const q = question.trim();
    if (!q) return;
    const { reply, dishes = [] } = assistantReply(q, { pantry, members, ratings, log, pins, plan, extraRecipes, hidden, extra });
    setMessages(m => [...m, { from: 'me', text: q }, { from: 'bot', text: reply, dishes }]);
    setText('');
  }

  return (
    <div className="screen">
      <Header title={t('Ask Ballava')} back="more" />
      <div className="chat" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={'bubble ' + m.from}>
            {m.text}
            {m.dishes?.length > 0 && (
              <div className="chips wrap">
                {m.dishes.map(id => <button key={id} className="chip" onClick={() => go('recipe/' + id)}>{findRecipe(id)?.name || id}</button>)}
              </div>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="chips scroll">{STARTERS.map(s => <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>)}</div>
      <form className="row nowrap chat-form" onSubmit={e => { e.preventDefault(); ask(text); }}>
        <input aria-label="Your question" value={text} onChange={e => setText(e.target.value)} placeholder="Ask anything about today's food" />
        {SpeechRec && <button type="button" className={'icon-btn mic' + (listening ? ' live' : '')} aria-label="Speak" onClick={() => { setListening(true); listenOnce(ask, () => setListening(false)); }}>🎤</button>}
        <button className="btn primary" type="submit">Send</button>
      </form>
    </div>
  );
}
