/* Read-only local reconstruction. Text is always text; only explicit saved
 * references become links. No automatic continuation, retries or source calls. */
import { estimatedDollars } from '/work/cost-display.js';
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const words = value => String(value || 'not recorded').replace(/_/g, ' ');
  const node = (tag, text, cls) => { const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n; };
  const details = (label, value) => { const d=node('details');d.append(node('summary',label),node('pre',JSON.stringify(value,null,2)));return d; };
  const link = (label, href) => {
    try { const url=new URL(href,location.href);if(!['http:','https:'].includes(url.protocol))return node('span',label);
      const a=node('a',label);a.href=url.href;if(url.origin!==location.origin){a.target='_blank';a.rel='noopener noreferrer';}return a;
    } catch (_) { return node('span',label); }
  };
  const traceLink = (label,id) => link(label,'/capture-history?operation_id='+encodeURIComponent(id));
  const list = value => Array.isArray(value)?value:[];
  const section = (host,id,title) => { const s=node('section');s.id=id;s.append(node('h2',title));host.append(s);return s; };
  const card = (host,title,cls='') => { const c=node('article',null,'card '+cls);if(title)c.append(node('h3',title));host.append(c);return c; };
  const none = (host,text) => host.append(node('p',text,'empty'));

  function render(data) {
    const host=$('history-content');host.replaceChildren();const nodes=data.nodes||{},links=list(data.links);
    const operations=list(nodes.operations), byOperation=new Map(operations.map(o=>[o.operation_id,o]));
    const artifactById=new Map(list(nodes.artifacts).map(a=>[a.id,a]));
    const gaps=list(data.gaps), capturedGaps=list(data.capture_gaps?.gaps);
    const warning=section(host,'history-gaps','Capture gaps');
    if(!gaps.length&&!capturedGaps.length)none(warning,'No gap was reported among these linked saved records. This does not establish that every past action was captured.');
    for(const gap of gaps) {const c=card(warning,words(gap.kind),'warning');c.append(node('p',gap.reason),details('Recorded reference',gap));}
    if(capturedGaps.length)warning.append(details('Saved capture failure records',capturedGaps));
    if(data.capture_gaps?.read_gaps?.length)warning.append(details('Capture log read errors',data.capture_gaps.read_gaps));
    if(data.capture_gaps?.truncated)warning.append(node('p','The capture gap log exceeded its read limit; earlier gaps may be outside this view.','warning'));

    const questions=section(host,'history-questions','Questions and intent');
    if(!operations.length)none(questions,'No started operation is linked to this selection. Its prepared proposal and exact captured input are shown below.');
    for(const op of operations) {const c=card(questions,op.question||'Saved operation · '+words(op.action_id));c.id='history-'+op.operation_id;
      const answer=list(nodes.answers).find(a=>a.id==='answer:'+op.operation_id);
      c.append(node('p','Operation lifecycle: '+words(op.status)+(answer?' · Answer: '+words(answer.current_status):'')+' · '+(op.created_at||'time unavailable'),'muted'));
      if(op.error)c.append(node('p',op.error,'warning'));
      if(op.url)c.append(link('Open saved operation',op.url));
      const cost=op.costs||{};
      const incomplete=['unknown','partial'].includes(cost.accounting_status)||list(cost.unknown_components).length>0||list(cost.unaccounted_operation_ids).length>0;
      const estimate=cost.estimated_cost_usd??cost.known_estimated_subtotal_usd;
      const known=typeof estimate==='number'&&Number.isFinite(estimate);
      const costText=cost.accounting_status==='reported_zero'&&!incomplete?'Recorded collection cost: $0.':known?
        'Known '+(incomplete?'subtotal':'cost')+': '+estimatedDollars(estimate)+'. '+(incomplete?'Accounting is incomplete; unknown components are not counted as free. ':'')+'Provider billing remains unconfirmed.':
        'Cost is unknown or incomplete; missing usage is not counted as free.';
      c.append(node('p',costText,'muted'));
      c.append(details('Operation identity and usage accounting',op));
    }

    const origins=section(host,'history-origins','Original passage and revisions');
    for(const doc of list(nodes.documents)) {const c=card(origins,doc.title||'Saved document');c.append(node('p','Current saved revision '+doc.revision+' · '+(doc.saved_at||'time unavailable'),'muted'),link('Open document',doc.url),details('Document identity',doc));}
    if(!list(nodes.documents).length)none(origins,'No explicit document reference was retained for this question.');
    for(const revision of list(nodes.revisions)) {const c=card(origins,'Revision '+revision.revision);c.append(node('p',(revision.chars??'Unknown')+' characters · '+words(revision.status)+' · '+(revision.saved_at||'time unavailable'),'muted'));
      if(revision.status==='retained')c.append(link('Read this exact retained revision',revision.url));c.append(details('Revision and content hashes',revision));}
    for(const snapshot of list(nodes.snapshots)) {const c=card(origins,'Captured '+words(snapshot.kind),snapshot.verification==='verified'?'':'warning');
      const range=snapshot.range;c.append(node('p',(snapshot.chars??'Unknown')+' captured characters'+(range?' · range '+range.start+'–'+range.end+' ('+range.units+')':''),'muted'));
      c.append(node('p',snapshot.committed_revision_match===true?'The captured text exactly matches its saved revision and range.':snapshot.committed_revision_match===false?'The captured input differs from its referenced revision; inspect both preserved records.':'No committed revision match is established for this input.'));
      if(snapshot.verification==='verified')c.append(link('Read the original captured input',snapshot.url));c.append(details('Snapshot identity and exact hashes',snapshot));}

    const proposals=section(host,'history-proposals','Prepared proposals');
    if(!list(nodes.proposals).length)none(proposals,'No saved proposal reference was available.');
    for(const proposal of list(nodes.proposals)) {const starts=links.filter(l=>l.from===proposal.id&&l.relation==='started_from');const c=card(proposals,words(proposal.action_id));
      c.append(node('p',starts.length?'A saved operation explicitly names this proposal.':'Prepared only · no Start is linked to this proposal.','muted'));
      for(const start of starts)c.append(traceLink('Inspect the linked operation',start.to));c.append(details('Frozen proposal reference',proposal));}

    const attempts=section(host,'history-attempts','Attempts and failures');
    if(!list(nodes.attempts).length)none(attempts,'No attempt event is recorded in this trace. A prepared proposal is not proof of a request.');
    for(const attempt of list(nodes.attempts)) {const fail=['error','failed','unknown'].includes(attempt.outcome)||attempt.kind==='failed';const c=card(attempts,words(attempt.kind)+(attempt.outcome?' · '+words(attempt.outcome):''),fail?'warning':'');
      c.append(node('p',[attempt.stage,attempt.at,attempt.detail?.provider,attempt.detail?.model].filter(Boolean).join(' · '),'muted'));
      if(attempt.detail?.message)c.append(node('p',attempt.detail.message));
      if(attempt.detail?.capture_gap)c.append(node('p','Capture failure: '+words(attempt.detail.capture_gap.why)+'. '+(attempt.detail.capture_gap.capture_gap?.durable===false?'The supplemental gap record was not confirmed durable; this operation note preserves its status.':''),'warning'));
      if(typeof attempt.detail?.duration_s==='number')c.append(node('p','Recorded attempt duration: '+attempt.detail.duration_s+' seconds.','muted'));
      if(attempt.identity_status==='event_only_no_attempt_identity')c.append(node('p','This historical event has no stable attempt identity; separate retries are not inferred.','muted'));
      for(const edge of links.filter(l=>l.from===attempt.id&&l.relation.startsWith('captured_'))) {const art=artifactById.get(edge.to);if(art?.verification==='verified')c.append(link('Inspect '+words(edge.relation),art.url));}
      c.append(details('Attempt identity, provider metadata and usage',attempt));}

    const sources=section(host,'history-sources','Evidence and source outcomes');
    if(!list(nodes.evidence).length)none(sources,'No verified saved result yielded an evidence record in this view.');
    for(const evidence of list(nodes.evidence)) {const c=card(sources,evidence.title||'Saved evidence record');c.append(node('p',words(evidence.evidence_kind),'muted'));
      const art=artifactById.get(evidence.artifact_id);if(art?.verification==='verified')c.append(link('Inspect saved source evidence',art.url));
      if(evidence.source_url)c.append(node('span',' · '),link(evidence.source_name||'Original source',evidence.source_url));
      c.append(details('Source identity, exact result hash and correction',evidence));}
    for(const source of list(nodes.source_checks)) {const c=card(sources,source.source||'Source check',source.kind==='failures'?'warning':'');
      c.append(node('p',[source.role,source.status].filter(Boolean).map(words).join(' · '),'muted'));if(source.reason)c.append(node('p',source.reason));
      if(source.attempt_inferred===false)c.append(node('p','Declared capability; this is not a recorded attempt.','muted'));c.append(details('Exact source outcome reference',source));}

    const answers=section(host,'history-answers','Answers and captured outputs');
    if(!list(nodes.answers).length)none(answers,'No saved answer or captured provider output is explicitly linked.');
    for(const answer of list(nodes.answers)) {const c=card(answers,words(answer.current_status),answer.current_status==='held'||answer.current_status==='integrity_unavailable'?'warning':'');
      c.append(node('p',answer.interpretation_support||'A saved response is not an independent finding.','muted'));
      if(answer.reviews?.length)c.append(node('p',answer.reviews[answer.reviews.length-1].reason));
      if(answer.error)c.append(node('p',answer.error));if(answer.display_url)c.append(link('Open the saved answer and its source links',answer.display_url));
      for(const ref of list(answer.source_refs)) {const art=artifactById.get('artifact:'+answer.operation_id+':'+ref.name);if(art?.verification==='verified')c.append(node('span',' · '),link('Inspect '+ref.name,art.url));}
      c.append(details('Saved output, receipt and review references',answer));}

    const followups=section(host,'history-followups','Follow-ups and retries');
    const relations=links.filter(l=>['follow_up','retry','reuses_evidence'].includes(l.relation));
    if(!relations.length)none(followups,'No explicit follow-up, retry, or evidence reuse link was recorded.');
    for(const relation of relations) {const c=card(followups,words(relation.relation));
      for(const [label,id] of [['From',relation.from],['To',relation.to]]) {const p=node('p');p.append(node('span',label+': '),traceLink(byOperation.get(id)?.question||id,id));c.append(p);}c.append(details('Explicit saved relationship',relation));}

    const attention=section(host,'history-attention','Observed activity');attention.append(node('p','Visits and UI actions show observed activity. They do not prove that a passage was read, agreed with, or sent to a model.','muted'));
    if(!list(nodes.attention).length)none(attention,'No attention record names these exact saved identities.');
    for(const event of list(nodes.attention)) {const c=card(attention,words(event.type));c.append(node('p',(event.at||event.received_at||'time unavailable')+(event.identity_status==='legacy_unverifiable'?' · historical capture without a stable event ID':''),'muted'));
      if(event.interval)c.append(node('p',words(event.interval.state)+': '+(event.interval.duration_ms/1000).toFixed(1)+' seconds ('+event.interval.duration_ms+' ms). This is a visibility, focus and idle estimate; it does not establish reading or attention.','muted'));
      c.append(details('Observed event identity and preserved line hash',event));}
    host.append(details('Artifact verification records',list(nodes.artifacts)),details('Workspace identity and reconstruction hash',{workspace:data.workspace,projection_sha256:data.projection_sha256,scope:data.scope,limits:data.limits,side_effects:data.side_effects}));
    const limits=node('ul');for(const text of list(data.limitations))limits.append(node('li',text));host.append(limits);
    $('history-status').textContent=operations.length+' operation(s) · '+list(nodes.proposals).length+' proposal(s) · '+gaps.length+' visible gap(s).';
  }

  async function load() {
    const button=$('history-refresh');button.disabled=true;$('history-error').replaceChildren();
    try {
      const params=new URLSearchParams(location.search), roots=['operation_id','doc_id','prepared_id'].filter(k=>params.has(k));
      if(roots.length!==1)throw new Error('Open capture history from a saved document, proposal, or operation. Exactly one record must identify this view.');
      const query=new URLSearchParams({[roots[0]]:params.get(roots[0])});
      const response=await fetch('/api/capture/history?'+query,{credentials:'same-origin',cache:'no-store'});
      if(response.status===401) {const c=card($('history-error'),'Pair this browser','warning');c.append(link('Open pairing','/pair'));throw new Error('This history is private to a paired browser.');}
      const data=await response.json();if(!response.ok)throw new Error(data.error||'Saved history could not be read.');render(data);
    } catch(error) {$('history-status').textContent='History unavailable';$('history-error').append(node('p',error.message||String(error),'card error'));}
    finally {button.disabled=false;}
  }
  document.addEventListener('DOMContentLoaded',()=>{$('history-refresh').addEventListener('click',load);load();});
})();
