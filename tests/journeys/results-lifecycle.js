// Deterministic browser lifecycle checks alongside the real Ledger reload
// checks. Named operation GETs and one explicit held POST are fixture
// responses; no operation is created by these cancellation checks.
module.exports = async function resultsLifecycle(page, {BASE, ENGINE, OUT, ok}) {
  await page.waitForFunction(() => window.__work?.results && !window.__work.results.polling);
  await page.evaluate(() => {
    const r = window.__work.results;
    clearTimeout(r.pollTimer);
    window.__resultsSaved = {tracked:r.tracked, selected:r.selected, recentNeeded:r.recentNeeded, recentLabelOf:r.recentLabelOf};
    r.tracked = new Map(); r.selected = null; r.recentNeeded = false;
  });
  const proof = {synthetic_page_transitions:true, real_cancelled_navigation:true, requests:[], observed_operation_requests:[]};
  const observe = request => {const url=new URL(request.url());if (/^\/api\/(operations|actions)(?:\/|$)/.test(url.pathname)) proof.observed_operation_requests.push({url:request.url(),method:request.method()});};
  page.on('request',observe);
  let phase = 'poll-before-hide', release, started;
  let waiting = new Promise(resolve => { started = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  const prefix = 'lifecycle_' + ENGINE + '_';
  const detailPattern = '**/api/operations/' + prefix + '*';
  let holdFirst = true;
  await page.route(detailPattern, async route => {
    const request = route.request();
    const id = new URL(request.url()).pathname.split('/').pop();
    proof.requests.push({url:request.url(),method:request.method(),phase});
    if (holdFirst) { holdFirst = false; started(); await held; }
    try { await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({operation_id:id,kind:'job',status:'complete',recovery:{why:'fixture record'},output:'fixture'})}); }
    catch (_) { /* the first fetch was deliberately aborted on pagehide */ }
  });
  await page.evaluate(prefix => {
    const r=window.__work.results;
    for (let i=0;i<3;i++) r.tracked.set(prefix+i,{id:prefix+i,kind:'job',status:'running',last:null,prepared:null});
    window.__heldPoll=r.poll();
  },prefix);
  await waiting;
  const hidden = await page.evaluate(() => {
    const r=window.__work.results;window.__oldResultsController=r.readController;
    window.dispatchEvent(new Event('beforeunload'));
    return {active:r.pageActive,aborted:r.readController?.signal.aborted};
  });
  phase='poll-after-hide';release();
  await page.evaluate(() => window.__heldPoll);
  ok(hidden.active === false && hidden.aborted === true, 'beforeunload aborts pending operation GETs before pagehide');
  ok(proof.requests.length === 1 && proof.requests[0].method === 'GET', 'a cancelled poll starts no later detail read in the departing page');
  phase='poll-after-restore';
  await page.evaluate(() => {window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  await page.waitForFunction(prefix => [...window.__work.results.tracked.values()].filter(t=>t.id.startsWith(prefix)).every(t=>t.status==='complete'),prefix);
  ok(await page.evaluate(() => window.__work.results.readController !== window.__oldResultsController && !window.__work.results.readController.signal.aborted), 'restore creates a fresh read generation and resumes pending details');
  ok(proof.requests.length === 4 && proof.requests.slice(1).every(r=>r.phase==='poll-after-restore'), 'restored reads complete all three records');
  ok(await page.locator('#results-updates-status').isHidden(), 'page restoration clears the paused-updates status');
  await page.unroute(detailPattern);

  // A restored page must also recover a list or explicit Open that was cut
  // before it had any detail to poll. Each first response is held across hide.
  for (const mode of ['list','open','refresh','retry_refresh','cancelled_navigation']) {
    let releaseFirst, sawFirst, count=0;
    const firstSeen=new Promise(resolve=>{sawFirst=resolve;});
    const firstHeld=new Promise(resolve=>{releaseFirst=resolve;});
    const id=prefix+mode;
    const pattern=mode==='list' ? '**/api/operations?limit=30' : '**/api/operations/'+id;
    await page.evaluate(() => {const r=window.__work.results;clearTimeout(r.pollTimer);r.tracked=new Map();r.selected=null;});
    await page.route(pattern,async route=>{
      count++;proof.requests.push({url:route.request().url(),method:route.request().method(),phase:mode+'-'+count});
      if(count===1){sawFirst();await firstHeld;}
      if(mode==='retry_refresh'&&count===2)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'temporary fixture failure'})});
      const record={operation_id:id,kind:'job',status:'complete',recovery:{why:'fixture record'},output:'fixture',fixture_generation:count};
      try{await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(mode==='list'?{operations:[record]}:record)});}catch(_){/* cancelled first read */}
    });
    await page.evaluate(({mode,id})=>{const r=window.__work.results;if(mode==='list')window.__pendingList=r.loadRecent();else {if(mode==='refresh'||mode==='retry_refresh')r.tracked.set(id,{id,kind:'job',status:'complete',fromStore:true,last:{recovery:{why:'previous read'}},prepared:null});r.open(id,'job');}},{mode,id});
    await firstSeen;
    if(mode==='cancelled_navigation') {
      await page.evaluate(()=>window.__work.layout.setResults(true));
      await page.keyboard.press('Shift'); // real activation allows the confirmation dialog
      const contentBefore=await page.locator('#results-body').textContent();
      await page.evaluate(()=>{window.__cancelNavigation=e=>{e.preventDefault();e.returnValue='Unsaved fixture';};addEventListener('beforeunload',window.__cancelNavigation);});
      let dismissed=false;
      page.once('dialog',async dialog=>{dismissed=dialog.type()==='beforeunload';await dialog.dismiss();});
      await page.goto(BASE+'/work?cancelled-navigation-fixture',{timeout:5000}).catch(()=>{});
      await page.evaluate(()=>{removeEventListener('beforeunload',window.__cancelNavigation);delete window.__cancelNavigation;});
      ok(dismissed && await page.evaluate(()=>!window.__work.results.pageActive&&!window.__work.results.pageHidden), 'declining a real navigation confirmation keeps the document and paused reads');
      await page.evaluate(()=>dispatchEvent(new KeyboardEvent('keydown',{key:'Shift'})));
      ok(count===1&&await page.evaluate(()=>!window.__work.results.pageActive),'untrusted input does not resume a cancelled navigation');
      ok(await page.locator('#results-body').textContent()===contentBefore,'pausing retains the displayed result content');
      ok(await page.locator('#results-updates-status').isVisible()&&await page.getByRole('button',{name:'Resume updates',exact:true}).isVisible(),'cancelled navigation visibly offers Updates paused and Resume updates');
      await page.evaluate(()=>window.__work.layout.setTools(false));
      await page.setViewportSize({width:760,height:900});
      await page.waitForFunction(()=>document.getElementById('results-body').parentElement.id==='stacked-body');
      ok(await page.locator('#results-updates-status').isVisible()&&await page.getByRole('button',{name:'Resume updates',exact:true}).isVisible(),'stacked Results also retains visible paused status and recovery');
      await page.screenshot({path:require('path').join(OUT,'results-paused-'+ENGINE+'.png'),fullPage:true});
      await page.getByRole('button',{name:'Resume updates',exact:true}).click();
      await page.setViewportSize({width:1280,height:800});
      ok(await page.locator('#results-updates-status').isHidden(),'Resume updates clears the status using a read-only action');
    } else await page.evaluate(()=>{window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
    releaseFirst();
    const expected=mode==='retry_refresh'?3:2;
    await page.waitForFunction(({id,expected})=>window.__work.results.tracked.get(id)?.last?.fixture_generation===expected,{id,expected});
    ok(count===expected, 'restore completes '+mode+' with '+expected+' recorded GET attempts');
    ok(await page.evaluate(id=>window.__work.results.tracked.get(id).last.recovery.why==='fixture record',id), 'the restored '+mode+' keeps the completed record');
    await page.unroute(pattern);
  }
  ok(proof.requests.every(r=>r.method==='GET'&&r.url.startsWith(BASE+'/api/operations')), 'lifecycle resumption uses same-origin operation GETs only');
  // The abort controller belongs only to reads. A write already sent keeps
  // its original receipt and is not replayed when the page is restored.
  let releaseWrite, writeSeen, writes=0;
  const writeStarted=new Promise(resolve=>{writeSeen=resolve;});
  const writeHeld=new Promise(resolve=>{releaseWrite=resolve;});
  const writePath='/api/operations/'+prefix+'write/recover';
  await page.route('**'+writePath,async route=>{writes++;writeSeen();await writeHeld;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({receipt:'original-write'})});});
  await page.evaluate(async writePath=>{const {postJSON}=await import('/work/util.js');window.__heldWrite=postJSON(writePath,{fixture:true});},writePath);
  await writeStarted;
  await page.evaluate(()=>{window.dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  releaseWrite();
  const writeReceipt=await page.evaluate(()=>window.__heldWrite);
  ok(writes===1&&writeReceipt.ok&&writeReceipt.data.receipt==='original-write','page lifecycle preserves the one explicitly sent write and its receipt');
  await page.unroute('**'+writePath);
  const mutations=proof.observed_operation_requests.filter(r=>r.method!=='GET');
  ok(mutations.length===1&&mutations[0].method==='POST'&&mutations[0].url===BASE+writePath,'restore issues no Start or replayed mutation');
  page.off('request',observe);
  await page.evaluate(()=>{const r=window.__work.results;Object.assign(r,window.__resultsSaved);delete window.__resultsSaved;r.render();r.poll();});
  return proof;
};
