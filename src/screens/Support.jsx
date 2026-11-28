import React, { useEffect, useState } from 'react';
import { Header, Empty } from '../ui.jsx';
import { api, go } from '../lib.js';

// Help & support: tell the Ballava team about a problem, or ask a question. Admins answer in the admin portal,
// and the answer shows here (and as a red dot on More). Private to you: your family doesn't see these.
//   #/support        your requests
//   #/support/new    send a new one
//   #/support/12     one request, with the conversation
const TOPICS = [
  ['problem', '🐞', "Something isn't working"],
  ['account', '👤', 'Sign-in or account'],
  ['recipe', '📖', 'A recipe or ingredient is wrong'],
  ['idea', '💡', 'Idea or suggestion'],
  ['other', '💬', 'Something else'],
];
const ICON = Object.fromEntries(TOPICS.map(([id, icon]) => [id, icon]));
const STATUS_CLASS = { open: 'warn', in_progress: 'info', resolved: 'good' };
const when = iso => new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
const day = iso => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

const StatusPill = ({ r }) => <span className={'pill ' + (STATUS_CLASS[r.status] || '')}>{r.statusLabel}</span>;

export default function Support({ auth, notify, param, setSupportUnread }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState(null);
  const signedIn = !!auth.user;

  const load = () => api('support').then(d => { setList(d.requests); setError(null); }).catch(e => setError(e.message));
  useEffect(() => {
    if (!signedIn) return undefined;
    load();
    window.addEventListener('focus', load); // a reply may have come while you were away
    return () => window.removeEventListener('focus', load);
  }, [signedIn]);
  useEffect(() => { if (list) setSupportUnread(list.filter(r => r.unread).length); }, [list]);
  // The server's latest copy of one request goes to the top (it was just updated).
  const replace = fresh => setList(l => [fresh, ...(l || []).filter(x => x.id !== fresh.id)]);

  if (!signedIn) {
    return (
      <div className="screen">
        <Header title="Help & support" back="more" />
        <div className="card">
          <h3>Sign in to contact the team</h3>
          <p>The Ballava team answers you here in the app, so they need to know whose request it is.</p>
          <button className="btn primary big" onClick={() => { try { localStorage.removeItem('ballava.guest'); } catch { /* ok */ } location.reload(); }}>Sign in</button>
        </div>
      </div>
    );
  }

  if (param === 'new') {
    return <NewRequest notify={notify} onSent={r => { replace(r); go('support/' + r.id); notify('Sent. The team will answer here.'); }} />;
  }

  if (param) {
    const r = list?.find(x => String(x.id) === param);
    if (r) return <Thread r={r} setList={setList} replace={replace} notify={notify} />;
    return (
      <div className="screen">
        <Header title="Help & support" back="support" />
        {error ? <div className="note warn">{error}</div>
          : list ? <Empty title="Request not found">It may have been removed. <button className="btn link" onClick={() => go('support')}>See all requests</button></Empty>
            : <p className="muted thinking" role="status">Loading…</p>}
      </div>
    );
  }

  return (
    <div className="screen">
      <Header title="Help & support" back="more" />
      <p className="muted">Something not working, or a question? Tell the Ballava team, and they'll answer here.</p>
      <button className="btn primary big" onClick={() => go('support/new')}>➕ New request</button>
      {error && <div className="note warn">{error} <button className="btn link" onClick={load}>Try again</button></div>}
      {!list && !error && <p className="muted thinking" role="status">Loading…</p>}
      {list && !list.length && <Empty title="No requests yet">When you send one, you can follow it here.</Empty>}
      {list?.length > 0 && (
        <div className="menu support-list">
          {list.map(r => (
            <button key={r.id} className="menu-item" onClick={() => go('support/' + r.id)}
              aria-label={`${r.subject}, ${r.statusLabel}${r.unread ? ', new reply from the team' : ''}`}>
              <span className="menu-icon" aria-hidden="true">{ICON[r.category] || '💬'}</span>
              <span><b>{r.subject}</b><span className="muted small">#{r.id} · updated {day(r.updatedAt)}</span></span>
              <span className="support-tags">{r.unread && <span className="pill warn">New reply</span>}<StatusPill r={r} /></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function NewRequest({ onSent, notify }) {
  const [topic, setTopic] = useState('problem');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try { onSent((await api('support', { category: topic, subject, message })).request); } catch (err) { notify(err.message); }
    setBusy(false);
  }

  return (
    <div className="screen">
      <Header title="New request" back="support" />
      <form className="card form" onSubmit={submit}>
        <fieldset>
          <legend>What is it about?</legend>
          <div className="chips wrap">
            {TOPICS.map(([id, icon, label]) => (
              <button type="button" key={id} className={'chip' + (topic === id ? ' on' : '')} aria-pressed={topic === id} onClick={() => setTopic(id)}>{icon} {label}</button>
            ))}
          </div>
        </fieldset>
        <label>In a few words
          <input value={subject} maxLength={100} onChange={e => setSubject(e.target.value)} placeholder="e.g. The timer stops when the screen turns off" />
        </label>
        <label>What happened?
          <textarea rows={6} value={message} maxLength={2000} onChange={e => setMessage(e.target.value)}
            placeholder="What did you do, what did you expect, and what happened instead?" />
        </label>
        <p className="muted small">Only you and the Ballava team see this, not your family. Please don't write passwords or sign-in codes. The name of your browser is sent too, to help find the problem.</p>
        <button className="btn primary big" type="submit" disabled={busy || !subject.trim() || !message.trim()}>Send to the team</button>
      </form>
    </div>
  );
}

function Thread({ r, setList, replace, notify }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const resolved = r.status === 'resolved';
  const answered = r.messages.some(m => m.fromTeam);

  // Opening it means the team's replies are no longer new.
  useEffect(() => {
    if (!r.unread) return;
    api(`support/${r.id}/read`, {}).then(() => setList(l => l.map(x => (x.id === r.id ? { ...x, unread: false } : x)))).catch(() => {});
  }, [r.id, r.unread]);

  async function run(fn) {
    setBusy(true);
    try { await fn(); } catch (e) { notify(e.message); }
    setBusy(false);
  }

  return (
    <div className="screen">
      <Header title={`Request #${r.id}`} back="support" />
      <div className="card">
        <div className="row between"><h3>{r.subject}</h3><StatusPill r={r} /></div>
        <p className="muted small">{ICON[r.category]} {r.categoryLabel} · sent {day(r.createdAt)}</p>
      </div>
      <div className="chat support-thread" aria-label="Messages">
        {r.messages.map((m, i) => (
          <div key={i} className={'bubble ' + (m.fromTeam ? 'team' : 'me')}>
            {m.fromTeam && <b className="bubble-from">Ballava team</b>}
            {m.text}
            <div className="bubble-note">{when(m.at)}</div>
          </div>
        ))}
      </div>
      {!answered && !resolved && <p className="note info">The team will answer here. You'll see a red dot on More when they do.</p>}
      {resolved && <p className="note info">This is resolved. Still having trouble? Write below and it opens again.</p>}
      <form className="card form" onSubmit={e => {
        e.preventDefault();
        run(async () => { replace((await api(`support/${r.id}/reply`, { text })).request); setText(''); });
      }}>
        <label>{resolved ? 'Write again' : 'Add a message'}
          <textarea rows={3} value={text} maxLength={2000} onChange={e => setText(e.target.value)} />
        </label>
        <div className="row">
          <button className="btn primary" type="submit" disabled={busy || !text.trim()}>Send</button>
          {!resolved && (
            <button type="button" className="btn ghost" disabled={busy}
              onClick={() => run(async () => { replace((await api(`support/${r.id}/resolve`, {})).request); notify('Marked as solved. Thank you!'); })}>
              ✓ My problem is solved
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
