// The admin's recipe editor (kitchen/templates/kitchen/recipe_form.html).
// It draws friendly boxes over the ordinary form fields, and keeps those fields filled in the recipe book's own format
// ("toor_dal:1 cup", "Simmer. |5m"), so saving works exactly as it always has. The thinking is in Python: recipe_editor.py.
(() => {
  const root = document.getElementById('recipe-editor');
  const source = document.getElementById('recipe-editor-data');
  if (!root || !source) return;
  const data = JSON.parse(source.textContent);
  const form = root.closest('form');
  const $ = (sel, from = root) => from.querySelector(sel);
  const field = k => document.getElementById('id_' + k);
  const byId = Object.fromEntries(data.ingredients.map(i => [i.id, i]));
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  let dirty = false, last = null;

  function el(tag, props = {}, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
      else if (k in node && k !== 'list') node[k] = v;
      else node.setAttribute(k, v === true ? '' : v);
    }
    node.append(...kids.filter(x => x != null));
    return node;
  }
  async function ask(tool, body) {
    const res = await fetch(`${data.tools}${tool}/`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify(body) });
    let out = null;
    try { out = await res.json(); } catch { /* not JSON: signed out, or the server is down */ }
    if (!res.ok || !out) throw new Error(out?.error || (res.status === 403 ? 'Please sign in again in another tab, then come back.' : 'That did not work. Please try again.'));
    return out;
  }
  function say(text, kind = 'info') {
    const box = $('#re-msg');
    box.replaceChildren(...(text ? [el('div', { className: 'b-note ' + kind, textContent: text })] : []));
    if (text) box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  async function busy(button, label, work) {
    const was = button.textContent;
    button.disabled = true;
    button.textContent = label;
    say('');
    try { await work(); } catch (e) { say(e.message, 'bad'); }
    button.disabled = false;
    button.textContent = was;
  }

  // ------------------------------------------------------------ the recipe, as rows
  const clean = s => s.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim();
  const tidy = s => clean(s.replace(/[|?:]/g, ' ')).toLowerCase().slice(0, 40);
  const blankIng = () => ({ options: [], qty: '', optional: false, from: '' });
  const blankStep = () => ({ text: '', kind: '', n: '' });
  const toStep = s => ({ text: s.text, kind: s.minutes ? 'm' : s.whistles ? 'w' : '', n: s.minutes || s.whistles || '' });
  function readIng(line) {
    const at = line.indexOf(':');
    let key = at < 0 ? line : line.slice(0, at);
    const optional = key.endsWith('?');
    if (optional) key = key.slice(0, -1);
    return { options: key.split('|').map(s => s.trim()).filter(Boolean), qty: at < 0 ? '' : line.slice(at + 1).trim(), optional, from: '' };
  }
  function readStep(line) {
    const m = line.match(/^(.*?)\s*\|(\d+)([mw])\s*$/);
    return m ? { text: m[1], kind: m[3], n: m[2] } : { text: line, kind: '', n: '' };
  }
  const lines = k => field(k).value.split('\n').map(s => s.trim()).filter(Boolean);
  let ings = lines('ingredients').map(readIng);
  let steps = lines('steps').map(readStep);
  const filled = () => ings.filter(r => r.options.length);

  function sync(changed = true) {
    field('ingredients').value = filled().map(r => r.options.join('|') + (r.optional ? '?' : '') + (clean(r.qty) ? ':' + clean(r.qty) : '')).join('\n');
    field('steps').value = steps.filter(s => clean(s.text)).map(s => clean(s.text) + (s.kind && Number(s.n) > 0 ? ` |${Math.round(s.n)}${s.kind}` : '')).join('\n');
    if (changed) dirty = true;
    scheduleCheck();
  }

  // ------------------------------------------------------------ ingredients
  function search(q) {
    const s = q.toLowerCase().trim();
    if (!s) return [];
    const out = [];
    for (const ing of data.ingredients) {
      const name = ing.name.toLowerCase();
      const alias = ing.aliases.find(a => a.toLowerCase().startsWith(s)) || ing.aliases.find(a => a.toLowerCase().includes(s));
      const score = name === s ? 0 : name.startsWith(s) ? 1 : alias && alias.toLowerCase() === s ? 1 : alias && alias.toLowerCase().startsWith(s) ? 2 : name.includes(s) ? 3 : alias && s.length > 2 ? 4 : null;
      if (score != null) out.push({ ing, alias: name.includes(s) ? '' : alias, score });
    }
    return out.sort((a, b) => a.score - b.score || a.ing.name.length - b.ing.name.length).slice(0, 7);
  }
  const exact = q => data.ingredients.find(i => [i.name, ...i.aliases].some(n => n.toLowerCase() === q.toLowerCase().trim()));

  // A row's search box. Typing "2 cups toor dal" and Enter, or pasting a list, fills whole rows.
  function combo(row) {
    let hits = [], at = -1;
    const list = el('ul', { className: 're-hits', role: 'listbox', hidden: true });
    const input = el('input', { type: 'text', className: 're-name', role: 'combobox', autocomplete: 'off', placeholder: row.options.length ? 'or which ingredient?' : 'Ingredient', 'aria-label': 'Ingredient', 'aria-expanded': 'false', 'aria-autocomplete': 'list' });
    const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); at = -1; };
    function choose(id) {
      if (!row.options.includes(id)) row.options.push(id);
      row.adding = false;
      drawIngs(row, 'qty');
    }
    const pickHit = h => (h.add ? openNew(h.add, row, null) : choose(h.ing.id));
    function draw() {
      const q = input.value.trim();
      hits = /\d/.test(q) ? [] : search(q);
      if (q.length > 1 && !/\d/.test(q) && data.canAddIngredient && !exact(q)) hits.push({ add: q });
      at = hits.length && !hits[0].add ? 0 : -1;
      list.replaceChildren(...hits.map((h, i) => el('li', { role: 'option', className: i === at ? 'on' : '', 'aria-selected': String(i === at), onmousedown: e => { e.preventDefault(); pickHit(h); } },
        h.add ? `➕ Add “${h.add}” as a new ingredient` : h.ing.name, h.alias ? el('small', { textContent: ' ' + h.alias }) : null)));
      list.hidden = !hits.length;
      input.setAttribute('aria-expanded', String(!!hits.length));
    }
    async function wholeLines(text) {
      const { ingredients } = await ask('lines', { text });
      const i = ings.indexOf(row);
      const rows = ingredients.map(r => ({ ...r, options: [...r.options] }));
      if (!rows.length) return;
      ings.splice(i, row.options.length ? 0 : 1, ...rows);
      const next = blankIng();
      ings.splice(i + rows.length, 0, next);
      drawIngs(next, 'name');
    }
    input.addEventListener('input', () => { dirty = true; draw(); });
    input.addEventListener('paste', e => {
      const text = e.clipboardData.getData('text');
      if (!/\n/.test(text.trim())) return;
      e.preventDefault();
      wholeLines(text).catch(err => say(err.message, 'bad'));
    });
    input.addEventListener('keydown', e => {
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && hits.length) {
        e.preventDefault();
        at = (at + (e.key === 'ArrowDown' ? 1 : -1) + hits.length) % hits.length;
        [...list.children].forEach((li, i) => { li.className = i === at ? 'on' : ''; li.setAttribute('aria-selected', String(i === at)); });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (at >= 0 && hits[at]) pickHit(hits[at]);
        else if (input.value.trim()) { const text = input.value; input.value = ''; wholeLines(text).catch(err => { input.value = text; say(err.message, 'bad'); }); }
      } else if (e.key === 'Escape') close();
    });
    input.addEventListener('blur', () => setTimeout(() => {
      if (!input.isConnected) return;
      close();
      const q = input.value.trim();
      if (!q) { if (row.adding) { row.adding = false; drawIngs(); } return; }
      const known = exact(q);
      if (known) { if (!row.options.includes(known.id)) row.options.push(known.id); row.adding = false; drawIngs(); } else if (/\d/.test(q)) { input.value = ''; wholeLines(q).catch(err => say(err.message, 'bad')); } else { row.options.push(tidy(q)); row.adding = false; drawIngs(); }
    }, 120));
    return el('span', { className: 're-combo' }, input, list);
  }
  const mover = (list, row, redraw, what) => {
    const i = list.indexOf(row);
    const go = to => { list.splice(i, 1); list.splice(to, 0, row); redraw(); };
    return el('span', { className: 're-move' },
      el('button', { type: 'button', textContent: '↑', disabled: i === 0, 'aria-label': `Move ${what} up`, onclick: () => go(i - 1) }),
      el('button', { type: 'button', textContent: '↓', disabled: i === list.length - 1, 'aria-label': `Move ${what} down`, onclick: () => go(i + 1) }),
      el('button', { type: 'button', className: 'x', textContent: '✕', 'aria-label': `Remove ${what}`, onclick: () => { list.splice(i, 1); redraw(); } }));
  };
  function ingRow(row, i) {
    const what = `ingredient ${i + 1}`;
    const main = el('span', { className: 're-ing' });
    row.options.forEach((o, k) => {
      const known = byId[o];
      if (k) main.append(el('span', { className: 're-or', textContent: 'or' }));
      main.append(el('span', { className: 're-chip' + (known ? '' : ' unknown') }, known ? known.name : `${o}?`,
        el('button', { type: 'button', textContent: '✕', 'aria-label': `Take out ${known ? known.name : o}`, onclick: () => { row.options.splice(k, 1); drawIngs(row, 'name'); } })));
      if (!known) main.append(el('button', { type: 'button', className: 're-link', textContent: data.canAddIngredient ? 'Add to the ingredient list' : 'Not in the list', disabled: !data.canAddIngredient, onclick: () => openNew(o, row, k) }));
    });
    if (!row.options.length || row.adding) main.append(combo(row));
    else main.append(el('button', { type: 'button', className: 're-link', textContent: 'or…', 'aria-label': `Add another choice to ${what}`, title: 'Any one of these works', onclick: () => { row.adding = true; drawIngs(row, 'name'); } }));
    const qty = el('input', { type: 'text', className: 're-qty', value: row.qty, maxLength: 60, list: 're-amounts', placeholder: 'How much?', 'aria-label': `Amount of ${what}`, oninput: e => { row.qty = e.target.value; sync(); },
      onkeydown: e => { if (e.key === 'Enter') { e.preventDefault(); addIng(i + 1); } } });
    const li = el('li', { className: 're-row' }, main, qty,
      el('label', { className: 're-opt' }, el('input', { type: 'checkbox', checked: row.optional, onchange: e => { row.optional = e.target.checked; sync(); } }), ' optional'),
      el('span', { className: 're-kcal' }), mover(ings, row, drawIngs, what));
    if (row.from) li.append(el('span', { className: 're-hint' }, `Read from “${row.from}”. Is that right? `, el('button', { type: 'button', className: 're-link', textContent: 'Yes', onclick: () => { row.from = ''; drawIngs(); } })));
    return li;
  }
  function drawIngs(focusRow, what) {
    if (!ings.length) ings.push(blankIng());
    const list = $('#re-ing-list');
    list.replaceChildren(...ings.map(ingRow));
    showLines();
    sync();
    const at = focusRow ? ings.indexOf(focusRow) : -1;
    if (at >= 0) list.children[at].querySelector(what === 'qty' ? '.re-qty' : '.re-name')?.focus();
  }
  function addIng(at = ings.length) {
    // An empty row is already waiting there: use it.
    const row = ings[at] && !ings[at].options.length ? ings[at] : blankIng();
    if (ings[at] !== row) ings.splice(at, 0, row);
    drawIngs(row, 'name');
  }

  // ------------------------------------------------------------ steps
  function detect(s) {
    if (s.kind || s.touched) return;
    const w = s.text.match(/(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*whistles?/i);
    const m = s.text.match(/(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*(min(?:ute)?s?|hours?|hrs?)\b/i);
    if (w) { s.kind = 'w'; s.n = w[2] || w[1]; } else if (m) {
      const n = Number(m[2] || m[1]) * (/^h/i.test(m[3]) ? 60 : 1);
      if (n > 0 && n <= 240) { s.kind = 'm'; s.n = n; }
    }
  }
  const grow = t => { t.style.height = 'auto'; t.style.height = Math.max(44, t.scrollHeight + 2) + 'px'; };
  function stepRow(s, i) {
    const what = `step ${i + 1}`;
    const number = el('input', { type: 'number', min: 1, max: 240, className: 're-n', value: s.n, hidden: !s.kind, 'aria-label': `Timer number for ${what}`, oninput: e => { s.n = e.target.value; s.touched = true; sync(); } });
    const kind = el('select', { 'aria-label': `Timer for ${what}`, onchange: e => { s.kind = e.target.value; s.touched = true; number.hidden = !s.kind; if (s.kind && !s.n) { s.n = s.kind === 'w' ? 3 : 5; number.value = s.n; } sync(); } },
      el('option', { value: '', textContent: 'No timer' }), el('option', { value: 'm', textContent: '⏱ minutes' }), el('option', { value: 'w', textContent: '♨ whistles' }));
    kind.value = s.kind;
    const text = el('textarea', { rows: 1, value: s.text, placeholder: i ? 'What next?' : 'e.g. Wash the dal and pressure cook it for 3 whistles.', 'aria-label': `Step ${i + 1}`, oninput: e => { s.text = e.target.value; grow(text); sync(); },
      onblur: () => { if (!s.text.trim() || s.kind || s.touched) return; detect(s); if (s.kind) { kind.value = s.kind; number.value = s.n; number.hidden = false; sync(); } },
      onkeydown: e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); detect(s); addStep(i + 1); } },
      onpaste: e => {
        const pasted = e.clipboardData.getData('text');
        if (!/\n/.test(pasted.trim())) return;
        e.preventDefault();
        ask('lines', { text: pasted }).then(r => { steps.splice(i, s.text.trim() ? 0 : 1, ...r.steps.map(toStep)); drawSteps(); }).catch(err => say(err.message, 'bad'));
      } });
    return el('li', { className: 're-row step' }, el('b', { className: 're-num', textContent: i + 1 }), text, el('span', { className: 're-timer' }, kind, number), mover(steps, s, drawSteps, what));
  }
  function drawSteps(focus) {
    if (!steps.length) steps.push(blankStep());
    const list = $('#re-step-list');
    list.replaceChildren(...steps.map(stepRow));
    list.querySelectorAll('textarea').forEach(grow);
    sync();
    if (focus) list.children[steps.indexOf(focus)].querySelector('textarea').focus();
  }
  function addStep(at = steps.length) {
    const s = steps[at] && !steps[at].text.trim() ? steps[at] : blankStep();
    if (steps[at] !== s) steps.splice(at, 0, s);
    drawSteps(s);
  }

  // ------------------------------------------------------------ meals, spice, tags
  const listOf = k => field(k).value.split(',').map(s => s.trim()).filter(Boolean);
  function chips(box, k, choices) {
    const on = listOf(k);
    const all = [...choices, ...on.filter(v => !choices.some(c => c[0] === v)).map(v => [v, v, ''])];
    $(box).replaceChildren(...all.map(([v, label, hint]) => el('button', { type: 'button', className: 're-pick' + (on.includes(v) ? ' on' : ''), 'aria-pressed': String(on.includes(v)), title: hint || '', textContent: label, onclick: () => toggle(k, v) })));
  }
  function drawChips() {
    chips('#re-meals', 'meal', data.meals);
    chips('#re-tags', 'tags', data.tags);
    const spice = field('spice').value;
    $('#re-spice').replaceChildren(...[['1', 'Mild'], ['2', 'Medium 🌶'], ['3', 'Hot 🌶🌶']].map(([v, label]) => el('button', { type: 'button', className: 're-pick' + (spice === v ? ' on' : ''), 'aria-pressed': String(spice === v), textContent: label, onclick: () => { field('spice').value = v; dirty = true; drawChips(); scheduleCheck(); } })));
  }
  function toggle(k, v) {
    const on = listOf(k);
    const order = (k === 'meal' ? data.meals : data.tags).map(c => c[0]);
    const next = on.includes(v) ? on.filter(x => x !== v) : [...on, v];
    field(k).value = next.sort((a, b) => (order.indexOf(a) + 1 || 99) - (order.indexOf(b) + 1 || 99)).join(', ');
    dirty = true;
    drawChips();
    scheduleCheck();
  }

  // ------------------------------------------------------------ live checks
  let timer = null, turn = 0;
  function scheduleCheck() { clearTimeout(timer); timer = setTimeout(check, 450); }
  async function check() {
    const mine = ++turn;
    const body = Object.fromEntries(['recipe_id', 'name', 'cuisine', 'meal', 'tags', 'time', 'serves', 'spice', 'ingredients', 'steps', 'safety'].map(k => [k, field(k).value]));
    try {
      const res = await ask('check', body);
      if (mine === turn) { last = res; showCheck(); }
    } catch (e) { if (mine === turn) $('#re-check').replaceChildren(el('h3', { textContent: 'Checks' }), el('p', { className: 'b-muted', textContent: e.message })); }
  }
  const PLACES = { name: '#id_name', time: '#id_time', serves: '#id_serves', meal: '#re-meals button', ingredients: '#re-ing-list input', steps: '#re-step-list textarea', tags: '#re-tags button', safety: '#id_safety', recipe_id: '#id_recipe_id' };
  function jump(name) {
    const target = (name === 'ingredients' && ($('.re-chip.unknown') || $('.re-kcal.unclear')?.closest('li').querySelector('.re-qty'))) || $(PLACES[name] || '#id_name');
    if (!target) return;
    target.closest('details')?.setAttribute('open', '');
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    if (target.focus) target.focus({ preventScroll: true });
  }
  function showLines() {
    const rows = filled();
    [...$('#re-ing-list').children].forEach((li, i) => {
      const at = rows.indexOf(ings[i]);
      const got = at >= 0 ? last?.lines?.[at] : null;
      const box = $('.re-kcal', li);
      box.textContent = got ? (got.unclear ? 'amount?' : `${got.kcal} kcal`) : '';
      box.className = 're-kcal' + (got?.unclear ? ' unclear' : '');
      box.title = got && !got.unclear ? `About ${got.grams} g` : '';
    });
  }
  function showCheck() {
    showLines();
    if (!last.problems.length && $('#re-msg .blocked')) say('');
    const { problems, advice, nutrition: n, suggested, safety } = last;
    const started = field('name').value.trim() || filled().length;
    const parts = [el('h3', { className: started ? (problems.length ? 'fix' : 'ready') : '', textContent: !started ? 'Checks' : problems.length ? `${problems.length} thing${problems.length > 1 ? 's' : ''} to fix before publishing` : '✓ Ready to publish' })];
    if (!started) parts.push(el('p', { className: 'b-muted', textContent: 'Calories and checks appear here as you type.' }));
    else if (problems.length) {
      parts.push(el('ul', { className: 're-problems' }, ...problems.map(p => el('li', {}, el('button', { type: 'button', className: 're-link', textContent: p.text, onclick: () => jump(p.field) })))));
    }
    if (safety) parts.push(el('button', { type: 'button', className: 're-btn small', textContent: '🛡 Add a food-safety note', title: safety, onclick: () => { field('safety').value = safety; dirty = true; scheduleCheck(); } }));
    if (n && filled().length) {
      parts.push(el('div', { className: 're-kcals' }, el('b', { textContent: n.kcal }), ` kcal a serving · protein ${Math.round(n.protein)} g · carbs ${Math.round(n.carbs)} g · fat ${Math.round(n.fat)} g`));
      parts.push(el('p', { className: 'b-muted' }, el('span', { className: 'diet ' + last.diet }), ` ${{ veg: 'Vegetarian', egg: 'Contains egg', nonveg: 'Non-vegetarian' }[last.diet]} · ${last.allergens.length ? 'contains ' + last.allergens.join(', ') : 'no common allergens'} · ${last.jainOk ? 'Jain OK' : 'not Jain'}${last.needsOnionGarlic ? ' · needs onion or garlic' : ''}`));
      if (n.oilTsp) parts.push(el('p', { className: 'b-muted', textContent: `Counts about ${n.oilTsp} tsp of cooking oil a serving, because the steps fry or temper.` }));
      if (last.uncounted.length) parts.push(el('p', { className: 'b-muted', textContent: `Not counted (no calories known): ${last.uncounted.join(', ')}.` }));
    }
    if (suggested.length) {
      const label = t => data.tags.find(x => x[0] === t)?.[1] || t;
      parts.push(el('div', { className: 're-chips' }, el('span', { className: 'b-muted', textContent: 'Suggested:' }), ...suggested.map(t => el('button', { type: 'button', className: 're-pick small', textContent: '＋ ' + label(t), onclick: () => toggle('tags', t) }))));
    }
    if (advice.length) parts.push(el('ul', { className: 're-advice' }, ...advice.map(a => el('li', {}, a.edit ? el('a', { href: data.recipes.find(r => r.id === a.edit)?.edit, textContent: a.text }) : el('button', { type: 'button', className: 're-link', textContent: a.text, onclick: () => jump(a.field) })))));
    $('#re-check').replaceChildren(...parts);
  }

  // ------------------------------------------------------------ a new ingredient
  const dialog = $('#re-new-ing');
  const box = k => dialog.querySelector(`[data-k=${k}]`);
  let newFor = null;
  box('category').append(...data.categories.map(c => el('option', { value: c, textContent: c })));
  const TEXT = ['name', 'aliases', 'kcal', 'protein', 'carbs', 'fat', 'fibre', 'grams_per_cup', 'grams_per_piece', 'shelf_days'];
  function fillNew(f) {
    for (const k of TEXT) box(k).value = f[k] ?? '';
    box('category').value = f.category;
    box('diet').value = f.diet;
    const has = Array.isArray(f.allergens) ? f.allergens : (f.allergens || '').split(',').map(s => s.trim());
    box('allergens').replaceChildren(...data.allergens.map(a => el('button', { type: 'button', className: 're-pick small' + (has.includes(a) ? ' on' : ''), 'aria-pressed': String(has.includes(a)), textContent: a, onclick: e => { const on = e.target.classList.toggle('on'); e.target.setAttribute('aria-pressed', String(on)); } })));
    if (f.kcal != null) $('details', dialog).open = true;
  }
  async function openNew(name, row, at) {
    newFor = { row, at };
    $('.re-error', dialog).textContent = '';
    $('details', dialog).open = false;
    try { fillNew((await ask('ingredient-guess', { name })).fields); } catch (e) { say(e.message, 'bad'); return; }
    dialog.showModal();
    box('name').focus();
  }
  dialog.addEventListener('click', async e => {
    const act = e.target.dataset.do;
    const error = $('.re-error', dialog);
    if (!act) return;
    if (act === 'cancel') { dialog.close(); return; }
    e.target.disabled = true;
    error.textContent = '';
    try {
      if (act === 'ai') fillNew({ allergens: [], ...(await ask('ingredient-guess', { name: box('name').value, ai: true })).fields });
      else {
        const { ingredient } = await ask('ingredient-add', { ...Object.fromEntries(TEXT.map(k => [k, box(k).value])), category: box('category').value, diet: box('diet').value, allergens: [...box('allergens').querySelectorAll('.on')].map(b => b.textContent) });
        if (!byId[ingredient.id]) { data.ingredients.push(ingredient); byId[ingredient.id] = ingredient; }
        const { row, at } = newFor;
        const word = at == null ? null : row.options[at];
        if (at == null) { if (!row.options.includes(ingredient.id)) row.options.push(ingredient.id); row.adding = false; }
        if (word) for (const r of ings) r.options = r.options.map(o => (o === word ? ingredient.id : o));
        dialog.close();
        drawIngs(row, 'qty');
      }
    } catch (err) { error.textContent = err.message; }
    e.target.disabled = false;
  });

  // ------------------------------------------------------------ ways to start
  const FIELDS = ['name', 'alt', 'cuisine', 'time', 'serves', 'spice', 'prep', 'safety', 'tip', 'recipe_id'];
  function fill({ fields: f, source: from, note }) {
    for (const k of FIELDS) if (f[k] != null && f[k] !== '') field(k).value = String(f[k]).slice(0, field(k).maxLength > 0 ? field(k).maxLength : undefined);
    if (f.meal?.length) field('meal').value = f.meal.join(', ');
    if (f.tags) field('tags').value = f.tags.join(', ');
    ings = (f.ingredients || []).map(r => ({ ...blankIng(), ...r, options: [...r.options] }));
    steps = (f.steps || []).map(toStep);
    last = null;
    drawChips();
    drawIngs();
    drawSteps();
    const look = ings.filter(r => r.from || r.options.some(o => !byId[o])).length;
    const done = { ai: 'The AI filled this in.', text: 'Filled in from your text.', copy: 'Copied. Give it its own name.' }[from];
    say(`${note ? note + ' ' : ''}${done} Please check the amounts and steps${look ? ` (${look} ingredient${look > 1 ? 's' : ''} need${look > 1 ? '' : 's'} a look)` : ''}, then publish.`, note ? 'warn' : 'info');
    showTab('blank');
    field('name').focus({ preventScroll: true });
  }
  const start = $('#re-start');
  const okToReplace = () => !(filled().length || steps.some(s => s.text.trim())) || window.confirm('This replaces what is in the form. Go on?');
  function showTab(name) {
    if (!start) return;
    start.querySelectorAll('[data-tab]').forEach(b => { b.classList.toggle('on', b.dataset.tab === name); b.setAttribute('aria-selected', String(b.dataset.tab === name)); });
    start.querySelectorAll('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== name; });
  }
  if (start) {
    start.hidden = false;
    showTab(field('name').value || filled().length ? 'blank' : data.ai ? 'write' : 'paste');
    start.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { showTab(b.dataset.tab); if (b.dataset.tab === 'blank') field('name').focus(); else start.querySelector(`[data-panel=${b.dataset.tab}] input, [data-panel=${b.dataset.tab}] textarea`)?.focus(); }));
    const write = $('#re-write-go');
    if (write) {
      write.addEventListener('click', () => okToReplace() && busy(write, 'Writing… (about 10 seconds)', async () => fill(await ask('write', { name: $('#re-write-name').value, wish: $('#re-write-wish').value }))));
      for (const id of ['#re-write-name', '#re-write-wish']) $(id).addEventListener('keydown', e => { if (e.key === 'Enter') write.click(); });
    }
    const paste = $('#re-paste-go');
    paste.addEventListener('click', () => okToReplace() && busy(paste, 'Reading…', async () => fill(await ask('read', { text: $('#re-paste').value }))));
    $('#re-copy-list').append(...data.recipes.map(r => el('option', { value: r.name })));
    const chosen = () => {
      const q = $('#re-copy').value.trim().toLowerCase();
      const r = data.recipes.find(x => x.name.toLowerCase() === q) || data.recipes.find(x => q && x.name.toLowerCase().includes(q));
      if (!r) say('Choose a recipe from the list first.', 'warn');
      return r;
    };
    $('#re-copy-new').addEventListener('click', e => { const r = chosen(); if (r && okToReplace()) busy(e.target, 'Copying…', async () => fill(await ask('source', { id: r.id }))); });
    $('#re-copy-edit').addEventListener('click', () => { const r = chosen(); if (r) location.href = r.edit; });
  }

  // ------------------------------------------------------------ go
  $('#re-amounts').append(...data.amounts.map(a => el('option', { value: a })));
  $('#re-ing-add').addEventListener('click', () => addIng());
  $('#re-step-add').addEventListener('click', () => addStep());
  for (const k of ['name', 'cuisine', 'time', 'serves', 'safety', 'recipe_id', 'alt', 'prep', 'tip']) field(k).addEventListener('input', () => { dirty = true; scheduleCheck(); });
  // Enter in a box never saves or publishes by accident.
  form.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.matches('input:not([type=submit])')) e.preventDefault(); });
  form.addEventListener('submit', e => {
    sync(false);
    if (e.submitter?.name === '_publish' && last?.problems.length) {
      e.preventDefault();
      say('Not yet: ' + last.problems.map(p => p.text).join(' '), 'bad blocked');
      jump(last.problems[0].field);
      return;
    }
    if (!field('name').value.trim()) { e.preventDefault(); say('Give the dish a name first.', 'bad'); jump('name'); return; }
    dirty = false;
  });
  window.addEventListener('beforeunload', e => { if (dirty) e.preventDefault(); });
  root.classList.add('on');
  drawChips();
  drawIngs();
  drawSteps();
  dirty = false;
})();
