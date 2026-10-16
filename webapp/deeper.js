/* Go deeper: a saved source thread stays the subject of each next question.
 * Preparing writes a local frozen proposal; reopening reads saved results.
 * Neither calls a model. One proposal keeps one dispatch request key. */
(() => {
  'use strict';
  const entries = new Map();
  const pendingStorageKey = 'nikodemus.deeper.pending.v1';
  let pendingStarts = {};
  try { pendingStarts = JSON.parse(sessionStorage.getItem(pendingStorageKey) || '{}'); } catch (_) { /* in-memory recovery still works */ }
  if (!pendingStarts || typeof pendingStarts !== 'object' || Array.isArray(pendingStarts)) pendingStarts = {};
  let serial = 0;
  let activeProposal = null;
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const freshKey = () => window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : 'deeper-' + Date.now() + '-' + Math.random().toString(36).slice(2);
  const subjectKey = subject => subject && subject.trace_id ? JSON.stringify([subject.trace_id, subject.thread_index == null ? null : subject.thread_index]) : null;
  function savePending(entry) {
    const key = subjectKey(entry.subject);
    if (!key || !entry.prepared || !entry.requestKey) return false;
    pendingStarts[key] = {prepared:entry.prepared, requestKey:entry.requestKey, operationId:entry.operationId || null, startUncertain:!!entry.startUncertain};
    try { sessionStorage.setItem(pendingStorageKey, JSON.stringify(pendingStarts)); return true; } catch (_) { return false; }
  }
  function clearPending(entry) {
    const key = subjectKey(entry.subject);
    if (!key || !pendingStarts[key] || pendingStarts[key].requestKey !== entry.requestKey) return;
    delete pendingStarts[key];
    try { sessionStorage.setItem(pendingStorageKey, JSON.stringify(pendingStarts)); } catch (_) { /* nothing else needs to run */ }
  }
  function recoverPending(entry) {
    const pending = pendingStarts[subjectKey(entry.subject)];
    if (!pending || !pending.prepared || typeof pending.prepared.prepared_id !== 'string' || typeof pending.requestKey !== 'string') return false;
    const different = entry.requestKey !== pending.requestKey;
    Object.assign(entry, {prepared:pending.prepared, requestKey:pending.requestKey, operationId:pending.operationId || null, completed:false, terminalStatus:null,
                         startUncertain:!!pending.startUncertain, question:((pending.prepared.disclosure || {}).exploration || {}).question || ''});
    return different;
  }
  const makeEntry = fields => {
    const key = 'deeper-' + (++serial);
    const entry = {key, mountId: key + '-area', generation: 0, ...fields};
    recoverPending(entry);
    entries.set(key, entry);
    return entry;
  };
  const mount = entry => document.getElementById(entry.mountId);
  const button = (entry, action, label, extra = '') => `<button type="button" class="judge-btn" data-deeper-action="${action}" data-deeper-key="${entry.key}" ${extra}>${esc(label)}</button>`;
  const message = text => `<p class="body muted" style="font-size:13px">${esc(text)}</p>`;
  const error = text => `<p class="body error" role="alert">${esc(text)}</p>`;
  const paragraph = text => `<p class="body" style="white-space:pre-wrap">${esc(text)}</p>`;
  const rootOf = context => (context && context.root) || {};
  const selectionOf = context => rootOf(context).selection || {};
  const focusOf = context => (context && context.focus) || {};
  const titleOf = context => focusOf(context).title || selectionOf(context).anchor_name || 'this subject';

  function contextNote(context) {
    const limits = (context && context.context_limits) || {};
    const count = limits.omitted_prior_steps || 0;
    const steps = Array.isArray(context && context.ancestry) ? context.ancestry : [];
    const shortened = steps.filter(step => step.explanation_omitted_chars > 0);
    return message('Context limit: the original thread stays in view; up to ' + (limits.max_prior_steps || 4) + ' previous steps accompany this question.' +
      (count ? ' ' + count + ' older step(s) are omitted from the model request.' : ' No earlier steps have been omitted.') +
      (shortened.length ? ' ' + shortened.length + ' previous explanation(s) were shortened by ' + shortened.reduce((sum, step) => sum + step.explanation_omitted_chars, 0) + ' characters in total.' : '') +
      ' Earlier answers remain in the saved record.');
  }

  function sourceStanding(context, disclosure) {
    const thread = selectionOf(context);
    const quote = thread.quote_status === 'paraphrase' ? 'The starting words are a paraphrase, not an exact quotation.' : 'The starting thread comes from model recall; its quotation has not been verified against an admitted passage.';
    const verdict = thread.review_verdict;
    return `<div style="border-left:2px solid var(--mode-source);padding-left:12px;margin:12px 0">
      ${message(disclosure || 'Model reading and source leads — this action does not admit or verify a passage.')}
      ${message(quote)}
      ${verdict ? message('“' + verdict + '” was the review of the original analogy. It is not a verdict on this person or work, and does not prevent exploring it.') : ''}
    </div>`;
  }

  function sourceLinks(citations) {
    const links = (Array.isArray(citations) ? citations : []).map(c => {
      const raw = typeof c === 'string' ? c : c && c.url;
      if (!raw) return '';
      try {
        const url = new URL(raw);
        if (!['https:', 'http:'].includes(url.protocol)) return '';
        return `<li><a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer" style="color:var(--mode-source)">${esc(c.title || url.hostname)}</a></li>`;
      } catch (_) { return ''; }
    }).filter(Boolean);
    return links.length
      ? `<details style="margin:12px 0"><summary style="cursor:pointer">Source leads returned by provider · ${links.length}</summary>${message('Provider citations are leads to inspect; they do not certify each claim or the starting quotation.')}<ul>${links.join('')}</ul></details>`
      : message('No web citations returned. This answer is a model reading from recall, not a source check.');
  }

  function trailHtml(result) {
    const rows = Array.isArray(result.trail) ? result.trail : [];
    const seen = new Set();
    const links = rows.filter(row => row && row.trace_id && !seen.has(row.trace_id) && seen.add(row.trace_id)).map(row => {
      if (row.trace_id === result.trace_id) return `<strong>${esc(row.title || result.title || 'This step')}</strong>`;
      const entry = makeEntry({reopenTrace: row.trace_id});
      return button(entry, 'reopen', row.title || 'Earlier step');
    });
    const root = rootOf(result.context);
    if (root.trace_id && !seen.has(root.trace_id)) {
      const entry = makeEntry({reopenTrace: root.trace_id});
      links.unshift(button(entry, 'reopen', 'Original thread'));
    }
    return links.length ? `<nav aria-label="Exploration trail" style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:12px"><span class="muted" style="font-size:12px">Your trail</span>${links.join('<span class="muted" aria-hidden="true">›</span>')}</nav>${result.trail_omitted_steps ? message(result.trail_omitted_steps + ' older steps are folded out of this trail. They remain reachable through earlier saved answers.') : ''}` : '';
  }

  window.deeperThreadControl = (result, threadIndex) => {
    if (!result.trace_id) return '';
    const thread = (result.threads || [])[threadIndex] || {};
    const entry = makeEntry({subject: {kind:'result', trace_id:result.trace_id, thread_index:threadIndex}, title:thread.anchor_name || 'this thread'});
    return `${button(entry, 'open', '↓ Go deeper', 'style="margin-top:6px;font-size:12px" title="Stay with this person, work or idea; review the proposal before anything runs"')}<div id="${entry.mountId}" aria-live="polite"></div>`;
  };

  window.buildDeeperHtml = result => {
    const context = result.context || {};
    const entry = makeEntry({subject: {kind:'result', trace_id:result.trace_id}, title:titleOf(context), questions:Array.isArray(result.next_questions) ? result.next_questions : []});
    const work = focusOf(context).work || selectionOf(context).culture_or_work;
    return `<section class="card deeper-result" style="border-left:3px solid var(--mode-source)">
      <div class="section-label" style="margin-top:0">Go deeper${result.is_fixture ? ' · MOCK FIXTURE — no live model call' : ''}</div>
      ${trailHtml(result)}
      <div class="result-title">${esc(result.title || titleOf(context))}</div>
      ${work ? message(work) : ''}
      ${result.question || context.question ? `<p class="body" style="font-size:13px"><strong>Your question</strong> · ${esc(result.question || context.question)}</p>` : ''}
      ${result.explanation ? paragraph(result.explanation) : message('This result has no explanation recorded.')}
      ${result.context_notes ? `<div class="section-label">In context</div>${paragraph(result.context_notes)}` : ''}
      ${result.source_guidance ? `<div class="section-label">Into the work itself</div>${paragraph(result.source_guidance)}` : ''}
      ${sourceLinks(result.citations)}
      <details style="margin:12px 0"><summary style="cursor:pointer">What this reading rests on</summary>${sourceStanding(context)}${contextNote(context)}</details>
      <div class="section-label">Stay with this subject</div>
      <div style="display:flex;gap:7px;flex-wrap:wrap">${entry.questions.map((q, i) => button(entry, 'question', q, `data-deeper-question="${i}" style="text-align:left;white-space:normal"`)).join('')}</div>
      <label for="${entry.key}-question" class="body muted" style="display:block;font-size:13px;margin-top:12px">Or ask your own next question</label>
      <textarea id="${entry.key}-question" rows="2" placeholder="What about this person, work or idea would you like to understand?" style="box-sizing:border-box;width:100%;margin:6px 0;resize:vertical"></textarea>
      ${button(entry, 'follow', 'Review next step')}
      ${message('Each next step has its own proposal. Your draft stays as you wrote it.')}
      <div id="${entry.mountId}" aria-live="polite"></div>
    </section>`;
  };

  function renderProposal(entry, notice) {
    const area = mount(entry);
    if (!area) return;
    activeProposal = entry;
    const p = entry.prepared, d = p.disclosure || {}, context = d.exploration || {}, lane = d.lane || {}, scope = d.scope || {};
    const outbound = d.leaves_this_machine || {};
    const fields = Array.isArray(outbound.fields) ? outbound.fields.join(', ') : String(outbound.fields || '');
    const laneLine = lane.external ? 'Live model · ' + (lane.model || lane.lane || 'configured provider') : 'MOCK — no live model calls';
    const prior = Array.isArray(context.ancestry) ? context.ancestry.length : 0;
    area.innerHTML = `<section class="card deeper-proposal" style="border:1px solid var(--mode-source);margin-top:14px" aria-label="Go deeper proposal">
      <div class="section-label" style="margin-top:0">Go deeper · proposal</div>
      <div class="result-title">${esc(titleOf(context))}</div>
      ${focusOf(context).work ? message(focusOf(context).work) : ''}
      ${paragraph(context.question || entry.question || 'Understand this subject on its own terms and find a useful way into the work.')}
      ${message('Scope: the exact saved thread' + (prior ? ' and ' + prior + ' prior exploration step(s)' : '') + ', with this question. ' + (scope.words == null ? '' : scope.words + ' words in the frozen context.'))}
      ${message(laneLine)}
      ${message('Leaves this machine: ' + (lane.external ? fields + ' → ' + (outbound.recipient || 'model') + ' (' + (lane.model || lane.lane || 'configured provider') + ')' : 'nothing in the mock lane.'))}
      ${message('Calls: ' + (d.calls == null ? 'as disclosed by the server' : d.calls) + ' · Cost: ' + (d.cost || 'not disclosed'))}
      ${sourceStanding(context, d.source_standing)}
      ${contextNote(context)}
      <details style="margin:10px 0"><summary style="cursor:pointer">Inspect frozen context</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:300px;overflow:auto">${esc(JSON.stringify(context, null, 2))}</pre></details>
      ${notice ? error(notice) : ''}
      ${d.available ? '' : error(d.reason || 'This model lane is not available.')}
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">${button(entry, 'start', entry.startUncertain ? 'Check Start again' : 'Start', d.available ? '' : 'disabled')}${button(entry, 'cancel', entry.startUncertain ? 'Close' : 'Cancel')}<span class="muted" style="font-size:12px">${entry.startUncertain ? 'The same request key is reused; this does not create another attempt.' : 'Nothing has started.'}</span></div>
    </section>`;
  }

  async function prepare(entry, question = '') {
    if (entry.preparing || entry.starting) return;
    recoverPending(entry);
    // A lost Start response is not permission to mint another request. The
    // original thread button and every follow-up control recover this same
    // frozen proposal, including after Close and a tab reload.
    if (entry.startUncertain && entry.prepared && entry.requestKey) {
      renderProposal(entry, 'An earlier Start has not been confirmed. Check that same request before opening another step here.');
      return;
    }
    if (entry.operationId && !entry.completed) { poll(entry); return; }
    const area = mount(entry);
    if (!area) return;
    entry.question = question;
    entry.operationId = null;
    entry.completed = false;
    entry.terminalStatus = null;
    entry.prepared = null;
    entry.preparing = true;
    activeProposal = entry;
    const generation = ++entry.generation;
    area.innerHTML = `<div class="card">${message('Preparing a local proposal for ' + entry.title + '… No model call has started.')}${button(entry, 'cancel', 'Cancel')}</div>`;
    try {
      const response = await fetch('/api/actions/prepare', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action_id:'explore.deepen', subject:entry.subject, inputs:{question}})});
      const data = await response.json();
      if (entry.generation !== generation) return;
      if (!response.ok) { area.innerHTML = error(data.error || 'Could not prepare this exploration.'); return; }
      entry.prepared = data;
      entry.requestKey = freshKey();
      entry.startUncertain = false;
      renderProposal(entry);
    } catch (_) {
      if (entry.generation === generation) area.innerHTML = error('Could not reach the server. No Start request was sent.');
    } finally {
      if (entry.generation === generation) entry.preparing = false;
    }
  }

  async function start(entry) {
    if (!entry.prepared || entry.starting || entry.operationId) return;
    if (recoverPending(entry)) {
      if (entry.operationId) poll(entry);
      else renderProposal(entry, 'This subject already has an unconfirmed Start. Check its saved request before starting another step.');
      return;
    }
    const area = mount(entry);
    if (!area) return;
    entry.starting = true;
    if (activeProposal === entry) activeProposal = null;
    // Record before the POST: leaving the page while the response is in
    // flight must recover the same request, not silently start another.
    entry.startUncertain = true;
    if (!savePending(entry)) {
      entry.starting = false;
      entry.startUncertain = false;
      clearPending(entry);
      renderProposal(entry, 'This browser could not save the request recovery key. Nothing was sent. Allow session storage or free browser storage, then try Start again.');
      return;
    }
    area.innerHTML = `<div class="card">${message('Starting the exploration…')}</div>`;
    try {
      const response = await fetch('/api/operations', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prepared_id:entry.prepared.prepared_id, request_key:entry.requestKey})});
      const data = await response.json();
      if (!response.ok) {
        entry.startUncertain = !data.nothing_was_sent;
        if (entry.startUncertain) savePending(entry); else clearPending(entry);
        renderProposal(entry, (data.error || 'The operation did not return a start confirmation.') + (data.nothing_was_sent ? ' Nothing was sent.' : ' Its outcome may need checking.'));
        return;
      }
      if (!data.operation_id) throw new Error('missing operation');
      entry.operationId = data.operation_id;
      entry.startUncertain = false;
      savePending(entry);
      poll(entry);
    } catch (_) {
      entry.startUncertain = true;
      savePending(entry);
      renderProposal(entry, 'The Start response did not arrive. It may already be running. Check again with the same request key.');
    } finally { entry.starting = false; }
  }

  async function poll(entry) {
    const area = mount(entry);
    if (!area || !entry.operationId || entry.polling) return;
    entry.polling = true;
    try {
      const response = await fetch('/api/operations/' + encodeURIComponent(entry.operationId));
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not read the operation.');
      if (['complete', 'done'].includes(data.status)) {
        let result = data.result;
        if (!result && data.trace_id) {
          const saved = await fetch('/api/result/' + encodeURIComponent(data.trace_id));
          if (!saved.ok) throw new Error('The operation finished, but its saved result could not be read.');
          result = await saved.json();
        }
        if (!result) throw new Error('The operation finished without a readable result.');
        entry.completed = true;
        clearPending(entry);
        area.innerHTML = window.buildDeeperHtml(result);
        if (typeof window.loadHistory === 'function') window.loadHistory();
        return;
      }
      if (['failed', 'unknown'].includes(data.status)) {
        entry.terminalStatus = data.status;
        entry.completed = data.status === 'failed';
        if (entry.completed) clearPending(entry);
        area.innerHTML = `<div class="card">${error((data.status === 'unknown' ? 'Outcome unknown: ' : 'Exploration failed: ') + (data.error || data.progress || 'No completed result was returned.'))}${message('The operation remains in the record. Nothing will be started again automatically.')}${button(entry, 'poll', 'Check saved status')}${data.status === 'failed' ? button(entry, 'retry', 'Review another attempt') : ''}</div>`;
        return;
      }
      area.innerHTML = `<div class="card"><div class="section-label">Going deeper · ${esc(entry.title)}</div><p class="body muted"><span class="spinner"></span>${esc(data.progress || data.status || 'Working…')}</p>${message('You can continue writing. The result will be saved when it finishes.')}</div>`;
      setTimeout(() => poll(entry), 1500);
    } catch (e) {
      area.innerHTML = `<div class="card">${error(e.message || 'Could not read the operation.')} ${message('Checking its saved status makes no model call.')}${button(entry, 'poll', 'Check saved status')}</div>`;
    } finally { entry.polling = false; }
  }

  function closeProposal(entry) {
    if (entry.starting || entry.operationId) return;
    entry.generation++;
    entry.preparing = false;
    // Closing an uncertain start hides its card only. Keep both proposal
    // and key so reopening can ask about exactly the same operation.
    if (!entry.startUncertain) entry.prepared = null;
    if (activeProposal === entry) activeProposal = null;
    if (mount(entry)) mount(entry).innerHTML = entry.startUncertain ? message('Closed. Reopen Go deeper to check the same Start request. Its proposal and request key are preserved.') : '';
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && activeProposal && mount(activeProposal)) {
      closeProposal(activeProposal);
      event.stopPropagation();
    }
  }, true);

  document.addEventListener('click', event => {
    const target = event.target.closest('[data-deeper-action]');
    if (!target || target.disabled) return;
    const entry = entries.get(target.dataset.deeperKey);
    if (!entry) return;
    const action = target.dataset.deeperAction;
    if (action === 'open') prepare(entry);
    else if (action === 'start') start(entry);
    else if (action === 'poll') poll(entry);
    else if (action === 'retry' && entry.terminalStatus === 'failed') {
      // A known failure may get a separately reviewed new attempt. An
      // unknown outcome keeps its old operation and can only be checked.
      entry.operationId = null;
      prepare(entry, entry.question || '');
    }
    else if (action === 'reopen' && typeof window.loadPastResult === 'function') window.loadPastResult(entry.reopenTrace);
    else if (action === 'cancel') closeProposal(entry);
    else if (action === 'question') {
      const question = entry.questions[Number(target.dataset.deeperQuestion)];
      if (typeof question === 'string') prepare(entry, question);
    } else if (action === 'follow') {
      const input = document.getElementById(entry.key + '-question');
      if (input && input.value.trim()) prepare(entry, input.value);
      else if (input) { input.focus(); input.setCustomValidity('Write the question you would like to follow.'); input.reportValidity(); input.addEventListener('input', () => input.setCustomValidity(''), {once:true}); }
    }
  });
})();
