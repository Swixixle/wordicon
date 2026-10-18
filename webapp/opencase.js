/* Open Case's bounded public-record workflow. Only Start dispatches. Every
 * reopened view reads Nikodemus's durable record, never a producer report. */
import { Ledger } from '/work/ledger.js';
import { costText, cacheReadText } from '/work/cost-display.js';
(() => {
  'use strict';
  const ledger = new Ledger();
  const ACTION = 'investigate.opencase.question';
  const PENDING = 'nikodemus.opencase.pending.v1';
  const $ = id => document.getElementById(id);
  const enc = encodeURIComponent;
  const active = new Set(['queued', 'running', 'dispatching']);
  const profileNames = {federal_judge_district:'Federal district judge',federal_judge_circuit:'Federal appeals judge',federal_judge_scotus:'Supreme Court justice',senator:'U.S. senator'};
  let origin = null, followUp = null, proposal = null, selected = null, timer = null, busy = false;
  const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const button = (label, fn, cls) => { const n = node('button', label, cls); n.type = 'button'; n.addEventListener('click', fn); return n; };
  const row = (...children) => { const n = node('div', null, 'row'); n.append(...children.filter(Boolean)); return n; };
  const detail = (title, value) => { const n = node('details'); n.append(node('summary', title)); const pre = node('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2)); pre.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px'; n.append(pre); return n; };
  const link = (label, href) => { try { const u = new URL(href, location.href); if (!['http:', 'https:'].includes(u.protocol)) return node('span', label); const n = node('a', label); n.href = u.href; n.target = '_blank'; n.rel = 'noopener noreferrer'; return n; } catch (_) { return node('span', label); } };
  async function api(path, body) {
    const r = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (r.status === 401) { location.href = '/pair'; throw new Error('Pair with Nikodemus to continue.'); }
    const d = await r.json();
    if (!r.ok) { const why = d.error || d.detail || `Request failed (${r.status})`; throw new Error(typeof why === 'string' ? why : JSON.stringify(why)); }
    return d;
  }
  const error = e => { $('oc-error').textContent = e ? (e.message || String(e)) : ''; };
  function progressText(value) {
    if (typeof value === 'string') { try { const parsed=JSON.parse(value); return parsed.message || value; } catch (_) { return value; } }
    return value?.message || '';
  }
  function originView() {
    const el = $('oc-origin'); el.replaceChildren();
    if (!origin) { el.append(node('span', 'Origin: this question. The question will be preserved with the investigation.', 'foot')); return; }
    el.append(node('strong', 'From ' + (origin.title || origin.kind || 'a saved source')));
    el.append(node('div', [origin.doc_id, origin.revision != null ? 'revision ' + origin.revision : '', origin.deposition_id, origin.item_ref].filter(Boolean).join(' · '), 'foot'));
    if (origin.text) el.append(detail('Passage carried into the proposal', origin.text));
    el.append(button('Use question alone', () => { origin = null; followUp = null; receiptsContinuation = null; originView(); }, 'quiet'));
    if (followUp) el.append(node('div', 'Follow-up to ' + followUp, 'foot'));
  }
  // These are observed navigation/carry boundaries, not evidence of reading
  // or agreement. The question and source bodies remain in their own records.
  function noteOrigin(value) {
    const id = value?.doc_id || value?.deposition_id;
    if (id) ledger.note('material_carried', {id, revision:value.revision ?? '', kind:'investigation_origin', scope:'open_case'});
  }
  function setOrigin(value) { receiptsContinuation = null; origin = value; noteOrigin(value); proposal = null; $('oc-proposal').replaceChildren(); originView(); $('open-case-card').scrollIntoView({block:'start',behavior:'smooth'}); $('oc-question').focus(); }
  let reuseEvidence = '', receiptsContinuation = null;
  async function prepare(event) {
    event.preventDefault(); if (busy) return; busy = true; error(null); $('oc-prepare').disabled = true;
    try {
      const question = $('oc-question').value.trim();
      const inputs = {question, subject_name:$('oc-subject').value.trim(), subject_type:$('oc-profile').value,
        jurisdiction:$('oc-jurisdiction').value.trim(), connector_id:$('oc-connector').value,
        task_profile:$('oc-task-profile').value, reuse_evidence_from:reuseEvidence, receipts_continuation:receiptsContinuation,
        synthesis:{enabled:$('oc-synthesis').checked,max_requests:1,max_output_tokens:reuseEvidence?8192:4096,max_input_chars:40000},
        allowance:{max_cost_usd:0,paid_models:false}, origin:origin || {kind:'question',text:question}, follow_up_of:followUp};
      proposal = await api('/api/actions/prepare', {action_id:ACTION, subject:{kind:'description',text:question,title:question.slice(0,100)}, inputs});
      if (followUp && !reuseEvidence) ledger.note('question_followed', {id:followUp, kind:'investigation_follow_up', scope:'open_case'});
      drawProposal(proposal);
    } catch (e) { error(e); } finally { busy = false; $('oc-prepare').disabled = false; }
  }
  function drawProposal(p, pending) {
    const box = $('oc-proposal'); box.replaceChildren();
    const plan = p.inputs?.plan || p.disclosure?.investigation_plan || p.plan || {};
    const card = node('div', null, 'item'); card.append(node('h2','Proposed investigation'));
    card.append(node('p', plan.question || $('oc-question').value, 'body'));
    card.append(node('p', [plan.subject_name, profileNames[plan.subject_type] || plan.subject_type, plan.jurisdiction].filter(Boolean).join(' · '), 'foot'));
    const synthesis = plan.synthesis || {};
    card.append(node('p', synthesis.enabled ? '$0 public-record collection + model API usage charges' : '$0 paid-model allowance · paid enrichment disabled', synthesis.enabled?'body':'ok'));
    card.append(node('p', (plan.reuse_evidence_from ? 'Nikodemus reuses the frozen saved evidence and its source labels.' : 'Open Case gathers public records for this official. Findings retain their source labels. The record may be partial.') + (synthesis.enabled ? (synthesis.answer_contract==='checked_excerpts.v1'?' Your configured model selects relevant source passages. Nikodemus checks each quotation against the saved text before displaying it; broader interpretation still requires review.':' Your configured model then writes an answer using the saved evidence, with record citations.') : ' The question is saved as context; no model writes an answer.'), 'body'));
    if (synthesis.enabled) {
      card.append(node('p', `Model: ${synthesis.provider || 'configured API'} · ${synthesis.model || 'configured model'}. Allowance: one request, up to ${synthesis.max_output_tokens || 2048} output tokens and ${synthesis.max_input_chars || 40000} input characters; no tools or automatic retry.`, 'body'));
      card.append(node('p', synthesis.cost || plan.cost || 'API usage is billed separately.', 'warn'));
      if (synthesis.allowance_usd != null) card.append(node('p',`Estimate allowance: $${Number(synthesis.allowance_usd).toFixed(2)}. Conservative maximum for this proposal: $${Number(synthesis.max_estimated_cost_usd).toFixed(6)}. Provider billing is confirmed separately.`, 'body'));
      if (synthesis.rate_card) card.append(detail('Rate and reservation basis', synthesis.rate_card));
    }
    card.append(node('p', 'Nikodemus keeps the captured origin. Open Case receives your question and its origin references; source requests use the public subject details shown in this plan.', 'foot'));
    if (plan.reuse_evidence_from) card.append(node('p','Answer recovery: keep the original question and evidence. This starts one new model attempt; earlier attempts and costs remain in the thread.','warn'));
    card.append(node('h3','Planned sources'));
    const sources = node('ul'); for (const source of (plan.source_scope || [])) sources.append(node('li',source)); card.append(sources);
    if(plan.source_capabilities?.length) {
      const extra=node('details'),caps=node('ul');extra.append(node('summary','All source capabilities · '+plan.source_capabilities.length));
      for(const c of plan.source_capabilities)caps.append(node('li',c.name+': '+c.role+' — '+c.reason+' Availability '+c.availability.replace(/_/g,' ')+'.'));
      extra.append(caps);card.append(extra);
    }
    card.append(node('p','Failed and empty checks are recorded separately from sources that do not apply or are not implemented.','foot'));
    card.append(detail('Full proposal and captured origin', plan));
    const start = button(pending ? 'Check this Start request' : 'Start investigation', () => startProposal(p, pending, start));
    start.id = 'oc-start';
    if (!pending && p.disclosure?.available === false) { start.disabled = true; card.append(node('p',p.disclosure.reason || 'This connection is not ready to start.','warn')); }
    card.append(row(start, pending ? null : button('Revise question', () => { proposal = null; box.replaceChildren(); $('oc-question').focus(); }, 'quiet')));
    if (pending) card.append(node('p','The previous Start response was not received. This checks the same saved request key; it does not create another attempt.', 'warn'));
    box.append(card);
  }
  async function startProposal(p, pending, start) {
    if (busy) return; busy = true; start.disabled = true; error(null);
    const request = pending || {prepared_id:p.prepared_id,request_key:crypto.randomUUID()};
    let accepted = false;
    try {
      // Save the key before the request leaves, so refresh cannot invent another Start.
      sessionStorage.setItem(PENDING, JSON.stringify({request,proposal:p}));
      const started = await api('/api/operations', request);
      accepted = true; sessionStorage.removeItem(PENDING); proposal = null; $('oc-proposal').replaceChildren();
      await open(started.operation_id,true); await historyList();
    } catch (e) { error(e); if (!accepted) drawProposal(p,request); } finally { busy = false; start.disabled = false; }
  }
  function recordRows(host, title, items, render) {
    host.append(node('h2', title + ' · ' + items.length));
    if (!items.length) { host.append(node('p','None recorded.', 'foot')); return; }
    for (const item of items) { const card = node('div', null, 'item'); render(card,item); host.append(card); }
  }
  function entries(value) { return Array.isArray(value) ? value : value && typeof value === 'object' ? Object.entries(value).map(([name,v]) => typeof v === 'object' ? {name,...v} : {name,status:v}) : []; }
  function render(view) {
    const el = $('oc-current'); el.hidden = false; el.replaceChildren();
    const plan = view.plan || view.prepared?.inputs?.plan || {};
    const result = view.result || {};
    const synthesis = view.synthesis || {};
    const state = ['unknown','failed'].includes(view.status) ? (result.status || view.status)
      : view.error && !view.result ? 'needs attention'
      : view.producer_status || result.status || view.producer_state?.status || view.status || 'unknown';
    el.append(node('div','Open Case investigation', 'section-label'));
    el.append(node('h2', view.question || plan.question || 'Investigation'));
    const status = node('p', view.dimensions?.display_status || (state === 'completed' ? 'Completed' : state.replace(/_/g,' ')), ['failed','interrupted','unknown'].includes(state) ? 'warn' : 'body');
    status.id = 'oc-progress'; status.setAttribute('role','status'); el.append(status);
    if (view.progress) el.append(node('p',progressText(view.progress),'body'));
    el.append(node('p', 'Public-record collection: ' + (result.actual_cost_usd === 0 ? '$0' : 'cost not yet reported') + ' · collection model runs: ' + (result.model_runs || []).length, 'foot'));
    if (plan.synthesis?.enabled) el.append(node('p','Optional model answer: '+(synthesis.status || 'waiting for evidence')+' · API dollar total: '+(synthesis.actual_cost_usd == null ? 'not reported' : '$'+synthesis.actual_cost_usd),'foot'));
    if (view.dimensions?.answer?.adequacy) el.append(detail('Model assessment · unverified interpretation',view.dimensions.answer.adequacy));
    if (view.dimensions) el.append(node('p', 'Activity: '+view.dimensions.lifecycle+' · source coverage: '+view.dimensions.acquisition.status+' · answer: '+view.dimensions.answer.status,'foot'));
    if (view.costs) {el.append(node('p',costText(view.costs,'This operation'),'body'));el.append(node('p',costText(view.thread_costs,'This question and preceding attempts'),'foot'));el.append(node('p',cacheReadText(view.thread_costs || view.costs),'foot'));el.append(detail('All component costs and accounting basis',view.costs));el.append(detail('Preceding attempts · precise accounting',view.thread_costs));}
    el.append(node('p', view.saved ? 'Saved to your investigations.' : 'Progress and evidence are kept automatically.', 'foot'));
    const save = button(view.saved ? 'Saved' : 'Save investigation', async () => { try { await api('/api/open-case/operations/'+enc(selected)+'/save', {}); await open(selected); await historyList(); } catch(e) {error(e);} });
    save.id = 'oc-save'; save.disabled = !!view.saved;
    const follow = button('Ask a follow-up…', () => {
      ledger.note('page_shown', {page:'investigation_follow_up', id:view.operation_id || selected, scope:'open_case'});
      reuseEvidence = ''; receiptsContinuation = null; followUp = view.operation_id || selected; origin = view.origin || plan.origin || {kind:'question',text:plan.question};
      proposal = null; $('oc-proposal').replaceChildren(); error(null);
      $('oc-subject').value = plan.subject_name || ''; $('oc-profile').value = plan.subject_type || 'federal_judge_district';
      $('oc-jurisdiction').value = plan.jurisdiction || 'United States'; $('oc-question').value = '';
      if (plan.connector_id) $('oc-connector').value = plan.connector_id;
      $('oc-synthesis').checked = false; $('oc-task-profile').value = plan.task_profile || 'public_records';
      originView(); $('open-case-card').scrollIntoView({block:'start'}); $('oc-question').focus();
    });
    const history = button('History and capture', () => { location.href = '/capture-history?operation_id=' + enc(view.operation_id || selected); });
    history.id = 'oc-capture-history';
    el.append(row(save, follow, history));
    if ((['truncated','rejected','failed','unknown'].includes(synthesis.status) || ['partial','insufficient'].includes(synthesis.answer_status)) && view.result) {
      const recover=button('Review answer recovery', () => {
        receiptsContinuation=null; reuseEvidence=view.operation_id; followUp=view.operation_id;origin=view.origin || plan.origin;
        $('oc-question').value=plan.question; $('oc-subject').value=plan.subject_name;
        $('oc-profile').value=plan.subject_type; $('oc-task-profile').value=plan.task_profile || 'public_records';
        $('oc-jurisdiction').value=plan.jurisdiction; $('oc-synthesis').checked=true;
        if(plan.connector?.connector_id) $('oc-connector').value=plan.connector.connector_id;
        originView();prepare({preventDefault(){}});$('oc-proposal').scrollIntoView({block:'start'});
      });recover.id='oc-answer-recovery';el.append(recover);
    }
    if (view.error || result.error) el.append(node('p',view.error || result.error,'error'));
    if (['unknown','interrupted','failed'].includes(view.status)) el.append(button('Check recorded progress', async () => { try { await api('/api/open-case/operations/'+enc(selected)+'/recover',{}); await open(selected); } catch(e) {error(e);} }, 'quiet'));
    const events = entries(view.producer_state?.events || view.events);
    if (events.length) {
      const d = node('details'); d.open = active.has(view.status); d.append(node('summary','Progress history · '+events.length));
      const localWords = {reserved:'Proposal recorded',claimed:'Investigation assigned',state:'Progress recorded',stage_intent:'Contacting Open Case',stage_end:'Response recorded',note:'Record saved'};
      const list = node('ol'); for (const e of events) list.append(node('li', [e.at || e.recorded_at || e.created_at, e.message || e.detail?.message || localWords[e.kind] || e.event || e.kind || e.type, e.status].filter(Boolean).join(' · '),'foot')); d.append(list); el.append(d);
    }
    if (Object.keys(result).length) {
      if (state === 'partial') el.append(node('p','Partial result: inspect the source failures and coverage below before drawing conclusions.','warn'));
      if (synthesis.answer) {
        el.append(node('h2',synthesis.answer_format==='checked_excerpts'?'Relevant passages from the saved evidence':'Model answer · interpretation needs review'));
        el.append(node('p',(synthesis.answer_format==='checked_excerpts'?'Model-selected passages · ':'Model synthesis · ')+(plan.synthesis?.model || 'configured model'),'foot'));
        el.append(node('p',synthesis.support_verification || 'Citations identify saved records; they do not independently verify the model’s interpretation.','foot'));
        if(synthesis.evidence_relationships) {
          const relations=synthesis.evidence_relationships;
          const p=node('p',relations.record_count+' cited records · '+relations.resolved_family_count+' resolved source families. '+relations.note,'foot');
          p.id='oc-evidence-relationships';el.append(p,detail('Cited record relationships',relations));
        }
        const citations=entries(synthesis.citations), answer=node('p',null,'body');
        answer.style.whiteSpace='pre-line';
        // Link only the locally resolved record ids. Model text remains text,
        // and every link lands on the preserved excerpt actually in its input.
        if(synthesis.answer_format==='checked_excerpts') {
          for(const selection of entries(synthesis.selections)) {
            answer.append(document.createTextNode('Saved source passage: “'+selection.quote+'” '));
            const index=citations.findIndex(c=>c.record_id===selection.record_id);
            if(index>=0) {const a=node('a','['+(index+1)+']');a.href='#oc-citation-'+(index+1);a.title='Inspect the saved source';answer.append(a);}
            answer.append(document.createTextNode('\n\n'));
          }
          if(!entries(synthesis.selections).length) answer.append(document.createTextNode('No passages were selected from the supplied evidence.'));
        } else {
          const pattern=/\[([^\]\n]+)\]/g; let cursor=0, match;
          while ((match=pattern.exec(synthesis.answer))) {
            answer.append(document.createTextNode(synthesis.answer.slice(cursor,match.index)));
            const index=citations.findIndex(c=>c.record_id===match[1]);
            if(index>=0) {const a=node('a','['+(index+1)+']');a.href='#oc-citation-'+(index+1);a.title='Inspect saved evidence: '+(citations[index].title || match[1]);answer.append(a);}
            else answer.append(document.createTextNode(match[0]));
            cursor=pattern.lastIndex;
          }
          answer.append(document.createTextNode(synthesis.answer.slice(cursor)));
        }
        el.append(answer);
        recordRows(el,'Cited evidence',citations,(n,c)=>{
          const index=citations.indexOf(c)+1;n.id='oc-citation-'+index;
          n.append(node('strong','['+index+'] '+(c.title || c.label || 'Saved evidence')));
          if(c.operation_id) {
            n.append(node('div',c.operation_id===selected?'Saved in this investigation.':'Saved in an earlier investigation.','foot'));
            if(c.operation_id!==selected) n.append(button('Open source investigation',()=>open(c.operation_id,true),'quiet'));
          }
          if(c.excerpt || c.text) {const excerpt=node('p',c.excerpt || c.text);excerpt.style.whiteSpace='pre-line';n.append(excerpt);}
          if(c.source_url || c.url) n.append(link(c.source_name || 'Original source',c.source_url || c.url));
          n.append(detail('Saved citation and source hash',c));
        });
        const review=node('details'); review.append(node('summary','Flag an unsupported answer'));
        const reason=node('textarea'); reason.id='oc-review-reason'; reason.maxLength=4000;
        reason.setAttribute('aria-label','Unsupported claim and evidence gap');
        reason.placeholder='Identify the claim and explain what the cited evidence does not establish.';
        const hold=button('Hold this answer',async()=>{
          hold.disabled=true;
          try { await api('/api/open-case/operations/'+enc(selected)+'/answer-review',{reason:reason.value,response_sha256:synthesis.response_artifact?.sha256}); await open(selected); await historyList(); }
          catch(e){error(e);hold.disabled=false;}
        }); hold.id='oc-review-hold';review.append(reason,hold);el.append(review);
      }
      if(synthesis.reviews) el.append(detail('Review history · original response retained',synthesis.reviews));
      if(synthesis.held_answer) el.append(detail('Held model answer · unsupported claim reported',synthesis.held_answer));
      if (synthesis.error) el.append(node('p','Model answer needs attention: '+synthesis.error.replace(/\.*$/,'')+'. The source records below remain available.','warn'));
      if (plan.synthesis?.enabled) el.append(detail('Model run and usage',synthesis));
      if(view.record_chronology?.status==='available') {
        const chronology=view.record_chronology, section=node('section');section.id='oc-record-chronology';
        section.append(node('h2','Recorded judicial appointments'),node('p',chronology.introduction,'foot'));
        const table=node('table');table.style.cssText='width:100%;text-align:left;border-spacing:8px';
        const head=node('tr');for(const label of ['Court','Commission','Termination','Oath']) head.append(node('th',label));table.append(head);
        for(const appointment of chronology.appointments) {
          const tr=node('tr');for(const field of ['court_name','commission_date','termination_date','oath_date']) {
            const value=appointment.rows.find(r=>r.field_path.endsWith('/'+field));tr.append(node('td',value?.value || 'Not supplied'));
          }table.append(tr);
        }
        section.append(table);
        for(const limit of chronology.limitations.slice(1,4)) section.append(node('p',limit,'foot'));
        for(const citation of chronology.citations) if(citation.result_artifact_url) section.append(link('Inspect saved FJC source record',citation.result_artifact_url));
        section.append(detail('All typed fields and source provenance',chronology));el.append(section);
      }
      const renderFinding = (n,f) => {
        n.append(node('strong',f.title || f.signal_type || f.id || 'Finding'));
        if(f.evidence_label || f.evidence_kind) n.append(node('div',f.evidence_label || f.evidence_kind,'foot'));
        if(f.correction) n.append(node('p','Linked producer correction: interpret the typed source fields below. The historical rendering is preserved.','foot'));
        if(f.semantic_record?.appointments) {for(const a of f.semantic_record.appointments) n.append(node('p',a.court_name+' · commission: '+(a.commission_date || 'not supplied')+' · oath: '+(a.oath_date || 'not supplied by this source'),'body'));}
        if(f.lineage) n.append(node('div','Source identity: '+f.lineage.identity_status+(f.lineage.provenance_family_id?' · family '+f.lineage.provenance_family_id:''),'foot'));
        if (!f.evidence_kind && (f.epistemic_level || f.is_absence)) n.append(node('div',(f.epistemic_level ? 'Open Case label: '+f.epistemic_level : '')+(f.is_absence?' · documented absence':''),'foot'));
        if (f.body || f.description) { const body=node('p',f.body || f.description); body.style.whiteSpace='pre-line';n.append(body); }
        if (f.source_url) n.append(link(f.source_name || 'Source',f.source_url));
        n.append(detail('Source record and provenance',f));
      };
      const findings = entries(view.findings || result.findings);
      if(view.evidence_groups) el.append(detail('Source families and substantive revisions',view.evidence_groups));
      recordRows(el,'Findings',findings.filter(f=>!f.is_absence && f.evidence_kind!=='acquisition_notice'),renderFinding);
      const gaps = findings.filter(f=>f.is_absence || f.evidence_kind==='acquisition_notice');
      if (gaps.length) recordRows(el,'Acquisition notices and documented gaps',gaps,renderFinding);
      recordRows(el,'Sources',entries(result.sources),(n,s) => { n.append(s.url || s.source_url ? link(s.name || s.source_name || s.title || 'Source',s.url || s.source_url) : node('strong',s.name || s.source_name || s.title || 'Source')); n.append(detail('Saved source record',s)); });
      recordRows(el,'Failures and gaps',entries(result.failures),(n,f) => { n.append(node('div',typeof f === 'string'?f:(f.message || f.error || f.detail || f.source || 'Source failed'),'warn')); if (typeof f !== 'string') n.append(detail('Failure record',f)); });
      el.append(detail('Source coverage',result.source_statuses || {}));
      el.append(detail('Model runs',result.model_runs || []));
    }
    window.NikodemusReceipts?.mount(el,view,suggestion=>{
      // Populate only; review the existing profile and allowance before Start.
      follow.click(); $('oc-question').value=suggestion.question;
      receiptsContinuation={operation_id:view.operation_id,id:suggestion.id,projection_sha256:suggestion.projection_sha256};
      $('oc-proposal').append(node('p',suggestion.reason+' '+suggestion.limitation,'foot'));
    });
    el.append(detail('Origin as captured',view.origin || plan.origin || {}));
    if (view.follow_up_of || plan.follow_up_of) el.append(button('Open preceding investigation',()=>open(view.follow_up_of || plan.follow_up_of,true),'quiet'));
    const custody = view.result_ref?.custody || {};
    const depositionId = view.deposition_id || view.investigation?.deposition_id || custody.deposition_id;
    if (depositionId) {
      const verified = custody.verification?.ok === true;
      el.append(node('p',verified ? 'Source package verified against the pinned Open Case key. The signature establishes origin and integrity of signed fields.' : 'Source package is kept but its signature has NOT been verified. Inspect the custody record before relying on its provenance.',verified?'foot ok':'warn'));
      el.append(link('Exact source package in custody','/api/depositions/'+enc(depositionId)+'/bytes'));
      el.append(detail('Custody and signature verification',custody));
    }
    const artifacts = entries(view.artifacts || view.investigation?.kept);
    if (artifacts.length) {
      const d = node('details'); d.append(node('summary','Exact saved artifacts · '+artifacts.length));
      for (const a of artifacts) { const url = a.url || '/api/open-case/operations/'+enc(selected)+'/artifacts/'+enc(a.name); d.append(row(link(a.name,url),node('code',a.sha256 || ''))); } el.append(d);
    }
    el.append(detail('Frozen investigation plan',plan));
    el.append(node('p','Operation '+(view.operation_id || selected)+' · reopening reads these saved records.','foot'));
  }
  async function open(id, bringIntoView = false, recordVisit = bringIntoView) {
    if (!id) return; selected = id; clearTimeout(timer);
    try {
      const v = await api('/api/open-case/operations/'+enc(id)); if (selected !== id) return;
      render(v);
      if (recordVisit) ledger.note('result_viewed', {id, kind:'investigation', scope:'open_case'});
      const url = new URL(location.href); url.searchParams.set('operation',id); history.replaceState(null,'',url);
      if (bringIntoView) $('oc-current').scrollIntoView({block:'start',behavior:'smooth'});
      if (active.has(v.status)) timer = setTimeout(()=>open(id),1800);
    } catch(e) { error(e); timer = setTimeout(()=>open(id, false, recordVisit),5000); }
  }
  async function historyList() {
    const d = await api('/api/open-case/operations'); const el = $('oc-history'); el.replaceChildren();
    for (const o of (d.operations || [])) { const item = node('div',null,'item'); item.append(button(o.question || o.plan?.question || o.operation_id,()=>open(o.operation_id,true),'quiet')); const status=o.dimensions?.display_status || (['unknown','failed'].includes(o.status)?o.status:o.result?.status || o.producer_state?.status || o.status);item.append(node('div',[status,o.saved?'saved':'automatically kept',o.created_at].filter(Boolean).join(' · '),'foot')); el.append(item); }
    if (!el.childElementCount) el.append(node('p','No investigations yet. Start with a question above.','foot'));
  }
  async function boot() {
    ledger.init();
    ledger.note('page_shown', {page:'investigation', scope:'open_case'});
    $('oc-form').addEventListener('submit',prepare);
    $('oc-question').addEventListener('input',()=>{reuseEvidence='';});
    $('oc-profile').addEventListener('change',()=>{if($('oc-profile').value==='senator') $('oc-task-profile').value='public_records';});
    try {
      const params = new URLSearchParams(location.search), key = params.get('origin_key');
      if (key) {
        const raw = sessionStorage.getItem(key);
        if (raw) {
          origin = JSON.parse(raw);
          const observed = 'nikodemus.opencase.origin-observed.v1.' + key;
          if (!sessionStorage.getItem(observed)) { noteOrigin(origin); sessionStorage.setItem(observed, '1'); }
        }
      }
      originView();
      const c = await api('/api/connectors');
      for (const x of (c.connectors || []).filter(x=>x.producer === 'open_case' && x.enabled)) { const opt = node('option',x.display || x.connector_id); opt.value=x.connector_id; $('oc-connector').append(opt); }
      if (!$('oc-connector').options.length) $('oc-connector').append(node('option','No Open Case connection configured'));
      const r = await api('/api/open-case/status');
      $('oc-readiness').textContent = r.reason || r.readiness?.reason || (r.available || r.ready || r.readiness?.available ? 'Open Case is ready. Review a proposal before starting.' : 'Open Case connection needs setup. Existing investigations remain readable.');
      if(r.synthesis) {
        $('oc-synthesis').disabled = r.synthesis.available === false;
        $('oc-synthesis-config').textContent = (r.synthesis.available === false ? (r.synthesis.reason || 'No model API is configured.') : `${r.synthesis.provider || 'Configured API'} · ${r.synthesis.model || 'configured model'}.`) + ' Optional: one request, at most 4,096 output tokens. '+(r.synthesis.cost || '')+' No model tools or automatic retries; no plugin subscription required.';
      }
      await historyList(); if (params.get('operation')) await open(params.get('operation'), false, true);
      const pending = sessionStorage.getItem(PENDING); if(pending) {const v=JSON.parse(pending);drawProposal(v.proposal,v.request);}
    } catch(e) {error(e);}
    document.addEventListener('click',e=> {const b=e.target.closest('[data-oc-deposition]'); if(b) setOrigin({kind:'deposition',deposition_id:b.dataset.ocDeposition,item_ref:b.dataset.ocItem,title:b.dataset.ocTitle});});
  }
  document.addEventListener('DOMContentLoaded',boot);
})();
