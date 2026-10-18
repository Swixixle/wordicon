// Offline browser fixture; every request is served by Playwright routing.
const fs=require('fs'),path=require('path');
const lib=require(process.env.JOURNEY_LIB || './lib');
const {BASE,ok,launch,pairedContext,finish,benignPageError}=lib;
const ROOT=path.resolve(__dirname,'../..'),STAGE=process.env.RECEIPTS_STAGE;
const NK=process.env.NK_ROOT || ROOT;
const read=(name)=>fs.readFileSync(STAGE && fs.existsSync(path.join(STAGE,'modified',name)) ? path.join(STAGE,'modified',name) : path.join(ROOT,name));
const projection=JSON.parse(fs.readFileSync(path.join(ROOT,'tests/fixtures/receipts.json')));
(async()=>{
  const browser=await launch(),ctx=await pairedContext(browser),page=await ctx.newPage();
  const errors=[],prepares=[],starts=[];let reads=0;
  page.on('pageerror',e=>{if(!benignPageError(e))errors.push(e.message);});
  const origin={kind:'selection',doc_id:'doc-original',revision:3,text:'The preserved passage.'};
  const plan={question:projection.question,subject_name:'Fixture Judge',subject_type:'federal_judge_district',task_profile:'judicial_biography',jurisdiction:'United States',origin,synthesis:{enabled:false},connector:{connector_id:'fixture'}};
  const result={status:'partial',actual_cost_usd:0,model_runs:[],findings:[{id:'f1',body:'A biography.',title:'Saved biography'}],sources:[],failures:[]};
  const view={operation_id:'op_a',status:'complete',question:plan.question,plan,origin,result,findings:result.findings,events:[],synthesis:{status:'not_requested'},result_ref:{}};
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(!url.href.startsWith(BASE))return route.abort();
    if(name==='/api/open-case/operations/op_a/receipts'){reads++;return route.fulfill({json:projection});}
    if(name==='/api/open-case/operations/op_a')return route.fulfill({json:view});
    if(name==='/api/open-case/operations')return route.fulfill({json:{operations:[view]}});
    if(name==='/api/connectors')return route.fulfill({json:{connectors:[{connector_id:'fixture',producer:'open_case',enabled:true}]}});
    if(name==='/api/open-case/status')return route.fulfill({json:{available:true,synthesis:{available:false}}});
    if(name==='/api/actions/prepare'){const body=route.request().postDataJSON();prepares.push(body);return route.fulfill({json:{prepared_id:'fixture-prepared',inputs:{plan:{...body.inputs,source_scope:[]}}}});}
    if(name==='/api/operations'){starts.push(route.request().postDataJSON());return route.fulfill({json:{operation_id:'unexpected'}});}
    if(name.startsWith('/api/'))return route.fulfill({json:{investigations:[],connectors:[],depositions:[],operations:[]}});
    if(name==='/investigation')return route.fulfill({body:read('webapp/investigation.html'),contentType:'text/html'});
    if(name==='/opencase.js')return route.fulfill({body:read('webapp/opencase.js'),contentType:'application/javascript'});
    if(name==='/receipts.js')return route.fulfill({body:read('webapp/receipts.js'),contentType:'application/javascript'});
    const local=path.resolve(NK,'webapp','.'+name);
    if(local.startsWith(path.resolve(NK,'webapp')+path.sep)&&fs.existsSync(local)&&fs.statSync(local).isFile())return route.fulfill({path:local});
    return route.fulfill({status:404,body:''});
  });
  await page.goto(BASE+'/investigation?operation=op_a');
  await page.waitForSelector('#oc-receipts');
  ok(reads===0,'opening an investigation does not automatically project or start anything');
  await page.getByRole('button',{name:'Build local evidence review',exact:true}).click();
  await page.waitForSelector('#oc-receipts summary');
  ok(reads===1&&starts.length===0&&prepares.length===0,'Receipts reads local saved evidence without preparing or dispatching');
  const panel=page.locator('#oc-receipts');
  ok((await panel.textContent()).includes('2003-01-02 · Court One · commission date')&&(await panel.textContent()).includes('Field comparisons and candidate conflicts · 0'),'typed timeline renders the commission date without inventing a conflict');
  ok((await panel.locator('img').count())===0,'source markup is rendered as text');
  ok((await panel.textContent()).includes('Citation structure only; factual support remains unassessed.'),'citation usage is explicitly structural');
  ok((await panel.textContent()).includes('setup required')&&(await panel.textContent()).includes('No source or model requests'),'access blockers and local-only behavior are visible');
  await panel.getByText('Targeted continuation suggestions · 2',{exact:true}).click();
  await panel.getByRole('button',{name:'Use as follow-up question'}).first().click();
  ok((await page.inputValue('#oc-question')).includes('oath date')&&prepares.length===0&&starts.length===0,'selecting a gap only fills the question');
  await page.click('#oc-prepare');await page.waitForSelector('#oc-start');
  ok(prepares.length===1&&prepares[0].inputs.follow_up_of==='op_a'&&prepares[0].inputs.origin.doc_id===origin.doc_id,'reviewed follow-up retains parent and original passage');
  ok(prepares[0].inputs.receipts_continuation.projection_sha256===projection.projection_sha256,'continuation carries the exact displayed projection identity for server revalidation');
  ok(starts.length===0,'proposal review never dispatches Start');
  await page.reload();await page.waitForSelector('#oc-receipts');await page.getByRole('button',{name:'Build local evidence review',exact:true}).click();await page.waitForSelector('#oc-receipts summary');
  ok(reads===2&&starts.length===0,'reopening rebuilds the saved view without a new investigation');
  ok(errors.length===0,'no page errors: '+JSON.stringify(errors));
  await browser.close();finish('receipts');
})().catch(e=>{console.error(e);process.exit(1);});
