/* Local, derived Receipts views. Opening a panel performs one authenticated
 * local read. Suggested follow-ups only populate the existing proposal form. */
(() => {
  'use strict';
  const node = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  const detail = (label, value) => { const n=node('details'); n.append(node('summary',label)); const p=node('pre',JSON.stringify(value,null,2)); p.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere'; n.append(p); return n; };
  const source = trace => {
    const box=node('div'); box.className='foot';
    const a=node('a',trace.record_id || trace.operation_id); a.href='/investigation?operation='+encodeURIComponent(trace.operation_id);box.append(a);
    const ref=trace.result_artifact;
    if(ref?.name) {const raw=node('a',' · exact saved result');raw.href='/api/open-case/operations/'+encodeURIComponent(trace.operation_id)+'/artifacts/'+encodeURIComponent(ref.name);raw.target='_blank';raw.rel='noopener noreferrer';box.append(raw);}
    box.append(detail('Record, source family and hashes',trace));return box;
  };
  const group = (host, title, rows, draw) => {
    const d=node('details');d.append(node('summary',title+' · '+rows.length));
    if(!rows.length)d.append(node('p','None identified by this projection. This does not establish completeness.'));
    for(const r of rows){const n=node('div');n.className='item';draw(n,r);d.append(n);}host.append(d);
  };
  function render(host,data,onFollowUp) {
    host.replaceChildren();
    host.append(node('p','Derived from saved evidence in '+data.manifest.inputs.length+' investigation(s). No source or model requests are made.'));
    const resolved=data.evidence_matrix.filter(r=>r.lineage?.identity_status==='resolved' && r.lineage?.provenance_family_id);
    const families=new Set(resolved.map(r=>r.lineage.provenance_family_id));
    host.append(node('p',data.evidence_matrix.length+' retained record references · '+families.size+' identified source family/families · '+(data.evidence_matrix.length-resolved.length)+' unresolved family reference(s). Repeated captures from one family do not provide independent corroboration.'));
    group(host,'Evidence matrix',data.evidence_matrix,(n,r)=>{
      n.append(node('strong',r.title),node('p',r.state.replace(/_/g,' ')+' · '+r.evidence_kind.replace(/_/g,' ')),source(r));
      if(r.excerpt)n.append(detail('Saved source text',r.excerpt));
      n.append(node('p',r.used_in_answer?'Referenced in the selected answer. Citation structure only; factual support remains unassessed.':'Not marked as referenced in the selected answer.'));
    });
    group(host,'Missing material and unresolved references',data.missing_evidence,(n,r)=>{
      n.append(node('strong',r.title),node('p',r.reason));if(r.excerpt)n.append(node('blockquote',r.excerpt));n.append(source(r.trace));
    });
    group(host,'Source coverage and blockers',data.coverage,(n,r)=>{
      n.append(node('strong',r.source+' · '+r.state.replace(/_/g,' ')),node('p',r.reason),node('p',r.next_action),source(r));
    });
    group(host,'Typed timeline',data.timeline,(n,r)=>{
      n.append(node('strong',(r.date || 'Date needs review')+' · '+r.title),node('p',r.status.replace(/_/g,' ')),source(r.trace));
      if(r.historical_coverage==='rendered_fields_only')n.append(node('p','Historical rendered fields only; the complete upstream revision is unknown.'));
    });
    group(host,'Records without a typed event date',data.unplaced_records,(n,r)=>{
      n.append(node('p',r.reason));if(r.matched_text)n.append(node('p','Unplaced text mention: '+r.matched_text));n.append(source(r.trace));
    });
    group(host,'Field comparisons and candidate conflicts',data.comparisons,(n,r)=>{
      n.append(node('strong',r.title+' · '+r.type.replace(/_/g,' ')),node('p',r.dates.join(' / ')),node('p',r.reason));
      for(const t of r.traces)n.append(source(t));
    });
    group(host,'Targeted continuation suggestions',data.continuations,(n,r)=>{
      n.append(node('strong',r.title),node('p',r.reason),node('p',r.question),node('p',r.limitation));
      const b=node('button','Use as follow-up question');b.type='button';b.addEventListener('click',()=>onFollowUp({...r,projection_sha256:data.projection_sha256}));n.append(b);
      const add=node('button','Add a source with Deflate');add.type='button';add.className='quiet';
      add.addEventListener('click',()=>{
        const key='nikodemus.deflate.origin.'+crypto.randomUUID();
        const origin={kind:'operation',operation_id:data.operation_id,title:r.title,
          receipts_continuation:{operation_id:data.operation_id,id:r.id,projection_sha256:data.projection_sha256}};
        try{sessionStorage.setItem(key,JSON.stringify(origin));}
        catch(_){n.append(node('p','The source link could not be retained in browser storage. No source was started.'));return;}
        location.href='/deflate-reading?origin_key='+encodeURIComponent(key);
      });n.append(add);
      n.append(detail('Proposed action and evidence references',r));
    });
    host.append(detail('Projection manifest and limits',{manifest:data.manifest,limitations:data.limitations,projection_sha256:data.projection_sha256}));
  }
  function mount(host,view,onFollowUp) {
    if(!view.result)return;
    const panel=node('section');panel.id='oc-receipts';panel.append(node('h2','Receipts evidence review'));
    panel.append(node('p','Inspect the saved evidence matrix, source gaps, typed timeline and candidate conflicts. Suggestions require a separate reviewed Start.'));
    const button=node('button','Build local evidence review'), content=node('div');button.type='button';
    button.addEventListener('click',async()=>{
      button.disabled=true;
      try {
        const response=await fetch('/api/open-case/operations/'+encodeURIComponent(view.operation_id)+'/receipts');
        const data=await response.json();if(!response.ok)throw new Error(data.error || 'Saved evidence could not be projected.');
        render(content,data,onFollowUp);button.textContent='Rebuild from saved evidence';
      }catch(e){content.replaceChildren(node('p',e.message || String(e)));}
      finally{button.disabled=false;}
    });
    panel.append(button,content);host.append(panel);
  }
  window.NikodemusReceipts={mount};
})();
