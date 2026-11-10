import React, { useState } from 'react';
import { shoppingText } from '../catalog.js';
import { Header, Empty, ingName } from '../ui.jsx';
import { whatsappLink, api } from '../lib.js';

export default function Shopping({ shopping, setShopping, addToShopping, addToPantry, notify }) {
  const [text, setText] = useState('');
  const open = shopping.filter(s => !s.done);
  const done = shopping.filter(s => s.done);

  async function add(e) {
    e.preventDefault();
    let found, unknown;
    try { ({ found, unknown } = await api('parse', { text })); } catch (err) { notify(err.message); return; }
    addToShopping(found);
    if (unknown.length) notify(`Didn't recognise: ${unknown.join(', ')}`);
    setText('');
  }
  const toggle = id => setShopping(shopping.map(s => (s.id === id ? { ...s, done: !s.done } : s)));

  function bought() {
    const ids = done.map(s => s.id);
    const added = addToPantry(ids);
    setShopping(open);
    notify(`Moved ${added.length} item(s) into your kitchen`);
  }

  return (
    <div className="screen">
      <Header title="Shopping list" />
      <form className="add-bar" onSubmit={add}>
        <input value={text} onChange={e => setText(e.target.value)} placeholder="Add items: paneer, dhaniya…" aria-label="Add to shopping list" />
        <button className="btn primary" type="submit">Add</button>
      </form>
      {shopping.length === 0 && <Empty title="Your list is empty">Open any recipe and tap "Add missing to shopping list".</Empty>}
      <ul className="shop-list">
        {[...open, ...done].map(s => (
          <li key={s.id} className={s.done ? 'done' : ''}>
            <label className="check"><input type="checkbox" checked={s.done} onChange={() => toggle(s.id)} /> {ingName(s.id)}</label>
            <button className="icon-btn sm remove" onClick={() => setShopping(shopping.filter(x => x.id !== s.id))} aria-label={`Remove ${ingName(s.id)}`}>✕</button>
          </li>
        ))}
      </ul>
      {shopping.length > 0 && (
        <div className="stack">
          {done.length > 0 && <button className="btn primary" onClick={bought}>✓ I bought the ticked items: add to my kitchen</button>}
          {open.length > 0 && <a className="btn whatsapp" href={whatsappLink(shoppingText(open.map(s => s.id)))} target="_blank" rel="noreferrer">Share list on WhatsApp</a>}
        </div>
      )}
    </div>
  );
}
