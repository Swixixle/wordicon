// Real reconstruction page; all traffic is fulfilled locally and never posted.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8499';
let checks=0;const ok=(value,label)=>{assert.ok(value,label);checks++;console.log('ok '+label);};
const empty={documents:[],revisions:[],snapshots:[],proposals:[],operations:[],attempts:[],artifacts:[],evidence:[],answers:[],attention:[],source_checks:[]};
const prepared={schema:'nikodemus.capture_history.v1',root:{kind:'document',id:'doc_fixture'},workspace:{workspace_id:'workspace_fixture'},
  nodes:{...empty,documents:[{id:'doc_fixture',doc_id:'doc_fixture',title:'Fixture document',revision:2,url:'/work?doc=doc_fixture'}],
    revisions:[{id:'revision:doc_fixture:2',revision:2,status:'retained',chars:149,url:'/api/notebook/documents/doc_fixture/revisions/2'}],
    snapshots:[{id:'snap_fixture',kind:'selection',chars:69,range:{start:80,end:149,units:'codepoint'},verification:'verified',committed_revision_match:true,url:'/api/snapshots/snap_fixture'}],
    proposals:[{id:'prep_fixture',prepared_id:'prep_fixture',action_id:'analyze.decompose',status:'prepared'}]},links:[],gaps:[],capture_gaps:{gaps:[],read_gaps:[]},
  projection_sha256:'a'.repeat(64),scope:'Explicit saved references',limits:{operations:100},side_effects:{writes:0,network:0,models:0},limitations:[]};
const operation=structuredClone(prepared);operation.root={kind:'operation',id:'op_fixture'};
operation.nodes.operations=[{id:'op_fixture',operation_id:'op_fixture',question:'What does the saved record establish?',status:'complete',url:'/investigation?operation=op_fixture',costs:{accounting_status:'unknown'}}];
operation.nodes.operations.push({id:'op_partial',operation_id:'op_partial',question:'Partial usage fixture',status:'complete',costs:{accounting_status:'unknown',estimated_cost_usd:null,known_estimated_subtotal_usd:0.004,unknown_components:['gateway:attempt_tool']}});
operation.nodes.attempts=[{id:'event:op_fixture:2',kind:'attempt_end',outcome:'error',stage:'source_read',detail:{message:'Source timed out',attempt_id:'attempt_fixture'}}];
operation.nodes.artifacts=[{id:'artifact:op_fixture:result.json',operation_id:'op_fixture',name:'result.json',sha256:'b'.repeat(64),verification:'verified',url:'/api/capture/operations/op_fixture/artifacts/result.json'}];
operation.nodes.evidence=[{id:'op_fixture:source1',title:'<img src=x onerror="window.unsafe=1">',evidence_kind:'official_primary_record',source_url:'javascript:window.unsafe=1',artifact_id:'artifact:op_fixture:result.json'}];
operation.nodes.source_checks=[{id:'source-check',kind:'failures',source:'Optional source',status:'network_failure',reason:'The saved source check timed out.'},
  {id:'source-cap',kind:'declared_source_capability',source:'Unimplemented adapter',role:'unimplemented',attempt_inferred:false}];
operation.nodes.answers=[{id:'answer:op_fixture',operation_id:'op_fixture',current_status:'held',recorded_status:'complete',reviews:[{reason:'The cited record does not establish the inference.'}],source_refs:[],display_url:'/investigation?operation=op_fixture',interpretation_support:'not_independently_verified'}];
operation.nodes.attention=[{id:'attention:old:1',type:'document_opened',identity_status:'legacy_unverifiable'}];
operation.nodes.attention.push({id:'attention:interval:1',type:'activity_interval',identity_status:'explicit_event_id',interval:{state:'foreground_idle_estimate',duration_ms:12000}});
operation.gaps=[{kind:'artifact_integrity',record_id:'old-response',reason:'The recorded response bytes are unavailable.'}];
operation.links=[{from:'prep_fixture',to:'op_fixture',relation:'started_from',basis:'operation.prepared_id'},
  {from:'op_fixture',to:'op_followup',relation:'follow_up',basis:'plan.follow_up_of'}];
(async()=>{
  const browser=await chromium.launch();
  try {
    const context=await browser.newContext(),requests=[],outbound=[],errors=[];
    await context.route('**/*',async route=>{const r=route.request(),u=new URL(r.url());requests.push({path:u.pathname,method:r.method()});
      if(u.origin!==base){outbound.push(u.href);return route.abort();}
      if(u.pathname==='/capture-history')return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(root,'webapp/capture-history.html'),'utf8')});
      if(u.pathname==='/capture-history.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'webapp/capture-history.js'),'utf8')});
      if(u.pathname==='/api/capture/history')return u.searchParams.get('operation_id')==='unpaired'?route.fulfill({status:401,json:{error:'Pair first'}}):route.fulfill({json:u.searchParams.has('doc_id')?prepared:operation});
      return route.fulfill({status:404,body:'Fixture route unavailable'});
    });
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/capture-history?doc_id=doc_fixture');await page.waitForSelector('#history-proposals');
    ok(await page.getByText('Prepared only · no Start is linked to this proposal.',{exact:true}).count()===1,'unstarted proposal is visibly distinct from a request');
    ok(await page.getByText('The captured text exactly matches its saved revision and range.',{exact:true}).count()===1,'exact revision/range verification is readable');
    ok(await page.getByRole('link',{name:'Read the original captured input'}).getAttribute('href')===base+'/api/snapshots/snap_fixture','captured input links to authenticated local record');
    ok(await page.getByRole('link',{name:'Read this exact retained revision'}).getAttribute('href')===base+'/api/notebook/documents/doc_fixture/revisions/2','revision link preserves its explicit identity');
    ok(await page.getByRole('button',{name:/Start/}).count()===0,'reconstruction offers no dispatch button');
    const before=requests.filter(r=>r.path==='/api/capture/history').length;
    await page.click('#history-refresh');await page.waitForFunction(()=>!document.querySelector('#history-refresh').disabled);
    ok(requests.filter(r=>r.path==='/api/capture/history').length===before+1,'refresh reads the saved projection once');
    await page.goto(base+'/capture-history?operation_id=op_fixture');await page.waitForSelector('#history-answers');
    ok(await page.locator('#history-gaps').innerText().then(t=>t.includes('recorded response bytes are unavailable')),'capture gaps remain visible at the top');
    ok(await page.locator('#history-questions').innerText().then(t=>t.includes('Cost is unknown or incomplete')),'missing accounting is not displayed as free');
    ok(await page.locator('#history-questions').innerText().then(t=>t.includes('Known estimated subtotal: $0.004000. Accounting is incomplete; unknown components are not counted as free.')),'known usage subtotal preserves visibly incomplete accounting');
    ok(await page.locator('#history-attempts').innerText().then(t=>t.includes('Source timed out')),'failed source attempt remains readable');
    ok(await page.locator('#history-answers').innerText().then(t=>t.includes('held')&&t.includes('does not establish the inference')),'held answer remains distinct from completed operation lifecycle');
    ok(await page.locator('#history-sources img').count()===0&&!(await page.evaluate(()=>window.unsafe)),'source titles are text, never executable HTML');
    ok(await page.locator('a[href^="javascript:"]').count()===0,'unsafe source URL never becomes a link');
    ok(await page.locator('#history-sources').innerText().then(t=>t.includes('not a recorded attempt')),'unimplemented capability is not fabricated into an attempt');
    ok(await page.locator('#history-followups a').count()===2,'explicit followup relation has both preserved endpoint links');
    ok(await page.locator('#history-attention').innerText().then(t=>t.includes('without a stable event ID')),'legacy activity does not acquire an invented identity');
    ok(await page.locator('#history-attention').innerText().then(t=>t.includes('foreground idle estimate: 12.0 seconds (12000 ms)')&&t.includes('does not establish reading or attention')),'duration estimate has readable state, amount and uncertainty');
    await page.goto(base+'/capture-history?operation_id=unpaired');await page.getByText('This history is private to a paired browser.',{exact:true}).waitFor();
    ok(await page.getByRole('link',{name:'Open pairing'}).count()===1,'unpaired reader is directed to pairing without records');
    ok(requests.every(r=>r.method==='GET')&&outbound.length===0,'all fixture traffic is local GET only');
    ok(errors.length===0,'real page and module report no browser errors');
    console.log('CHECKS '+checks+'\nCapture history browser fixture: PASS');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
