// Actual standalone page; only named scratch API replies are controlled here.
module.exports=async function deflateLifecycle(page,{BASE,ok,view,setSaved}){
  const mutations=[];
  const observe=r=>{if(r.method()!=='GET'&&/^\/api\/(operations|actions|deflate)(?:\/|$)/.test(new URL(r.url()).pathname))mutations.push({url:r.url(),method:r.method()});};
  page.on('request',observe);
  const id='op_deflate_fixture',detail='**/api/deflate/operations/'+id;
  let release,seen,sawRestored,count=0;
  const restored=new Promise(resolve=>{sawRestored=resolve;});
  const started=new Promise(resolve=>{seen=resolve;}),held=new Promise(resolve=>{release=resolve;});
  await page.route(detail,async route=>{count++;if(count===1){seen();await held;}else sawRestored();const v=view();if(count===1){v.progress='STALE_OLD_GENERATION';v.status='running';}try{await route.fulfill({json:v});}catch(_){/* cancelled read */}});
  await page.locator('#dr-history button').first().click();await started;
  const content=await page.locator('#dr-current').textContent();
  await page.evaluate(()=>dispatchEvent(new Event('beforeunload')));release();
  await page.waitForTimeout(1900); // exceeds the page's scheduled polling interval
  ok(count===1,'departing Deflate page stops the pending read and sends no follow-on poll');
  ok(await page.locator('#dr-current').textContent()===content&&await page.locator('#dr-updates-paused').isVisible(),'paused Deflate display retains its source and offers visible recovery');
  await page.evaluate(()=>{dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  await restored;
  await page.waitForFunction(()=>document.getElementById('dr-progress')?.textContent==='Partial reading saved. Review held passages.');
  await page.waitForFunction(()=>document.getElementById('dr-updates-paused').hidden);
  ok(count===2&&!await page.locator('#dr-current').textContent().then(t=>t.includes('STALE_OLD_GENERATION')),'restoration uses a fresh GET generation and ignores the old response');
  await page.unroute(detail);

  // An interrupted initial status read must not lose its following history/open.
  let releaseStatus,sawStatus,statusCount=0;
  const statusStarted=new Promise(resolve=>{sawStatus=resolve;}),statusHeld=new Promise(resolve=>{releaseStatus=resolve;});
  await page.route('**/api/deflate/status',async route=>{statusCount++;if(statusCount===1){sawStatus();await statusHeld;}try{await route.fulfill({json:{available:true}});}catch(_){}});
  await page.reload({waitUntil:'domcontentloaded'});await statusStarted;
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true})));releaseStatus();
  await page.evaluate(()=>dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
  await page.waitForSelector('#dr-transcript');
  ok(statusCount===2&&await page.locator('#dr-history button').count()>0,'restoration resumes interrupted connection, history and selected-source reads');
  await page.unroute('**/api/deflate/status');

  // A real declined navigation leaves a visible explicit read-only recovery.
  await page.keyboard.press('Shift');
  await page.evaluate(()=>{window.__cancelDeflate=e=>{e.preventDefault();e.returnValue='Unsaved fixture';};addEventListener('beforeunload',window.__cancelDeflate);});
  let declined=false;page.once('dialog',async d=>{declined=d.type()==='beforeunload';await d.dismiss();});
  await page.goto(BASE+'/deflate-reading?cancelled-fixture',{timeout:5000}).catch(()=>{});
  await page.evaluate(()=>{removeEventListener('beforeunload',window.__cancelDeflate);delete window.__cancelDeflate;});
  ok(declined&&await page.getByRole('button',{name:'Resume updates',exact:true}).isVisible(),'declining navigation leaves Resume updates visible on the Deflate page');
  await page.getByRole('button',{name:'Resume updates',exact:true}).click();
  await page.waitForFunction(()=>document.getElementById('dr-updates-paused').hidden);
  await page.waitForSelector('#dr-transcript');
  ok(mutations.length===0,'Deflate read restoration and visible resume never retry Start or another mutation');

  // A Save already sent is not attached to the read AbortController.
  setSaved(false);await page.locator('#dr-history button').first().click();await page.waitForFunction(()=>document.getElementById('dr-save')?.disabled===false);
  let releaseSave,sawSave,saves=0;
  const saveStarted=new Promise(resolve=>{sawSave=resolve;}),saveHeld=new Promise(resolve=>{releaseSave=resolve;});
  await page.route(detail+'/save',async route=>{saves++;sawSave();await saveHeld;setSaved(true);await route.fulfill({json:{saved:true}});});
  await page.click('#dr-save');await saveStarted;
  await page.evaluate(()=>{dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}));dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}));});
  releaseSave();await page.waitForFunction(()=>document.getElementById('dr-save')?.textContent==='Saved');
  ok(saves===1&&mutations.length===1&&mutations[0].url.endsWith('/'+id+'/save'),'one explicit Save keeps its receipt across read cancellation without replay');
  await page.unroute(detail+'/save');page.off('request',observe);
};
