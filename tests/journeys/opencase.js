// UI-only fixture: deterministic API replies, no source/model requests.
// Producer/backend durability is exercised in the Python integration tests.
const { BASE, ok, launch, pairedContext, finish } = require('./lib');
(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errors = [], starts = [], prepares = [];
  page.on('pageerror', e => { if (!require('./lib').benignPageError(e)) errors.push(e.message); });
  let saved = false, reads = 0, rejectedResult = false, heldAnswer = false, reviewReason = '', checkedPassages = false;
  const origin = {kind:'selection',text:'A preserved passage about a judge.',doc_id:'fixture-document',revision:7,range:{start:0,end:34},title:'Origin fixture'};
  let plan;
  const result = {job_id:'job-fixture',case_id:'case-fixture',status:'partial',actual_cost_usd:0,model_runs:[],
    findings:[{id:'fjc-1',title:'Official appointment record',body:'Fixture biography retained.',source_name:'FJC',source_url:'https://www.fjc.gov/history/judges',epistemic_level:'VERIFIED',raw_data_json:'{"fixture":true}'}],
    sources:[{name:'FJC biography',url:'https://www.fjc.gov/history/judges'},{name:'Unsafe link fixture',url:'javascript:alert(1)'}],
    failures:[{source:'CourtListener',message:'Credential unavailable'}],source_statuses:{fjc:'ok',courtlistener:'credential_failure'}};
  const view = () => ({operation_id:'op_fixture',action_id:'investigate.opencase.question',status:reads++ < 1 ? 'running':'complete',question:plan.question,plan,origin,saved,
    progress:'Public records gathered; source gaps retained',producer_state:{status:reads < 2?'running':'partial',events:[{at:'2026-10-18T12:00:00Z',type:'source',message:'FJC checked'}]},result:reads<2?null:result,
    synthesis:plan.synthesis?.enabled ? {status:'complete',answer:'The saved appointment record establishes the appointment. [op_fixture:fjc-1]',citations:[{record_id:'op_fixture:fjc-1',excerpt:'Fixture biography retained.',title:'Official appointment record',source_name:'FJC',source_url:'https://www.fjc.gov/history/judges'}],usage:{input_tokens:250,output_tokens:80},actual_cost_usd:null} : {status:'not_requested'},
    result_ref:{custody:{deposition_id:'dep_fixture',verification:{ok:true}}},artifacts:[{name:'result.json',sha256:'fixturehash',url:'/api/open-case/operations/op_fixture/artifacts/result.json'}]});
  await page.route('**/api/open-case/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/status')) return route.fulfill({json:{available:true,synthesis:{available:true,provider:'anthropic',model:'fixture-model'}}});
    if (path.endsWith('/save')) {saved=true;return route.fulfill({json:{saved:true}});}
    if (path.endsWith('/answer-review')) {reviewReason=route.request().postDataJSON().reason;return route.fulfill({json:{saved:true}});}
    if (path.endsWith('/operations')) return route.fulfill({json:{operations:plan?[{operation_id:'op_fixture',question:plan.question,status:'complete',saved}]:[]}});
    const v = view();
    if(checkedPassages) Object.assign(v.synthesis,{answer_format:'checked_excerpts',selections:[{record_id:'op_fixture:fjc-1',quote:'Literal [op_fixture:fjc-1] remains source text.'}]});
    v.record_chronology={status:'available',introduction:'Source-attributed fields; separate from the model answer.',limitations:['Record view','Commission and oath are distinct.','Missing termination does not establish present service.'],citations:[],appointments:[{rows:[{field_path:'/court_name',value:'Fixture appeals court'},{field_path:'/commission_date',value:'2021-06-17'},{field_path:'/termination_date',value:'2022-06-29'},{field_path:'/oath_date',value:null}]}]};
    if(reviewReason) {v.synthesis={status:'rejected',answer:'',held_answer:'Original unsupported interpretation',hold_reason:'support_disputed',error:reviewReason,reviews:[{reason:reviewReason}]};v.dimensions={display_status:'Answer held',lifecycle:'complete',acquisition:{status:'ready'},answer:{status:'held'}};}
    if (rejectedResult) { v.status='unknown';v.result=null;v.producer_state.status='completed';v.error='The producer returned a different subject; result not accepted.'; }
    if(heldAnswer) {v.synthesis={status:'truncated',answer:'',hold_reason:'output_limit',error:'Output allowance reached.'};v.dimensions={display_status:'Answer held',lifecycle:'complete',acquisition:{status:'ready'},answer:{status:'held'}};}
    v.costs={estimated_cost_usd:0.130282,known_estimated_subtotal_usd:0.130282,unknown_components:[],entries:[{basis:'provider_usage_rate_card_estimate',usage:[{category:'cache_read_input_tokens',count:0}]}]};v.thread_costs={...v.costs,estimated_cost_usd:0.192304};
    v.synthesis.evidence_relationships={record_count:2,resolved_family_count:1,note:'These cited records share a source family; agreement is not independent corroboration.'};
    if(rejectedResult) v.costs={estimated_cost_usd:null,known_estimated_subtotal_usd:0,unknown_components:[],accounting_status:'unknown'};
    return route.fulfill({json:v});
  });
  await page.route('**/api/actions/prepare', async route => {
    const body = route.request().postDataJSON(); prepares.push(body); plan={...body.inputs,question:body.subject.text,source_scope:['FJC','CourtListener'],outbound_origin:{doc_id:origin.doc_id,revision:7},synthesis:{...body.inputs.synthesis,provider:'anthropic',model:'fixture-model',allowance_usd:0.5,max_estimated_cost_usd:0.363008,cost:'Conservative estimate checked before dispatch; provider billing confirmed separately.'}};
    return route.fulfill({json:{prepared_id:'prep_fixture',inputs:{plan},disclosure:{investigation_plan:plan}}});
  });
  await page.route('**/api/operations', async route => {starts.push(route.request().postDataJSON());return route.fulfill({json:{operation_id:'op_fixture',status:'running'}});});
  await page.addInitScript(o => sessionStorage.setItem('fixture-origin',JSON.stringify(o)),origin);
  await page.goto(BASE+'/investigation?origin_key=fixture-origin');
  await page.waitForSelector('#oc-question');
  await page.fill('#oc-question','What does the appointment record establish?');
  await page.fill('#oc-subject','Fixture Judge');
  await page.click('#oc-prepare');
  await page.waitForSelector('#oc-start');
  ok(starts.length===0,'reviewing the proposal starts no investigation');
  ok(prepares.length===1 && prepares[0].inputs.origin.text===origin.text,'the exact selected passage and revision reach preparation');
  ok(/\$0 paid-model allowance/.test(await page.textContent('#oc-proposal')),'the proposal shows the fixed zero-dollar allowance');
  await page.click('#oc-start');
  await page.waitForFunction(()=>document.querySelector('#oc-current').textContent.includes('Fixture biography retained.'),null,{timeout:12000});
  ok(starts.length===1 && starts[0].prepared_id==='prep_fixture' && !!starts[0].request_key,'Start dispatches the frozen proposal under one request key');
  ok(/Partial result/.test(await page.textContent('#oc-current')) && /Credential unavailable/.test(await page.textContent('#oc-current')),'partial results show source failure beside retained findings');
  ok(/FJC checked/.test(await page.textContent('#oc-current')),'source progress is visible');
  ok(/2022-06-29/.test(await page.textContent('#oc-record-chronology')) && /Not supplied/.test(await page.textContent('#oc-record-chronology')),'record chronology separates known dates from the missing oath');
  ok((await page.locator('#oc-current a[href^="javascript:"]').count())===0,'untrusted source URLs cannot become executable links');
  await page.click('#oc-save');
  await page.waitForFunction(()=>document.querySelector('#oc-save').textContent==='Saved');
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('#oc-current').textContent.includes('Fixture biography retained.'));
  ok(starts.length===1 && /Saved to your investigations/.test(await page.textContent('#oc-current')),'reload reopens saved findings without another Start');
  ok(/preserved passage/.test(await page.textContent('#oc-current')) && /fixturehash/.test(await page.textContent('#oc-current')),'the reopened record retains origin and exact artifact hash');
  await page.getByRole('button',{name:'Ask a follow-up…',exact:true}).click();
  await page.fill('#oc-question','Which source is still missing?'); await page.check('#oc-synthesis'); await page.click('#oc-prepare'); await page.waitForSelector('#oc-start');
  ok(prepares[1].inputs.follow_up_of==='op_fixture' && prepares[1].inputs.origin.doc_id===origin.doc_id,'follow-up preserves its parent and original passage');
  ok(prepares[1].inputs.synthesis.enabled && prepares[1].inputs.synthesis.max_requests===1 && prepares[1].inputs.synthesis.max_output_tokens===4096 && prepares[1].inputs.allowance.paid_models===false,'optional existing-model usage has a separate bounded allowance');
  ok(/Estimate allowance: \$0.50/.test(await page.textContent('#oc-proposal')) && /fixture-model/.test(await page.textContent('#oc-proposal')),'proposal discloses the model and estimate allowance');
  await page.reload(); await page.waitForFunction(()=>document.querySelector('#oc-current').textContent.includes('The saved appointment record establishes'));
  ok(/Cited evidence/.test(await page.textContent('#oc-current')) && /API dollar total: not reported/.test(await page.textContent('#oc-current')) && /input_tokens/.test(await page.textContent('#oc-current')),'saved model answer exposes resolved evidence and usage without claiming a dollar total');
  ok((await page.locator('#oc-current a[href="#oc-citation-1"]').count())===1 && /Fixture biography retained/.test(await page.textContent('#oc-citation-1')),'answer citations link to the saved source excerpt actually supplied to the model');
  ok(starts.length===1,'reopening an optional model answer never sends Start');
  checkedPassages=true;await page.reload();await page.waitForFunction(()=>document.querySelector('#oc-current').textContent.includes('Relevant passages from the saved evidence'));
  ok(/Literal \[op_fixture:fjc-1\] remains source text/.test(await page.textContent('#oc-current')) && (await page.locator('#oc-current a[href="#oc-citation-1"]').count())===1,'checked quotations retain source brackets literally with a separate citation link');
  ok(/2 cited records · 1 resolved source families/.test(await page.textContent('#oc-evidence-relationships')) && /not independent corroboration/.test(await page.textContent('#oc-evidence-relationships')),'literal source selections carry a visible same-family relationship limit');
  checkedPassages=false;
  await page.getByText('Flag an unsupported answer',{exact:true}).click();
  await page.fill('#oc-review-reason','The evidence does not establish the added timing inference.');await page.click('#oc-review-hold');
  await page.waitForFunction(()=>document.querySelector('#oc-progress').textContent==='Answer held');
  await page.reload();await page.waitForSelector('#oc-answer-recovery');
  ok(/Review history/.test(await page.textContent('#oc-current')) && /Original unsupported interpretation/.test(await page.textContent('#oc-current')),'a reviewed hold survives reopen and retains the original answer');
  ok(starts.length===1,'reviewing an unsupported answer creates no paid request');
  reviewReason='';
  heldAnswer=true;await page.reload();await page.waitForSelector('#oc-answer-recovery');
  ok((await page.textContent('#oc-progress'))==='Answer held','held answers do not inherit source completion');
  ok(/about \$0.13 estimated/.test(await page.textContent('#oc-current')) && /about \$0.19 estimated/.test(await page.textContent('#oc-current')),'operation and thread estimates round to cents while including earlier attempts');
  ok(/0.130282/.test(await page.textContent('#oc-current')) && /0.192304/.test(await page.textContent('#oc-current')),'accounting details retain full calculation precision');
  ok(/cache-read tokens: 0 recorded/.test(await page.textContent('#oc-current')) && /provider-billed amount unconfirmed/.test(await page.textContent('#oc-current')),'zero provider cache reads stay visible without a billing or savings claim');
  await page.click('#oc-answer-recovery');await page.waitForSelector('#oc-start');
  ok(prepares.at(-1).inputs.reuse_evidence_from==='op_fixture' && prepares.at(-1).inputs.synthesis.max_output_tokens===8192,'recovery proposes a larger single allowance over the saved evidence');
  ok(starts.length===1,'reviewing recovery sends no paid Start');
  heldAnswer=false;rejectedResult = true;
  await page.reload(); await page.waitForFunction(()=>document.querySelector('#oc-current').textContent.includes('result not accepted'));
  ok((await page.textContent('#oc-progress'))==='unknown','a rejected result cannot inherit the producer’s completed label');
  ok(/This operation: total unknown/.test(await page.textContent('#oc-current')),'unknown accounting is not displayed as zero');
  await page.unroute('**/api/operations');
  await page.route('**/api/operation-costs',route=>route.fulfill({json:{accounting_status:'unknown',estimated_cost_usd:null,
    known_estimated_subtotal_usd:0.192304,unaccounted_operation_ids:['older-unknown'],
    entries:[{basis:'provider_usage_rate_card_estimate',usage:[{category:'cache_read_input_tokens',count:0}]}]}}));
  await page.goto(BASE+'/work');
  await page.waitForFunction(()=>!!window.__work);
  await page.locator('a[data-page="settings"]').click();
  await page.waitForFunction(()=>document.querySelector('#settings-view').textContent.includes('about $0.19 estimated'));
  const settings=await page.textContent('#settings-view');
  ok(/Usage accounting: total unknown · known subtotal about \$0.19 estimated/.test(settings),'Settings uses the same rounding while retaining incomplete total status');
  ok(/cache-read tokens: 0 recorded/.test(settings) && /0.192304/.test(settings),'Settings preserves zero cache reads and precise accounting details');
  ok(errors.length===0,'no page errors: '+JSON.stringify(errors));
  await browser.close(); finish('opencase');
})().catch(e=>{console.error(e);process.exit(1);});
