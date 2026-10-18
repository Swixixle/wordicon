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
  const subjectKey = subject => {
    if (!subject) return null;
    if (subject.trace_id) return JSON.stringify([subject.trace_id, subject.thread_index == null ? null : subject.thread_index]);
    // the Deflate door: a deposition item keeps the same lost-Start recovery
    // (one pending request key per subject) as a thread does
    if (subject.deposition_id) {
      const identity = ['dep', subject.deposition_id, subject.item_ref || ''];
      if (subject.source_operation_id) identity.push(subject.source_operation_id);
      return JSON.stringify(identity);
    }
    return null;
  };
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
                         startUncertain:!!pending.startUncertain, question:((pending.prepared.disclosure || {}).exploration || {}).question || '',
                         continueEvidence:((((pending.prepared.disclosure || {}).exploration || {}).research_goal || {}).kind === 'continue_evidence')});
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
    // a deposition root's starting lines come from custody, not recall — the
    // standing line must say which law applies, never the wrong one
    const quote = rootOf(context).deposition_id
      ? 'The starting item is an imported deposition: its transcript lines are quoted from the package in custody, signature-verified against the pinned key — origin and integrity, never truth, and never a public-source verification.'
      : (thread.quote_status === 'paraphrase' ? 'The starting words are a paraphrase, not an exact quotation.' : 'The starting thread comes from model recall; its quotation has not been verified against an admitted passage.');
    const verdict = thread.review_verdict;
    return `<div style="border-left:2px solid var(--mode-source);padding-left:12px;margin:12px 0">
      ${message(disclosure || 'Model reading and source leads. No source admission or interpretive support ruling; checks shown here concern wording in retrieved text only.')}
      ${message(quote)}
      ${verdict ? message('“' + verdict + '” was the review of the original analogy. It is not a verdict on this person or work, and does not prevent exploring it.') : ''}
    </div>`;
  }

  const safeSourceUrl = raw => {
    try { const url = new URL(raw); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
    catch (_) { return null; }
  };
  const countKnown = value => Number.isInteger(value) && value >= 0;
  function sourceLeads(citations) {
    const seen = new Set();
    return (Array.isArray(citations) ? citations : []).map(c => {
      const raw = typeof c === 'string' ? c : c && c.url;
      const url = raw && safeSourceUrl(raw);
      if (!url || seen.has(url)) return null;
      seen.add(url);
      return {url, title:c.title || new URL(url).hostname};
    }).filter(Boolean);
  }

  function sourceLinks(citations, hasRetrievedText) {
    const links = sourceLeads(citations).map(c => `<li><a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer" style="color:var(--mode-source);overflow-wrap:anywhere">${esc(c.title)}</a></li>`);
    return links.length
      ? `<details style="margin:12px 0"><summary style="cursor:pointer">Source leads returned by provider · ${links.length}</summary>${message('Provider citations are leads to inspect; they do not certify each claim or the starting quotation.')}<ul>${links.join('')}</ul></details>`
      : message(hasRetrievedText ? 'No provider citation leads were returned. Retrieved source text is recorded separately below.' : 'No web citations returned. Provider citations do not establish a source check.');
  }

  function acquisitionHtml(result) {
    const records = Array.isArray(result.acquisition_records) && result.acquisition_records.length
      ? result.acquisition_records : result.acquisition_usage ? [result.acquisition_usage] : [];
    const known = records.filter(record => record && countKnown(record.web_search_requests));
    const unknown = records.length - known.length;
    const total = known.reduce((sum, record) => sum + record.web_search_requests, 0);
    const allowanceKnown = records.length > 0 && records.every(record => record && countKnown(record.max_uses_requested));
    const allowance = allowanceKnown ? records.reduce((sum, record) => sum + record.max_uses_requested, 0) : null;
    const countText = known.length
      ? 'Provider reports ' + (unknown ? 'at least ' : '') + total + ' search' + (total === 1 ? '' : 'es') + (unknown ? '; count unknown for ' + unknown + ' acquisition(s)' : '')
      : 'Provider search count not recorded';
    const line = countText + (allowanceKnown ? ' · ' + allowance + ' allowed across recorded acquisitions' : '') + ' · ' + sourceLeads(result.citations).length + ' distinct source leads attached';
    const rows = records.map((record, index) => {
      const outcomes = Array.isArray(record && record.search_result_outcomes) ? record.search_result_outcomes : [];
      const uses = Array.isArray(record && record.search_tool_uses) ? record.search_tool_uses : null;
      const details = outcomes.map(outcome => {
        const labels = {results_returned:'Results returned', empty_results:'No search results returned', error:'Search error', unrecognized:'Unrecognized search result shape'};
        let text = labels[outcome.outcome] || 'Unrecognized search result outcome';
        if (outcome.outcome === 'results_returned' && countKnown(outcome.result_count)) text += ' · ' + outcome.result_count + ' result(s)';
        if (outcome.error_code) text += ' · error code: ' + outcome.error_code;
        if (outcome.tool_use_id) text += ' · attempt: ' + outcome.tool_use_id;
        return `<li style="overflow-wrap:anywhere">${esc(text)}</li>`;
      });
      return `<li>Acquisition ${index + 1}${uses ? ' · ' + uses.length + ' identified search tool attempt(s)' : ''}${details.length ? '<ul>' + details.join('') + '</ul>' : message(record && record.search_outcomes_recorded ? 'No search result blocks were recorded in this response.' : 'Per-search outcomes were not recorded for this acquisition.')}</li>`;
    });
    return `<div class="deeper-acquisition" style="margin:12px 0">${message((result.is_fixture ? 'MOCK FIXTURE · ' : '') + line)}${rows.length ? `<details><summary style="cursor:pointer">Search acquisition record</summary>${message('These are provider-reported counts and returned block outcomes. They do not establish that the model read a page or that a quotation is accurate. Identified tool attempts can exceed allowed searches; they are not a billable-search count.')}<ul>${rows.join('')}</ul></details>` : ''}</div>`;
  }

  function researchPlanHtml(plan) {
    if (!plan || typeof plan !== 'object') return '';
    const limits = plan.limits || plan;
    const items = [[limits.max_search_rounds, 'search rounds'], [limits.max_source_reads, 'direct source reads'], [limits.max_model_calls, 'model calls']]
      .filter(([value]) => countKnown(value)).map(([value, label]) => value + ' ' + label);
    if (plan.version >= 6) {
      const contextLimit = countKnown(limits.max_grounding_chars)
        ? message('The answer can receive up to ' + limits.max_grounding_chars.toLocaleString('en-US') + ' characters of source passages, with their saved locations.') : '';
      return `<div class="deeper-research-plan">${message('One Start lets the tool follow further leads and examine several passages from a saved work within the approved allowance.')}
        <details><summary style="cursor:pointer">Research allowance and cost</summary>
          ${message('Evidence checking: ' + (items.length ? 'up to ' + items.join(', ') + '.' : 'within the frozen research limits.'))}
          ${contextLimit}
          ${message('Each discovery request allows one provider search; the final model request writes the answer from the collected passages. Saved passages can be inspected without another download or another press of Continue checking.')}
          ${message('Readable pages are tried before catalog hints, and some reads are reserved for later searches. Earlier passage locations are remembered so new reading can advance through the work. Matching words does not establish that an answer is supported.')}
          ${message('Search and model token charges may apply; actual cost is unknown until reported. This allowance is not a dollar cap or a completion-time guarantee. If the allowance runs out, the record keeps the evidence and remaining question for a separately reviewed continuation.')}
        </details></div>`;
    }
    return `<div class="deeper-research-plan">${message('Evidence checking: ' + (items.length ? 'up to ' + items.join(', ') + '.' : 'within the frozen research limits.'))}${plan.version >= 2 ? message('For a question without exact quoted wording, checking continues through the available source-read or search allowance. Finding readable text or matching topic terms does not establish that the answer is supported.') : ''}${plan.version >= 3 ? message('Links that look like readable pages are tried first. Some reads are kept for later search approaches, so the first set of links cannot use the whole allowance.') : ''}${plan.version >= 4 ? message('If none of the carried-over links matches the question\'s own terms, the first reads wait for fresh search results instead — the carried links stay saved and can still be read later.') : ''}${plan.version >= 5 ? message('When a saved text comes back in a later pass, the next excerpt is taken from parts not yet shown to the model; if only an already-shown part matches, the record says it was reused.') : ''}${message('If an attempt fails, checking can continue through other source leads and targeted follow-up searches within those limits. Search and model token charges may apply; actual cost is unknown until reported. Reaching a limit preserves the evidence and remaining question for a separately reviewed continuation.')}</div>`;
  }

  function evidenceNoticeHtml(result) {
    const research = result.evidence_research;
    if (result.is_fixture || !research || typeof research !== 'object' || !countKnown(research.source_count)) return '';
    const hasExplanation = typeof result.explanation === 'string' && result.explanation.trim().length > 0;
    let notice = '';
    if (research.source_count === 0) {
      notice = research.final_answer_status === 'unavailable'
        ? 'No source text retrieved — no model explanation available.'
        : hasExplanation ? 'No source text retrieved — model explanation, unverified.' : 'No source text retrieved.';
    } else if (research.usable_source_count === 0) {
      notice = research.final_answer_status === 'unavailable'
        ? 'No retrieved text retained for grounding — no model explanation available.'
        : hasExplanation ? 'No retrieved text retained for grounding — explanation remains unverified.' : 'No retrieved text retained for grounding.';
    }
    return notice ? `<div class="deeper-evidence-notice" role="note"><p class="body" style="font-size:13px"><strong>${esc(notice)}</strong></p></div>` : '';
  }

  function sourceScreeningHtml(sources) {
    const rows = (Array.isArray(sources) ? sources : []).filter(source => source && typeof source === 'object' && source.assessment && typeof source.assessment === 'object').map(source => {
      const assessment = source.assessment;
      const url = safeSourceUrl(source.final_url || source.url);
      const kinds = {catalog_like:'Catalog or landing page', text_indicated:'Possible text page', unknown:'Page type not established'};
      const questionTerms = Array.isArray(assessment.matched_question_terms) ? assessment.matched_question_terms.filter(term => typeof term === 'string') : [];
      const workTerms = Array.isArray(assessment.matched_work_terms) ? assessment.matched_work_terms.filter(term => typeof term === 'string') : [];
      const reasons = Array.isArray(assessment.reason) ? assessment.reason.filter(reason => typeof reason === 'string') : [];
      return `<li style="margin:10px 0;overflow-wrap:anywhere">
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" style="color:var(--mode-source)">${esc(url)}</a>` : 'Source URL omitted'}
        ${message((assessment.weak === true ? 'Weak candidate' : assessment.weak === false ? 'Candidate retained for inspection' : 'Screening strength not recorded') + ' · ' + (kinds[assessment.candidate_kind] || kinds.unknown))}
        ${message((assessment.question_basis === 'frozen_focus_fallback' ? 'Frozen subject terms found: ' : 'Question terms found: ') + (questionTerms.length ? questionTerms.join(', ') : 'none recorded'))}
        ${message('Work terms found: ' + (workTerms.length ? workTerms.join(', ') : 'none recorded'))}
        ${reasons.length ? message('Screening reasons: ' + reasons.join('; ')) : ''}
      </li>`;
    });
    return rows.length ? `<details class="deeper-source-screening"><summary style="cursor:pointer">Source screening · ${rows.length}</summary>${message('These are automatic clues for choosing passages to inspect, not verification. Word overlap and page type do not establish authorship, relevance, or support for the answer.')}<ul>${rows.join('')}</ul></details>` : '';
  }

  function researchStopHtml(research) {
    const reasons = {
      quotation_located:'Checking stopped after locating the requested wording. Broader answer support remains unverified.',
      source_read_budget_reached:'This pass reached its source-read allowance. The research question remains open.',
      search_budget_reached:'This pass reached its search allowance. The research question remains open.',
      reused_complete_pass_for_answer_retry:'Saved source screening was reused for another answer attempt. The research question remains open.'
    };
    if (reasons[research.stop_reason]) return message(reasons[research.stop_reason]);
    return research.retrieval_pass_complete === true ? message('This bounded retrieval pass has ended; that does not establish that the research question is answered.') : '';
  }

  function evidenceHtml(result, entry) {
    const research = result.evidence_research;
    if (!research || typeof research !== 'object') return '';
    const fixture = !!result.is_fixture;
    const labels = {quote_located:'Quotation wording located in retrieved text', candidate_passages_found:'Candidate passages collected; answer support remains unverified', source_text_obtained:'Legacy record: source text obtained; relevance and answer support were not established', needs_more_evidence:'More evidence needed'};
    const proofs = Array.isArray(research.proofs) ? research.proofs : [];
    const steps = Array.isArray(research.steps) ? research.steps : [];
    const proofHtml = proofs.map(proof => {
      const match = proof.match || {};
      const url = safeSourceUrl(proof.final_url || proof.url);
      const location = Array.isArray(match.section_path) ? match.section_path.join(' → ') : match.section_path;
      return `<article style="border-left:2px solid var(--mode-source);padding-left:12px;margin:12px 0;overflow-wrap:anywhere">
        ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" style="color:var(--mode-source)">${esc(url)}</a>` : message('No valid source URL recorded.')}
        ${match.excerpt || match.exact_text ? `<blockquote class="body" style="white-space:pre-wrap;margin:10px 0">${esc(match.excerpt || match.exact_text)}</blockquote>` : ''}
        <details><summary style="cursor:pointer">Passage record</summary>
          ${location ? message('Section: ' + location) : ''}
          ${countKnown(match.start) && countKnown(match.end) ? message('Saved text offsets: ' + match.start + '–' + match.end) : ''}
          ${match.match_type ? message('Match method: ' + match.match_type) : ''}
          ${proof.body_sha256 ? message('Retrieved body SHA-256: ' + proof.body_sha256) : ''}
        </details>
      </article>`;
    }).join('');
    const readableCounts = countKnown(research.fresh_source_count) && countKnown(research.reused_source_count)
      ? [[research.fresh_source_count, 'new readable source reads'], [research.reused_source_count, 'saved source reads reused']]
      : [[research.source_count, 'readable source texts obtained (new/reused split not recorded)']];
    const progress = [[research.rounds_used, 'search rounds used'], [research.sources_tried, 'new source reads attempted'], ...readableCounts, [research.usable_source_count, 'source texts retained as candidates']]
      .filter(([value]) => countKnown(value)).map(([value, label]) => value + ' ' + label).join(' · ');
    const answerInput = [[research.grounding_passage_count, 'passages'], [research.unique_source_count, 'distinct saved texts'], [research.grounding_chars, 'source characters']]
      .filter(([value]) => countKnown(value)).map(([value, label]) => value.toLocaleString('en-US') + ' ' + label).join(' · ');
    return `<section class="deeper-evidence" aria-label="Recorded source evidence" style="margin:16px 0">
      <div class="section-label">${fixture ? 'MOCK FIXTURE · Evidence demonstration' : 'Recorded source evidence'}</div>
      ${paragraph(fixture ? 'Simulated evidence only — no live source check was performed.' : labels[research.status] || 'Evidence status not recognized')}
      ${research.target_quote ? message('Wording sought: “' + research.target_quote + '”') : ''}
      ${!fixture && research.status === 'quote_located' ? message('This locates wording in the retrieved text. It does not by itself establish authorship, the edition’s authority, or every claim in the explanation.') : ''}
      ${fixture ? '' : researchStopHtml(research)}
      ${research.screening_basis === 'frozen_focus_fallback' ? message('Source screening used the saved subject and work because the question supplied no specific topic terms. Your research question is unchanged.') : ''}
      ${research.remaining_requirement ? message(research.remaining_requirement) : ''}
      ${research.final_answer_status === 'unavailable' ? message('A grounded answer is not yet available. Continue checking can prepare another answer using the saved evidence.') : ''}
      ${progress ? message(progress) : ''}
      ${answerInput ? message('Included in the answer request: ' + answerInput + '. These counts describe supplied text, not verified understanding.') : ''}
      ${proofHtml}
      ${sourceScreeningHtml(research.sources)}
      ${steps.length ? `<details><summary style="cursor:pointer">Checking attempts · ${steps.length}</summary><ol>${steps.map(step => `<li style="overflow-wrap:anywhere">${esc([step.kind, step.status, step.url ? safeSourceUrl(step.url) || 'Source URL omitted' : '', step.reason].filter(Boolean).join(' · '))}</li>`).join('')}</ol></details>` : ''}
      ${research.checkpoint_id ? `<details><summary style="cursor:pointer">Saved checkpoint</summary>${message(research.checkpoint_id)}</details>` : ''}
      ${['needs_more_evidence', 'source_text_obtained', 'candidate_passages_found'].includes(research.status) || research.final_answer_status === 'unavailable' ? button(entry, 'continue-evidence', 'Continue checking', 'style="margin-top:10px"') + message('Review a continuation proposal using this saved result. Nothing runs until you press Start.') : ''}
    </section>`;
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

  window.deeperDepositionControl = (depositionId, itemRef, title, sourceOperationId) => {
    // the Deflate door (2026-10-17): an imported, verified reading or claim
    // opens the same proposal machinery a saved thread does — the subject is
    // resolved server-side from custody; this control carries only its ids
    if (!depositionId || !itemRef) return '';
    const entry = makeEntry({subject: {kind:'deposition', deposition_id:depositionId, item_ref:itemRef,
      ...(sourceOperationId ? {source_operation_id:sourceOperationId} : {})}, title:title || 'this imported reading'});
    return `${button(entry, 'open', '↓ Go deeper', 'style="margin-top:6px;font-size:12px" title="Explore this imported reading or claim; review the proposal before anything runs"')}<div id="${entry.mountId}" aria-live="polite"></div>`;
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
      ${evidenceNoticeHtml(result)}
      ${result.explanation ? paragraph(result.explanation) : message('This result has no explanation recorded.')}
      ${result.context_notes ? `<div class="section-label">In context</div>${paragraph(result.context_notes)}` : ''}
      ${result.source_guidance ? `<div class="section-label">Into the work itself</div>${paragraph(result.source_guidance)}` : ''}
      ${acquisitionHtml(result)}
      ${sourceLinks(result.citations, !!(result.evidence_research && result.evidence_research.source_count))}
      ${evidenceHtml(result, entry)}
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
      ${context.research_goal && context.research_goal.kind === 'continue_evidence' && context.research_goal.question && context.research_goal.question !== context.question ? `<p class="body" style="white-space:pre-wrap"><strong>Evidence question</strong> · ${esc(context.research_goal.question)}</p>` : ''}
      ${message('Scope: ' + (rootOf(context).deposition_id ? 'the exact imported deposition item, re-verified against the pinned key at preparation (custody, never truth)' : 'the exact saved thread') + (prior ? ' and ' + prior + ' prior exploration step(s)' : '') + ', with this question. ' + (scope.words == null ? '' : scope.words + ' words in the frozen context.'))}
      ${message(laneLine)}
      ${message('Leaves this machine: ' + (lane.external ? fields + ' → ' + (outbound.recipient || 'model') + ' (' + (lane.model || lane.lane || 'configured provider') + ')' : 'nothing in the mock lane.'))}
      ${lane.external && (context.research_plan || d.research_plan) ? message('Public source hosts receive bounded unauthenticated GETs; retrieved excerpts and failure summaries go to the configured model.') : ''}
      ${message('Calls: ' + (d.calls == null ? 'as disclosed by the server' : d.calls) + ' · Cost: ' + (d.cost || 'not disclosed'))}
      ${researchPlanHtml(context.research_plan || d.research_plan)}
      ${sourceStanding(context, d.source_standing)}
      ${contextNote(context)}
      <details style="margin:10px 0"><summary style="cursor:pointer">Inspect frozen context</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:300px;overflow:auto">${esc(JSON.stringify(context, null, 2))}</pre></details>
      ${notice ? error(notice) : ''}
      ${d.available ? '' : error(d.reason || 'This model lane is not available.')}
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">${button(entry, 'start', entry.startUncertain ? 'Check Start again' : 'Start', d.available ? '' : 'disabled')}${button(entry, 'cancel', entry.startUncertain ? 'Close' : 'Cancel')}<span class="muted" style="font-size:12px">${entry.startUncertain ? 'The same request key is reused; this does not create another attempt.' : 'Nothing has started.'}</span></div>
    </section>`;
  }

  async function prepare(entry, question = '', continueEvidence = false) {
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
    entry.continueEvidence = continueEvidence;
    entry.operationId = null;
    entry.completed = false;
    entry.terminalStatus = null;
    entry.prepared = null;
    entry.preparing = true;
    activeProposal = entry;
    const generation = ++entry.generation;
    area.innerHTML = `<div class="card">${message('Preparing a local proposal for ' + entry.title + '… No model call has started.')}${button(entry, 'cancel', 'Cancel')}</div>`;
    try {
      const inputs = {question};
      if (entry.continueEvidence) inputs.continue_evidence = true;
      const response = await fetch('/api/actions/prepare', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action_id:'explore.deepen', subject:entry.subject, inputs})});
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
      prepare(entry, entry.question || '', !!entry.continueEvidence);
    }
    else if (action === 'reopen' && typeof window.loadPastResult === 'function') window.loadPastResult(entry.reopenTrace);
    else if (action === 'cancel') closeProposal(entry);
    else if (action === 'continue-evidence') prepare(entry, 'Continue checking the quotation against source texts using the saved evidence.', true);
    else if (action === 'question') {
      const question = entry.questions[Number(target.dataset.deeperQuestion)];
      // W2: the Ledger notes that a question was followed and which run it
      // left from — never the question's words. A suggested question taken
      // and his own asked are the same act with a different kind. Guarded:
      // this file also loads where no reporter exists.
      if (typeof question === 'string') {
        if (window.__nikLedger) window.__nikLedger.note('question_followed', {id: (entry.subject && entry.subject.trace_id) || '', kind: 'suggested'});
        prepare(entry, question);
      }
    } else if (action === 'follow') {
      const input = document.getElementById(entry.key + '-question');
      if (input && input.value.trim()) {
        if (window.__nikLedger) window.__nikLedger.note('question_followed', {id: (entry.subject && entry.subject.trace_id) || '', kind: 'own'});
        prepare(entry, input.value);
      }
      else if (input) { input.focus(); input.setCustomValidity('Write the question you would like to follow.'); input.reportValidity(); input.addEventListener('input', () => input.setCustomValidity(''), {once:true}); }
    }
  });
})();
