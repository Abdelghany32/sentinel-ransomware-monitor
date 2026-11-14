const $ = id => document.getElementById(id);
let data = null, page = 0, sequence = 0, activeClaim = null, activeVersion = 0, detailSequence = 0;
const perPage = 10;
function el(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function params() { return new URLSearchParams({mode: $('mode').value, days: $('days').value, actor: $('actor').value, status: $('status').value, q: $('search').value}); }
async function load() {
  const request = ++sequence;
  try {
    const response = await fetch('/api/dashboard?' + params());
    if (!response.ok) throw new Error('Unable to load dashboard');
    const next = await response.json(); if (request !== sequence) return;
    data = next; $('error').hidden = true;
    const actor = $('actor').value; $('actor').replaceChildren(new Option('All actors', ''));
    data.actors.forEach(a => $('actor').add(new Option(a, a))); $('actor').value = actor;
    $('banner-text').textContent = $('mode').value === 'demo' ? 'DEMO ENVIRONMENT · All organizations and actors shown are fictional.' : 'COLLECTED METADATA · Listings are unverified claims. Coverage depends on your configured sources.';
    $('export').href = '/api/export?' + params();
    const rows = data.records;
    $('stats').replaceChildren();
    const recent = rows.filter(r => Date.now() - Date.parse(r.first_seen) < 86400000).length;
    [['Tracked claims', rows.length, 'Within selected filters'], ['New in 24 hours', recent, 'First observed, UTC'], ['Observed actors', new Set(rows.map(r => r.actor)).size, 'Within selected filters'], ['Watchlist matches', rows.filter(r => r.matches.length).length, 'Claims matching any keyword']].forEach(([title, value, caption]) => {
      const card = el('div', undefined, 'stat'); card.append(el('span', title), el('strong', value), el('small', caption)); $('stats').append(card);
    });
    $('timeline').replaceChildren();
    const dates = []; const today = new Date();
    for (let i = Number($('days').value) - 1; i >= 0; i--) { const day = new Date(today); day.setUTCDate(day.getUTCDate() - i); dates.push(day.toISOString().slice(0, 10)); }
    const max = Math.max(1, ...Object.values(data.timeline));
    dates.forEach(date => { const count = data.timeline[date] || 0; const bar = el('div', undefined, 'bar'); bar.style.height = Math.max(1, count / max * 100) + '%'; bar.title = `${date}: ${count} new claims`; bar.setAttribute('aria-label', bar.title); $('timeline').append(bar); });
    $('sectors').replaceChildren();
    Object.entries(data.sectors).sort((a,b) => b[1]-a[1]).slice(0,6).forEach(([name,count]) => {
      const block = el('div', undefined, 'sector'), label = el('div', undefined, 'sector-label'), meter = el('div', undefined, 'meter'), fill = el('div', undefined, 'fill');
      label.append(el('span', name), el('span', count)); fill.style.width = count / Math.max(1, rows.length) * 100 + '%'; meter.append(fill); block.append(label,meter); $('sectors').append(block);
    });
    if (!rows.length) $('sectors').append(el('p', 'No observations in this selection.', 'empty'));
    $('terms').replaceChildren();
    data.watchlist.forEach(term => { const button = el('button', term + ' ×'); button.title = 'Remove ' + term; button.onclick = () => watch(term, 'delete'); $('terms').append(button); });
    $('tor-health').replaceChildren();
    (data.transport_checks || []).forEach(check => {
      const card = el('div', undefined, 'source-card');
      card.append(el('strong', `Tor route diagnostic: ${check.status}`), el('p', check.detail), el('p', `Checked ${check.checked_at} · ${check.proxy}`));
      $('tor-health').append(card);
    });
    $('source-health').replaceChildren();
    (data.sources || []).forEach(source => {
      const card = el('div', undefined, 'source-card');
      card.append(el('strong', source.name), el('span', 'Sync: ' + source.freshness, 'tag'));
      card.append(el('p', source.transport === 'tor_onion' ? 'DIRECT ONION · Tor SOCKS transport' : 'PUBLIC API · HTTPS feed'));
      card.append(el('p', `Last successful sync: ${source.last_success || 'Never'}`));
      card.append(el('p', `Latest provider observation: ${source.latest_source_at || 'Not supplied'}`));
      card.append(el('p', `Eligible to poll after: ${source.next_poll || 'Next worker check'} · ${source.failures} consecutive failures`));
      if (source.error) card.append(el('p', source.error, 'source-error'));
      $('source-health').append(card);
    });
    if (!(data.sources || []).length) $('source-health').append(el('p', 'No live source configured. Start the monitor command to connect the public feed.'));
    $('runs').replaceChildren();
    data.runs.slice(0,4).forEach(run => { const n = el('div', undefined, 'run'); const head = el('div'); head.append(el('i', undefined, 'status-dot ' + (run.status === 'ok' ? 'ok' : 'bad')), el('strong', `${run.source} · ${run.added} new`)); n.append(head, el('span', `${run.started_at.slice(0,16).replace('T',' ')} UTC · ${run.error || run.observed + ' observed'}`)); $('runs').append(n); });
    if (!data.runs.length) $('runs').append(el('p', 'No collection runs yet. Configure a source and run the collector from the terminal.', 'empty'));
    renderTable(); $('updated').textContent = 'Refreshed ' + new Date().toLocaleTimeString();
  } catch (error) { $('error').hidden = false; $('error').textContent = error.message; }
}
function renderTable() {
  const rows = data.records; page = Math.min(page, Math.max(0, Math.ceil(rows.length / perPage)-1));
  $('rows').replaceChildren(); $('count').textContent = `(${rows.length})`;
  rows.slice(page*perPage, (page+1)*perPage).forEach(row => {
    const tr = el('tr'), name = el('td'), button = el('button', row.name, 'name'); button.onclick = () => detail(row); name.append(button);
    const actor = el('td'); actor.append(el('span',row.actor,'tag'));
    const geo = el('td',row.country); geo.append(el('small',row.sector));
    tr.append(name, actor, geo, el('td',row.first_seen.slice(0,16).replace('T',' ')), el('td', `${row.status} · ${row.priority}`, 'review-status'), el('td',row.matches.join(', ') || '—',row.matches.length ? 'match' : '')); $('rows').append(tr);
  });
  if (!rows.length) { const tr = el('tr'), td = el('td', 'No claims found. Adjust filters, import metadata, or seed the fictional demo.'); td.colSpan = 6; tr.append(td); $('rows').append(tr); }
  $('page').textContent = `Page ${page+1} of ${Math.max(1,Math.ceil(rows.length/perPage))}`; $('prev').disabled = page === 0; $('next').disabled = (page+1)*perPage >= rows.length;
}
async function detail(row) {
  const request = ++detailSequence;
  activeClaim = row.id;
  $('detail-fields').replaceChildren();
  ['name','actor','country','sector','source','source_url','published_at','first_seen','last_seen'].forEach(key => $('detail-fields').append(el('dt',key.replaceAll('_',' ')),el('dd',row[key] || 'Not supplied')));
  $('triage-form').reset(); $('observations').replaceChildren(); $('audit-history').replaceChildren();
  $('save-triage').disabled = true; $('detail-message').textContent = 'Loading assessment…';
  $('detail').showModal();
  try {
    const response = await fetch('/api/investigation?' + new URLSearchParams({id: row.id}));
    if (!response.ok) throw new Error('Unable to load investigation. Close and reopen to retry.');
    const item = await response.json();
    if (request !== detailSequence) return;
    renderInvestigation(item); $('detail-message').textContent = ''; $('save-triage').disabled = false;
  } catch (error) { if (request === detailSequence) $('detail-message').textContent = error.message; }
}
function renderInvestigation(item) {
  activeVersion = item.version;
  $('triage-status').value = item.status; $('triage-priority').value = item.priority; $('triage-notes').value = item.notes;
  $('observations').replaceChildren(); $('audit-history').replaceChildren();
  item.observations.forEach(obs => {
    const entry = el('div', undefined, 'run');
    entry.append(el('strong',obs.source), el('p',`${obs.sightings} ${obs.sightings === 1 ? 'sighting' : 'sightings'} · Last seen ${obs.last_seen}`), el('small',obs.source_url || 'Manual metadata import'), el('p', `Provider first observed: ${obs.source_observed_at || 'Not supplied'}`));
    $('observations').append(entry);
  });
  if (!item.observations.length) $('observations').append(el('p','Legacy record: no observation history collected yet.'));
  item.history.forEach(event => {
    const before = JSON.parse(event.before_json), after = JSON.parse(event.after_json);
    const entry = el('div', undefined, 'run');
    entry.append(el('strong',`${before.status} → ${after.status} · ${after.priority} priority`),el('p',event.created_at),el('p',after.notes || 'No notes', 'audit-note'));
    $('audit-history').append(entry);
  });
  if (!item.history.length) $('audit-history').append(el('p','No assessments yet. Save your first review to begin the history.'));
}
$('triage-form').onsubmit = async event => {
  event.preventDefault(); const claim = activeClaim, request = detailSequence;
  $('save-triage').disabled = true; $('detail-message').textContent = 'Saving…';
  try {
    const response = await fetch('/api/investigation', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:claim, version:activeVersion, status:$('triage-status').value, priority:$('triage-priority').value, notes:$('triage-notes').value})});
    const item = await response.json();
    if (!response.ok) throw new Error(item.error || 'Unable to save assessment');
    if (request !== detailSequence) return;
    renderInvestigation(item); $('detail-message').textContent = 'Assessment saved. Review status does not confirm an incident.';
    await load();
  } catch (error) { if (request === detailSequence) $('detail-message').textContent = error.message; }
  finally { if (request === detailSequence) $('save-triage').disabled = false; }
};
async function watch(term, action) {
  try { const response = await fetch('/api/watchlist',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({term,action})}); if (!response.ok) throw new Error('Could not update watchlist'); $('term').value = ''; await load(); }
  catch (error) { $('error').hidden = false; $('error').textContent = error.message; }
}
$('watch-form').onsubmit = event => { event.preventDefault(); watch($('term').value.trim(),'add'); };
$('close-detail').onclick = () => $('detail').close();
$('detail').addEventListener('close', () => { detailSequence++; activeClaim = null; });
$('prev').onclick = () => { page--; renderTable(); }; $('next').onclick = () => { page++; renderTable(); };
['mode','days','actor','status'].forEach(id => $(id).onchange = () => { if (id === 'mode') $('actor').value = ''; page = 0; load(); });
let timer; $('search').oninput = () => { clearTimeout(timer); timer = setTimeout(() => {page = 0; load();},250); };
if (new URLSearchParams(window.location.search).get('mode') === 'live') $('mode').value = 'live';
$('refresh').onclick = load; load(); setInterval(load,60000);
