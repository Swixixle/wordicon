// Focused exploration, on an isolated fixture server with JOURNEY_MOCK_LANE=1.
const fs = require('fs');
const path = require('path');
const {BASE, DIR, OUT, ok, launch, pairedContext, finish} = require('./lib');
const root = 'trace_deeper_journey_root';
const state = process.env.JOURNEY_STATE || path.join(DIR, 'state');
const source = {trace_id:root, mode:'sprout', created_at:new Date().toISOString(),
  source:{title:'A fixture seed'}, input_text:'Go deeper navigation fixture',
  threads:[{anchor_name:'Augustine’s excavation of memory', culture_or_work:'Augustine, Confessions, Book X',
    reading:'A fixture selection for checking focused navigation.', parallel:'A navigation fixture.',
    locator:'Book X, chapters 8–17', review_verdict:'strained', review_note:'Fixture: this rating is about the analogy.',
    quote_status:'paraphrase'}], doors:[], citations:[], trail:[], summary:'Go deeper navigation fixture'};
fs.mkdirSync(path.join(state, 'results'), {recursive:true});
fs.writeFileSync(path.join(state, 'results', root+'.json'), JSON.stringify(source));

(async () => {
  const browser = await launch();
  const ctx = await pairedContext(browser);
  const page = await ctx.newPage();
  const errors = [], starts = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('request', r => {if(r.method()==='POST' && new URL(r.url()).pathname==='/api/operations') starts.push(r.postDataJSON());});
  await page.goto(BASE+'/?trace='+root);
  await page.waitForSelector('[data-deeper-action="open"]');
  await page.evaluate(() => {document.getElementById('compose-text').value='The draft remains mine.';});
  ok(starts.length===0, 'opening a saved thread starts no model operation');
  await page.click('[data-deeper-action="open"]');
  await page.waitForSelector('.deeper-proposal');
  const proposal = await page.textContent('.deeper-proposal');
  ok(proposal.includes('Augustine') && proposal.includes('Confessions'), 'the proposal names the exact selected work');
  ok(proposal.includes('mock') && proposal.includes('Cost:'), 'the proposal states the actual lane and cost disclosure');
  ok(proposal.includes('original analogy') && proposal.includes('strained'), 'strained is retained as a judgment of the original analogy');
  ok(starts.length===0, 'preparing a focused exploration starts nothing');
  await page.keyboard.press('Escape');
  ok(await page.locator('.deeper-proposal').count()===0 && starts.length===0, 'Escape cancels without a Start');
  await page.click('[data-deeper-action="open"]');
  await page.waitForSelector('[data-deeper-action="start"]');
  await page.evaluate(() => {const b=document.querySelector('[data-deeper-action="start"]'); b.click(); b.click();});
  await page.waitForSelector('.deeper-result', {timeout:20000});
  ok(starts.length===1, 'two quick Start clicks create one operation');
  const resultText = await page.textContent('.deeper-result');
  ok(resultText.includes('MOCK FIXTURE') && resultText.includes('no live model call'), 'fixture results remain conspicuously fixtures');
  ok(resultText.includes('Into the work itself') && resultText.includes('Stay with this subject'), 'the answer offers source guidance and progressive next questions');
  const first = (await (await page.request.get(BASE+'/api/operations')).json()).operations.find(x=>x.prepared_id===starts[0].prepared_id);
  const firstResult = await (await page.request.get(BASE+'/api/result/'+first.trace_id)).json();
  const history = await (await page.request.get(BASE+'/api/history')).json();
  ok(history.items.some(x=>x.trace_id===first.trace_id && x.operation==='deepen' && x.subject_key===root+':0'), 'a focused reading appears in Recent with exact subject identity, without inventing a candidate concept');
  ok(firstResult.context.root.trace_id===root && firstResult.context.root.thread_index===0, 'the saved result retains exact root identity');
  ok(firstResult.raw_response && firstResult.prompt_identities.length===1, 'raw response and prompt identity are available for later analysis');
  const custom='How does the argument change within this work?';
  await page.locator('.deeper-result textarea').fill(custom);
  await page.locator('.deeper-result [data-deeper-action="follow"]').click();
  await page.waitForSelector('.deeper-proposal');
  ok(starts.length===1 && (await page.textContent('.deeper-proposal')).includes(custom), 'a custom follow-up receives a separate frozen proposal');
  await page.click('.deeper-proposal [data-deeper-action="start"]');
  await page.waitForFunction(() => document.querySelectorAll('.deeper-result').length===2);
  const second = (await (await page.request.get(BASE+'/api/operations')).json()).operations.find(x=>x.prepared_id===starts[1].prepared_id);
  const secondResult = await (await page.request.get(BASE+'/api/result/'+second.trace_id)).json();
  ok(secondResult.parent_trace_id===first.trace_id && secondResult.context.root.trace_id===root && secondResult.context.ancestry.length===1, 'the next answer keeps both root and previous question in its lineage');
  ok(await page.inputValue('#compose-text')==='The draft remains mine.', 'exploration leaves the writing unchanged');
  await page.goto(BASE+'/?trace='+second.trace_id);
  await page.waitForSelector('.deeper-result');
  ok(starts.length===2 && (await page.textContent('.deeper-result')).includes(custom), 'reloading a saved answer performs no new Start');
  await page.screenshot({path:path.join(OUT,'go-deeper-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  ok(await page.locator('[data-deeper-action="follow"]').isVisible(), 'the next question is usable at phone width');
  ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1), 'the exploration does not overflow the phone viewport');
  await page.screenshot({path:path.join(OUT,'go-deeper-phone.png'),fullPage:true});
  await page.locator('[aria-label="Exploration trail"] [data-deeper-action="reopen"]').first().click();
  await page.waitForSelector('[data-deeper-action="open"]');
  ok(starts.length===2 && (await page.textContent('body')).includes('Augustine’s excavation of memory'), 'the trail returns to the original selection without another call');
  // A response can disappear after the server has already accepted Start.
  // Preserve the key through Close, another click, and a full page reload.
  await page.goto(BASE+'/?trace='+root);
  await page.waitForSelector('[data-deeper-action="open"]');
  let prepares=0;
  page.on('request',r=>{if(r.method()==='POST' && new URL(r.url()).pathname==='/api/actions/prepare') prepares++;});
  await page.click('[data-deeper-action="open"]');
  await page.waitForSelector('[data-deeper-action="start"]');
  const prepareCount=prepares;
  await page.route('**/api/operations', async route=>{
    if(route.request().method()!=='POST') return route.continue();
    await route.fetch();
    await route.abort('failed');
  });
  await page.click('[data-deeper-action="start"]');
  await page.getByRole('button',{name:'Check Start again',exact:true}).waitFor();
  const uncertain=starts[starts.length-1];
  await page.click('[data-deeper-action="open"]');
  ok(prepares===prepareCount, 'reopening an uncertain Start does not prepare another paid attempt');
  await page.click('[data-deeper-action="cancel"]');
  await page.click('[data-deeper-action="open"]');
  ok(prepares===prepareCount, 'Close preserves the unresolved proposal and request key');
  await page.reload();
  await page.waitForSelector('[data-deeper-action="open"]');
  await page.click('[data-deeper-action="open"]');
  await page.getByRole('button',{name:'Check Start again',exact:true}).waitFor();
  await page.unroute('**/api/operations');
  await page.click('[data-deeper-action="start"]');
  await page.waitForSelector('.deeper-result');
  const retried=starts[starts.length-1];
  ok(retried.request_key===uncertain.request_key && retried.prepared_id===uncertain.prepared_id && prepares===prepareCount,
    'after reload an uncertain Start checks the same request key and frozen proposal');
  const savedOps=(await (await page.request.get(BASE+'/api/operations')).json()).operations;
  ok(savedOps.filter(x=>x.prepared_id===uncertain.prepared_id).length===1, 'a lost reply and its recovery produce one durable operation');
  // A browser that cannot retain a recovery key must refuse before spending.
  await page.goto(BASE+'/?trace='+root);
  await page.waitForSelector('[data-deeper-action="open"]');
  await page.click('[data-deeper-action="open"]');
  await page.waitForSelector('[data-deeper-action="start"]');
  const startsBeforeBlocked=starts.length;
  await page.evaluate(()=>{Storage.prototype.setItem=function(){throw new Error('fixture storage denied');};});
  await page.click('[data-deeper-action="start"]');
  await page.getByText(/could not save the request recovery key/).waitFor();
  ok(starts.length===startsBeforeBlocked, 'unavailable recovery storage refuses before a Start leaves the browser');
  ok(errors.length===0, 'no browser script errors: '+errors.join('; '));
  await browser.close();
  finish('deeper');
})().catch(e=>{console.error(e);process.exit(1);});
