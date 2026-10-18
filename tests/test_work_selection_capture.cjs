// Real Work bootstrap + pinned ProseMirror/plain adapters. No live server or
// request is used: all API/static traffic is fulfilled inside this fixture.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8477';
const body='A private forty-nine character selection boundary. More words remain in this draft.';
const docs={doc_selection:{doc_id:'doc_selection',title:'Selection fixture',title_is_manual:true,body,revision:1,fingerprint:'fixture-1',saved_at:'2026-10-18T00:00:00Z'},
  doc_second:{doc_id:'doc_second',title:'Second fixture',title_is_manual:true,body,revision:1,fingerprint:'fixture-2',saved_at:'2026-10-18T00:00:00Z'},
  doc_plain:{doc_id:'doc_plain',title:'Plain fixture',title_is_manual:true,body:'Plain\u0001 text selection remains observable.',revision:1,fingerprint:'fixture-3',saved_at:'2026-10-18T00:00:00Z'}};
let checks=0;const ok=(v,m)=>{assert.ok(v,m);checks++;console.log('ok '+m);};
(async()=>{
  const browser=await chromium.launch();
  try{
    const context=await browser.newContext(),posted=[],egress=[],unexpected=[],errors=[];
    await context.route('**/*',async route=>{
      const req=route.request(),u=new URL(req.url()),p=u.pathname;
      if(u.origin!==base){egress.push(req.url());return route.abort();}
      const json=data=>route.fulfill({json:data});
      if(p==='/api/ledger/config')return json({enabled:true,scope_id:'ledger_'+'a'.repeat(24)});
      if(p==='/api/ledger') {const events=req.postDataJSON().events;posted.push(...events);return json({acknowledged:events.map(e=>e.event_id)});}
      if(p==='/api/actions')return json({actions:[{id:'analyze.decompose',label:'Analyze',group:'on_draft',subjects:['selection','document'],readiness:{ready:true}}]});
      if(p==='/api/operations')return json({operations:[]});
      if(p==='/api/notes')return json({notes:[]});
      if(p==='/api/vault/status')return json({preview:false});
      if(p==='/api/notebook/documents')return json({documents:[docs.doc_selection]});
      if(p.startsWith('/api/notebook/documents/')&&req.method()==='GET')return json(docs[p.split('/').at(-1)]||{});
      if(p==='/brand.js')return route.fulfill({contentType:'application/javascript',body:'window.BRAND={name:"Nikodemus"};'});
      if(p==='/work'||p.startsWith('/work/')){
        const file=path.join(root,p==='/work'?'webapp/work/work.html':'webapp'+p);
        if(fs.existsSync(file))return route.fulfill({contentType:p==='/work'?'text/html':p.endsWith('.css')?'text/css':'application/javascript',body:fs.readFileSync(file)});
      }
      unexpected.push(req.method()+' '+p);return route.fulfill({status:404,body:'Unexpected fixture request'});
    });
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/work');await page.waitForFunction(()=>window.__work?.session.id==='doc_selection');
    const pause=()=>page.waitForTimeout(350);
    const selected=async()=>{await page.evaluate(()=>window.__work.ledger.flush());return posted.filter(e=>e.type==='material_selected');};
    const count=async()=> (await selected()).length;
    const programSelect=(a,b)=>page.evaluate(([a,b])=>{const e=window.__work.editor;e.focus();e.setSelection(a,b);},[a,b]);
    await pause();ok(await count()===0,'opening an empty caret emits no material selection');

    // DOM selection is how accessibility selection reaches ProseMirror: no
    // mouseup, keyup, toolbar click, or direct invocation of its callback.
    await page.evaluate(()=>{
      const node=document.querySelector('.pm-editor p').firstChild;
      window.__work.editor.focus();window.getSelection().setBaseAndExtent(node,0,node,49);
    });
    await page.waitForFunction(()=>window.__work.editor.getSelection().end===49);await pause();
    let rows=await selected();
    ok(rows.length===1,'DOM accessibility-style selection reaches the real editor callback');
    ok(await page.locator('#sel-popover').isHidden(),'generic selection observation opens no popup');
    ok(rows[0].subject.id==='doc_selection'&&rows[0].subject.revision==='1'&&rows[0].subject.kind==='editor_range','selection metadata names only document revision and observed kind');
    ok(JSON.stringify(Object.keys(rows[0].subject).sort())===JSON.stringify(['id','kind','revision'])&&!JSON.stringify(rows).includes('private'),'selected words and offsets never enter activity metadata');
    await programSelect(0,49);await programSelect(0,49);await pause();
    ok(await count()===1,'repeated callbacks for the same settled selection are deduplicated');
    await programSelect(1,10);await programSelect(2,20);await programSelect(3,30);await pause();
    ok(await count()===2,'rapid intermediate ranges produce only one settled observation');
    await programSelect(3,3);await pause();ok(await count()===2,'empty selection is suppressed');
    await programSelect(3,30);await pause();ok(await count()===3,'a later re-selection after collapse is a new observation');
    await programSelect(4,32);await page.locator('#doc-menu-btn').focus();await pause();
    ok(await count()===3,'losing editor focus before debounce suppresses stale selection');
    await page.evaluate(()=>window.__work.editor.setSelection(5,33));await pause();
    ok(await count()===3,'unfocused programmatic range change emits no attention event');
    await programSelect(6,34);await page.locator('a[data-page="help"]').click();await pause();
    ok(await count()===3,'leaving Work before debounce suppresses stale range');
    await page.locator('a[data-page="work"]').click();
    await page.evaluate(()=>window.__work.ledger.setEnabled(false));await programSelect(7,35);await pause();
    ok(await count()===3,'recording Off suppresses new selection records');
    await page.evaluate(()=>window.__work.ledger.setEnabled(true));await programSelect(0,0);await pause();
    await page.evaluate(()=>window.__work.session.open('doc_second'));await programSelect(3,30);await pause();
    rows=await selected();ok(rows.length===4&&rows[3].subject.id==='doc_second','same range in a distinct document retains distinct identity');

    // Existing mouse/Shift popover paths keep their behavior. Observation must
    // happen before the popover takes focus, and still deduplicate callbacks.
    await programSelect(0,5);await page.locator('#editor-host').dispatchEvent('mouseup');await pause();
    ok(await count()===5&&!await page.locator('#sel-popover').isHidden(),'mouse popup remains available and does not duplicate selection metadata');
    await page.evaluate(()=>window.__work.actions.hidePopover());
    await page.evaluate(()=>window.__work.session.open('doc_plain'));await pause();
    ok(await page.evaluate(()=>window.__work.editor.mode())==='plain','real plain-text fallback is under test');
    await page.evaluate(()=>{const ta=document.querySelector('.plain-editor');ta.focus();ta.setSelectionRange(0,5);});await pause();
    rows=await selected();ok(rows.length===6&&rows[5].subject.id==='doc_plain','native textarea select is captured without mouse or Shift');
    ok(await page.locator('#sel-popover').isHidden(),'plain accessibility-style selection also opens no popup');
    ok(egress.length===0&&unexpected.length===0,'all traffic stays in declared local fixtures with no paid dispatch');
    ok(errors.length===0,'production Work bootstrap and both real editors have no browser errors');
    console.log('CHECKS '+checks+'\nWork selection capture: PASS');
    await context.close();
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
