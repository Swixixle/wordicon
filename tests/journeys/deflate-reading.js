// Offline actual-page fixture: all requests are intercepted at the scratch origin.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const FILES=path.resolve(__dirname,'../..');
const MAIN=fs.existsSync(path.join(FILES,'scripts/federation.py'))?FILES:path.resolve(FILES,'../../nikodemus');
const lib=require(path.join(MAIN,'tests/journeys/lib'));
const {BASE,OUT,ok,pairedContext,finish,benignPageError}=lib;
const playwright=require('playwright');
const ENGINE=process.env.JOURNEY_ENGINE==='webkit'?'webkit':'chromium';
const NAME='deflate-reading-'+ENGINE;
const read=n=>fs.readFileSync(fs.existsSync(path.join(FILES,n))?path.join(FILES,n):path.join(MAIN,n));
(async()=>{
 const browser=await playwright[ENGINE].launch(),context=await pairedContext(browser),page=await context.newPage();
 ok(browser.browserType().name() === ENGINE,'Deflate reading is measured in '+ENGINE);
 const errors=[],prepares=[],deeperPrepares=[],deeperStarts=[],starts=[],uploads=[],mutations=[];let costMissing=false,currentPinRemoved=false;let saved=false,accepted=false,loseFirst=true;
 const origin={kind:'operation',operation_id:'op_open_case_parent',title:'Original appointment investigation',question:'What additional source can help?',parent_origin:{kind:'selection',doc_id:'doc_original',revision:2,text:'Original captured passage'}};
 await context.addInitScript(value=>{if(!sessionStorage.getItem('fixture-origin'))sessionStorage.setItem('fixture-origin',JSON.stringify(value));},origin);
 page.on('pageerror',e=>{if(!benignPageError(e))errors.push(e.message);});
 const safeProse='The passage reports a meeting. This is a model reading, not independent proof.';
 const unsafe='<img src=x onerror="window.BAD_MARKUP=true"> Source text remains literal.';
 const sourceHash=crypto.createHash('sha256').update(unsafe).digest('hex');
 const fixtureAudio=Buffer.from('ID3controlled-fixture-audio');
 const original=Buffer.from('ID3retained-original-fixture'),originalHash=crypto.createHash('sha256').update(original).digest('hex');
 const view=()=>({operation_id:'op_deflate_fixture',action_id:'investigate.deflate.read',status:'complete',progress:'Partial reading saved. Review held passages.',question:'What does this source establish?',saved,created_at:'2026-10-18T12:00:00Z',
  plan:{question:'What does this source establish?',origin,reading_enabled:true,producer_plan:{context:{title:'Fixture source'}},input:{url:'https://source.example/article'}},
  origin,follow_up_of:origin.operation_id,events:[{kind:'note',detail:{source:'saved'}}],
  costs:costMissing?{accounting_status:'unknown',estimated_cost_usd:null}:{entries:[{basis:'provider_usage_rate_card_estimate',usage_complete:true,usage:[{category:'cache_read_input_tokens',count:0}]}],accounting_status:'partial',estimated_cost_usd:.0012,known_estimated_subtotal_usd:.0012,actual_cost_usd:null,unknown_components:['model_002']},
  thread_costs:{accounting_status:'unknown',estimated_cost_usd:null,known_estimated_subtotal_usd:.0012},
  result:{acquisition:{status:'done'},reading:{status:'partial'}},deposition_id:'dep_fixture',
  deposition:{gaps:[{kind:'source_audio_not_retained',detail:'Producer deleted temporary audio; chosen original stays in Nikodemus.'}],payload:{transcript:{included:true,text:unsafe,sha256:sourceHash},claims:{run:{title:'A captured source',transcript:{sha256:sourceHash},source:{url:'https://source.example/article',label:'Original public article'},sourceIdentity:{state:'needs_confirmation'},attributionGate:{status:'ready'}},
   passages:[{id:'ready',title:'Ready attributed reading',model:'fixture model',readingGate:{status:'ready'},basedOn:{inputHash:sourceHash},stale:[],reading:{deflated:{hs:safeProse},supports:{hs:'<script>window.BAD_MARKUP=true</script> Literal model prose.'}},quotes:[{quote:'The passage reports a meeting.',verbatim:true}]},
    {id:'basis_missing',title:'Missing source basis',readingGate:{status:'ready'},stale:[],reading:{deflated:{hs:'MISSING_BASIS_PROSE_MUST_NOT_SHOW'}}},
    {id:'basis_other',title:'Another source basis',readingGate:{status:'ready'},basedOn:{inputHash:'f'.repeat(64)},stale:[],reading:{deflated:{hs:'OTHER_BASIS_PROSE_MUST_NOT_SHOW'}}},
    {id:'duplicate_held',title:'Ready label with held record',readingGate:{status:'ready'},basedOn:{inputHash:sourceHash},stale:[],reading:{deflated:{hs:'DUPLICATE_HELD_PROSE_MUST_NOT_SHOW'}}},
    {id:'ambiguous',title:'Duplicate identity first record',readingGate:{status:'ready'},basedOn:{inputHash:sourceHash},stale:[],reading:{deflated:{hs:'DUPLICATE_ID_FIRST_PROSE'}}},
    {id:'ambiguous',title:'Duplicate identity second record',readingGate:{status:'ready'},basedOn:{inputHash:sourceHash},stale:[],reading:{deflated:{hs:'DUPLICATE_ID_SECOND_PROSE'}}},
    {id:'partial_fields',title:'Partial reading fields',readingGate:{status:'ready'},basedOn:{inputHash:sourceHash},stale:[],reading:{supports:{hs:'A retained secondary reading field.'}}},
    {id:'stale',title:'Stale must not render',readingGate:{status:'ready'},stale:['input changed'],reading:{deflated:{hs:'STALE_PROSE_MUST_NOT_SHOW'}}},
    {id:'held',title:'Held must not render',readingGate:{status:'held'},reading:{deflated:{hs:'HELD_PROSE_MUST_NOT_SHOW'}}}],
   passagesHeld:[{id:'held',title:'Held source reading',reasons:['Quotation could not be matched.'],source:'Held source words.',attempts:[{draft:'HELD_DRAFT_ONLY_IN_INSPECTION'}]},{id:'duplicate_held',title:'Same passage remains held',reasons:['A hold remains in this signed export.']}],
   claims:[{passageId:'ready',text:'A meeting occurred.',displayType:'Checkable claim',wouldSettle:'Inspect the original meeting record.'}]}}},
  artifacts:[{name:'producer-deposition.json',sha256:'b'.repeat(64),url:'/api/deflate/operations/op_deflate_fixture/artifacts/producer-deposition.json'},{name:'producer-model_001.request.json',sha256:'c'.repeat(64),url:'/api/deflate/operations/op_deflate_fixture/artifacts/producer-model_001.request.json'}]});
 const uploadView=()=>{const v=view();v.operation_id='op_upload_fixture';v.plan.input={kind:'upload',name:'retained.mp3'};v.original_upload={name:'retained.mp3',bytes:original.length,sha256:originalHash,media_type:'audio/mpeg',url:'/api/deflate/operations/op_upload_fixture/original'};v.deposition.payload.claims.passages.push({id:'legacy',title:'Earlier metadata only',readingGate:{status:'ready'},basedOn:{inputHash:sourceHash},stale:[],reading:{by:'model',model:'fixture',contract:'reading-2'}});return v;};
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),p=url.pathname;
  if(url.origin!==new URL(BASE).origin)return route.abort();
  if(request.method()==='POST')mutations.push(p);
  if(p==='/api/deflate/status')return route.fulfill({json:{available:true}});
  if(p==='/api/ledger/config')return route.fulfill({json:{enabled:false}});
  if(p==='/api/deflate/operations')return route.fulfill({json:{operations:accepted?[view()]:[]}});
  if(p==='/api/deflate/operations/op_deflate_fixture/save'){saved=true;return route.fulfill({json:view()});}
  if(p==='/api/deflate/operations/op_deflate_fixture'){const v=view();if(currentPinRemoved){v.deposition=null;v.current_verification={ok:false};v.error='Current pinned-key verification is unavailable. Original signed bytes remain saved.';}return route.fulfill({json:v});}
  if(p==='/api/deflate/operations/op_upload_fixture')return route.fulfill({json:uploadView()});
  if(p==='/api/deflate/operations/op_upload_fixture/original')return route.fulfill({body:original,contentType:'audio/mpeg',headers:{'Content-Disposition':'attachment; filename="retained.mp3"','X-Content-SHA256':originalHash}});
  // WebKit omits a File request body from Playwright's route inspector. The
  // mocked descriptor is fixed fixture data; exact transport custody is covered
  // by authenticated backend tests, not claimed from this route interception.
  if(p==='/api/deflate/uploads'){uploads.push({name:url.searchParams.get('name'),bytes:request.postDataBuffer()?.length});return route.fulfill({json:{upload:{upload_id:'upload_fixture',name:url.searchParams.get('name'),bytes:request.postDataBuffer()?.length ?? fixtureAudio.length}}});}
  if(p==='/api/actions/prepare'){const data=request.postDataJSON();if(data.action_id==='explore.deepen'){deeperPrepares.push(data);return route.fulfill({json:{prepared_id:'prep_deeper_'+deeperPrepares.length,disclosure:{available:true,reason:'Offline fixture; all requests are intercepted.',exploration:{root:{deposition_id:data.subject.deposition_id},question:'Inspect this retained reading'},lane:{external:false}}}});}prepares.push(data);return route.fulfill({json:{prepared_id:'prep_'+prepares.length,inputs:{plan:{...data.inputs,ready:true,input:data.inputs.upload_id?{name:'fixture.mp3'}:{url:data.inputs.url},cost:data.inputs.reading_enabled?'Up to $0.50 in estimated model usage.':'No paid model reading.',retention:'Exact source and attempts remain local.',limitations:['Interpretations are not independently established facts.'],producer_plan:{model:data.inputs.reading_enabled?{provider:'anthropic',model:'fixture model'}:null}}}}});}
  if(p==='/api/operations'){const data=request.postDataJSON();if(data.prepared_id.startsWith('prep_deeper_')){deeperStarts.push(data);return route.abort('connectionfailed');}starts.push(data);accepted=true;if(loseFirst){loseFirst=false;return route.abort('connectionfailed');}return route.fulfill({json:{operation_id:'op_deflate_fixture'}});}
  if(p.startsWith('/api/'))return route.fulfill({json:{available:true,enabled:false,operations:[],actions:[],depositions:[]}});
  if(p==='/deflate-reading')return route.fulfill({body:read('webapp/deflate-reading.html'),contentType:'text/html'});
  for(const root of [FILES,MAIN]){const web=path.resolve(root,'webapp'),target=path.resolve(web,'.'+p);if(target.startsWith(web+path.sep)&&fs.existsSync(target)&&fs.statSync(target).isFile())return route.fulfill({path:target,contentType:p.endsWith('.js')?'application/javascript':undefined});}
  return route.fulfill({status:404,body:''});
 });
 await page.goto(BASE+'/deflate-reading?origin_key=fixture-origin');await page.waitForFunction(()=>document.getElementById('dr-readiness').textContent.includes('connected'));
 ok(!await page.locator('#dr-reading').isChecked(),'optional model reading defaults off');
 ok(await page.inputValue('#dr-budget')==='0.50'&&!await page.locator('#dr-budget-box').isVisible(),'editable default allowance is $0.50 and hidden when reading is off');
 ok(await page.locator('#dr-title').getAttribute('maxlength')==='200'&&await page.locator('#dr-reading').evaluate(e=>e.getBoundingClientRect().width<30),'source title matches backend limit and model checkbox remains aligned with its label');
 ok((await page.locator('#dr-origin').textContent()).includes('Original appointment investigation'),'originating investigation is visible before proposal');
 await page.fill('#dr-url','https://source.example/article');await page.fill('#dr-question','What does this source establish?');await page.click('#dr-prepare');await page.waitForSelector('#dr-start');
 ok(prepares.length===1&&starts.length===0&&uploads.length===0,'URL proposal review starts no acquisition, upload, or operation');
 ok(prepares[0].inputs.origin.operation_id===origin.operation_id&&prepares[0].inputs.origin.parent_origin.revision===2,'proposal retains explicit originating operation and revision');
 ok(prepares[0].inputs.reading_enabled===false,'model-off choice reaches the proposal unchanged');
 await page.getByRole('button',{name:'Revise',exact:true}).click();await page.check('#dr-reading');await page.click('#dr-prepare');await page.waitForSelector('#dr-start');
 ok(prepares.length===2&&prepares[1].inputs.reading_enabled===true&&prepares[1].inputs.allowance_usd===.5,'optional model reading sends the explicitly selected cumulative allowance');
 await page.click('#dr-start');await page.waitForFunction(()=>document.getElementById('dr-start')?.textContent==='Check this Start request');
 ok(starts.length===1,'a lost Start reply does not automatically resubmit');
 const first=starts[0];await page.reload();await page.waitForFunction(()=>document.getElementById('dr-start')?.textContent==='Check this Start request');
 ok(starts.length===1,'reload restores pending Start without any automatic POST');
 await page.click('#dr-start');await page.waitForSelector('#dr-transcript');
 ok(starts.length===2&&JSON.stringify(starts[1])===JSON.stringify(first),'explicit check reuses the exact original Nikodemus request identity');
 ok((await page.locator('#dr-transcript pre').textContent())===unsafe,'retained source text is rendered literally');
 ok(await page.locator('#dr-current img,#dr-current script').count()===0&&!await page.evaluate(()=>window.BAD_MARKUP),'source/model markup never becomes executable DOM');
 ok((await page.locator('#dr-current').innerText()).includes(safeProse),'ready model prose is visible with attribution');
 const current=await page.locator('#dr-current').innerText();
 ok(!current.includes('HELD_PROSE_MUST_NOT_SHOW')&&!current.includes('STALE_PROSE_MUST_NOT_SHOW'),'held and stale model prose is excluded from the ordinary reading');
 ok(!current.includes('MISSING_BASIS_PROSE_MUST_NOT_SHOW')&&!current.includes('OTHER_BASIS_PROSE_MUST_NOT_SHOW')&&current.includes('does not identify the saved source text'),'missing and mismatched source basis withhold prose with an inspection notice');
 ok(!current.includes('DUPLICATE_HELD_PROSE_MUST_NOT_SHOW')&&current.includes('also listed as held'),'a ready label cannot override the same passage in held records');
 ok((await page.locator('#dr-current').textContent()).includes('MISSING_BASIS_PROSE_MUST_NOT_SHOW'),'withheld source-basis record remains intact inside closed inspection details');
 ok(!current.includes('DUPLICATE_ID_FIRST_PROSE')&&!current.includes('DUPLICATE_ID_SECOND_PROSE')&&current.includes('identity occurs more than once'),'duplicate passage identities stay inspectable without current prose');
 ok(current.includes('A retained secondary reading field.')&&current.includes('no primary reading. Go deeper is unavailable'),'secondary reading fields remain visible without promoting an absent primary reading');
 ok(current.includes('Quotation could not be matched.'),'held source reason remains visible');
 ok(current.includes('total unknown')&&current.includes('less than $0.01 estimated'),'known estimated subtotal never hides incomplete accounting');
 ok(current.includes('Provider cache-read tokens: 0 recorded')&&current.includes('Local source reuse is separate'),'provider cache-read zero is explicit and distinct from source reuse');
 ok(current.includes('needs_confirmation')||current.includes('needs confirmation'),'source identity uncertainty is visible');
 ok(await page.getByRole('button',{name:'↓ Go deeper',exact:true}).count()===1,'native Go deeper is offered only on the ready passage');
 const startsBeforeDeeper=starts.length;await page.getByRole('button',{name:'↓ Go deeper',exact:true}).click();await page.waitForSelector('.deeper-proposal');
 ok(deeperPrepares.length===1&&deeperPrepares[0].subject.source_operation_id==='op_deflate_fixture'&&deeperPrepares[0].subject.deposition_id==='dep_fixture'&&deeperPrepares[0].subject.item_ref==='deflate:passage:ready','Go deeper proposal carries the explicit source operation and exact retained item');
 ok(starts.length===startsBeforeDeeper,'reviewing linked Go deeper prepares only and never starts a model call');
 await page.locator('.deeper-proposal').getByRole('button',{name:'Cancel',exact:true}).click();
 ok(new URL(await page.getByRole('link',{name:'History and capture',exact:true}).getAttribute('href'),BASE).pathname+new URL(await page.getByRole('link',{name:'History and capture',exact:true}).getAttribute('href'),BASE).search==='/capture-history?operation_id=op_deflate_fixture','reading links to the shared operation history');
 await page.click('#dr-save');await page.waitForFunction(()=>document.getElementById('dr-save')?.textContent==='Saved');
 ok(saved&&(await page.locator('#dr-current').innerText()).includes('Saved to your sources and readings.'),'explicit Save is acknowledged');
 const mutationCount=mutations.length;await page.reload();await page.waitForSelector('#dr-transcript');
 ok(mutations.length===mutationCount&&starts.length===2,'reopen reads saved results with no Start, import, or other mutation');
 await page.screenshot({path:path.join(OUT,'deflate-saved-reading-'+ENGINE+'.png'),fullPage:true});
 costMissing=true;await page.reload();await page.waitForSelector('#dr-transcript');
 const visibleCost=await page.locator('#dr-current > p').allTextContents();
 ok(visibleCost.some(t=>t.includes('This operation: total unknown')&&t.includes('estimate unavailable'))&&!visibleCost.some(t=>t.includes('This operation:')&&t.includes('$0.00')),'missing known subtotal stays unavailable rather than becoming zero');
 costMissing=false;currentPinRemoved=true;await page.reload();await page.waitForFunction(()=>document.getElementById('dr-current').textContent.includes('Current pinned-key verification'));
 ok(await page.locator('#dr-transcript').count()===0&&await page.getByRole('button',{name:'↓ Go deeper',exact:true}).count()===0,'a removed current pin withholds ordinary source prose and Go deeper');
 ok(await page.locator('#dr-current a[href*="artifacts"]').count()===2,'current verification hold preserves original artifact inspection links');
 currentPinRemoved=false;await page.reload();await page.waitForSelector('#dr-transcript');
 await page.getByRole('button',{name:'Add another source',exact:true}).click();await page.locator('#dr-file').setInputFiles({name:'fixture.mp3',mimeType:'audio/mpeg',buffer:fixtureAudio});
 await page.click('#dr-prepare');await page.waitForSelector('#dr-start');
 ok(uploads.length===1&&uploads[0].name==='fixture.mp3'&&starts.length===2,'upload proposal retains chosen bytes locally without starting Deflate');
 ok(prepares.at(-1).inputs.upload_id==='upload_fixture'&&!prepares.at(-1).inputs.url,'upload proposal carries the local retained upload identity');
 ok(prepares.at(-1).inputs.origin.operation_id==='op_deflate_fixture','additional source proposal follows the explicit saved Deflate operation');
 ok((await page.locator('#dr-upload').innerText()).includes('only after Start'),'upload timing and local custody are disclosed');
 const beforeOriginal=mutations.length;await page.goto(BASE+'/deflate-reading?operation=op_upload_fixture');await page.waitForSelector('#dr-transcript');
 const downloadLink=page.getByRole('link',{name:'Download original recording · retained.mp3',exact:true});
 ok(new URL(await downloadLink.getAttribute('href'),BASE).pathname==='/api/deflate/operations/op_upload_fixture/original'&&(await page.locator('#dr-current').innerText()).includes(originalHash),'original recording has an operation-bound download link and visible exact hash');
 let received;
 if(ENGINE==='chromium'){
  const pendingDownload=page.waitForEvent('download');await downloadLink.click();const download=await pendingDownload;
  received=fs.readFileSync(await download.path());
  ok(received.equals(original)&&crypto.createHash('sha256').update(received).digest('hex')===originalHash,'original download preserves exact fixture media bytes');
 }else{
  // The installed WebKit does not emit download for this routed attachment.
  // Inspect its same-origin response bytes instead; this does not claim native
  // WebKit download UI acceptance (the Chromium assertion remains unchanged).
  received=Buffer.from(await page.evaluate(async url=>Array.from(new Uint8Array(await (await fetch(url)).arrayBuffer())),await downloadLink.getAttribute('href')));
  ok(received.equals(original)&&crypto.createHash('sha256').update(received).digest('hex')===originalHash,'WebKit original-response bytes match exactly; native download UI is not asserted');
 }
 ok(await page.getByRole('button',{name:'↓ Go deeper',exact:true}).count()===1&&(await page.locator('#dr-current').innerText()).includes('metadata'),'legacy ready metadata without prose does not expose a new Go deeper reading');
 ok(mutations.length===beforeOriginal,'reopening and downloading a retained original make only read requests');
 // The same signed item may be retained by distinct source operations. A lost
 // Start must remain bound to the originating operation, not migrate by item ID.
 await page.goto(BASE+'/deflate-reading?operation=op_deflate_fixture');await page.waitForSelector('#dr-transcript');
 await page.getByRole('button',{name:'↓ Go deeper',exact:true}).click();await page.waitForSelector('.deeper-proposal');
 await page.locator('.deeper-proposal').getByRole('button',{name:'Start',exact:true}).click();
 await page.getByRole('button',{name:'Check Start again',exact:true}).waitFor();
 const pendingDeeper={...deeperStarts[0]},beforeOtherPrepare=deeperPrepares.length;
 await page.goto(BASE+'/deflate-reading?operation=op_upload_fixture');await page.waitForSelector('#dr-transcript');
 await page.getByRole('button',{name:'↓ Go deeper',exact:true}).click();await page.waitForSelector('.deeper-proposal');
 ok(deeperPrepares.length===beforeOtherPrepare+1&&deeperPrepares.at(-1).subject.source_operation_id==='op_upload_fixture'&&deeperStarts.length===1,'another source operation never inherits an uncertain Start for the same signed item');
 await page.locator('.deeper-proposal').getByRole('button',{name:'Cancel',exact:true}).click();
 const beforeReturn=deeperPrepares.length;
 await page.goto(BASE+'/deflate-reading?operation=op_deflate_fixture');await page.waitForSelector('#dr-transcript');
 await page.getByRole('button',{name:'↓ Go deeper',exact:true}).click();await page.getByRole('button',{name:'Check Start again',exact:true}).waitFor();
 ok(deeperPrepares.length===beforeReturn&&deeperStarts.length===1,'returning to the original source restores its pending proposal without preparation or Start');
 await page.getByRole('button',{name:'Check Start again',exact:true}).click();await page.getByRole('button',{name:'Check Start again',exact:true}).waitFor();
 ok(deeperStarts.length===2&&JSON.stringify(deeperStarts[1])===JSON.stringify(pendingDeeper),'explicit Go deeper recovery retains the same original source-bound request identity');
 await page.locator('.deeper-proposal').getByRole('button',{name:'Close',exact:true}).click();
 await require('./deflate-lifecycle')(page,{BASE,ok,view,setSaved:value=>{saved=value;}});
 ok(errors.length===0,'no page errors: '+JSON.stringify(errors));
 await browser.close();finish(NAME);
})().catch(e=>{console.error(e);process.exit(1);});
