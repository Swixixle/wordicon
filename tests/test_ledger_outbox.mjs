// Offline browser-boundary fixtures. No server, provider or real browser store.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';

const source = fs.readFileSync(new URL('../webapp/work/ledger.js', import.meta.url), 'utf8')
  .replace('export class Ledger', 'globalThis.Ledger = class Ledger');
const SCOPE_A = 'ledger_' + 'a'.repeat(24), SCOPE_B = 'ledger_' + 'b'.repeat(24);
class Storage {
  constructor() { this.rows = new Map(); this.fail = false; }
  get length() { if (this.fail) throw Error('fixture unavailable'); return this.rows.size; }
  key(i) { return [...this.rows.keys()][i] || null; }
  getItem(k) { if (this.fail) throw Error('fixture unavailable'); return this.rows.get(k) || null; }
  setItem(k,v) { if (this.fail) throw Error('fixture unavailable'); this.rows.set(k, String(v)); }
  removeItem(k) { if (this.fail) throw Error('fixture unavailable'); this.rows.delete(k); }
}
function fixture(storage = new Storage(), scope = SCOPE_A) {
  const state = {storage, scope, enabled:true, posts:[], beacons:[], timers:new Map(), listeners:{}, reply:'ack', beacon:true};
  let nextTimer = 0;
  const context = vm.createContext({crypto:webcrypto, Date, Math, JSON, Set, Map, String, console,
    localStorage: storage,
    document:{hidden:false, addEventListener:(kind, fn) => state.listeners[kind] = fn},
    window:{addEventListener:(kind, fn) => state.listeners[kind] = fn},
    navigator:{sendBeacon:(url, body) => {state.beacons.push({url, events:JSON.parse(body).events}); return state.beacon;}},
    setTimeout:fn => {state.timers.set(++nextTimer,fn);return nextTimer;},
    clearTimeout:id => state.timers.delete(id),
    fetch:async (url, options={}) => {
      if (url === '/api/ledger/config') return {ok:true,json:async()=>({enabled:state.enabled,scope_id:state.scope})};
      assert.equal(url, '/api/ledger');
      const events = JSON.parse(options.body).events;
      state.posts.push({events, options});
      if (state.reply === 'network') throw Error('fixture disconnected');
      if (state.reply === 'off') return {ok:false,status:409,json:async()=>({code:'recording_off'})};
      if (state.reply === '500') return {ok:false,status:500,json:async()=>({error:'fixture failed'})};
      if (state.reply === 'invalid_json') return {ok:true,status:200,json:async()=>{throw Error('fixture truncated');}};
      if (state.reply === 'unrelated_ack') return {ok:true,status:200,json:async()=>({acknowledged:['event_not_sent']})};
      return {ok:true,status:200,json:async()=>({acknowledged:events.map(e=>e.event_id)})};
    }});
  vm.runInContext(source, context);
  state.ledger = new context.Ledger();
  return state;
}
const tests = [];
function test(name, fn) { tests.push([name,fn]); }
async function fresh() { const f=fixture();await f.ledger.config();return f; }

test('reload delivers the same stable ID and retains separate intentional visits', async()=>{
  const f=await fresh();f.ledger.note('document_opened',{id:'doc1'});f.ledger.note('document_opened',{id:'doc1'});
  const ids=f.ledger.pending().map(e=>e.event_id);
  assert.equal(new Set(ids).size,2);
  const restarted=fixture(f.storage);await restarted.ledger.config();
  assert.deepEqual(Array.from(restarted.ledger.pending(),e=>e.event_id),Array.from(ids));
  await restarted.ledger.flush();assert.equal(restarted.ledger.pending().length,0);
  assert.equal(restarted.posts[0].events[0].session_id,f.ledger.session);
  assert.notEqual(restarted.ledger.session,f.ledger.session);
});

test('accepted beacon is not an acknowledgement, and reload retries it', async()=>{
  const f=await fresh();f.ledger.note('page_shown',{page:'work'});await f.ledger.flush(true);
  assert.equal(f.beacons.length,1);assert.equal(f.posts.length,0);assert.equal(f.ledger.pending().length,1);
  const restarted=fixture(f.storage);await restarted.ledger.config();await restarted.ledger.flush();
  assert.equal(restarted.posts[0].events[0].event_id,f.beacons[0].events[0].event_id);
  assert.equal(restarted.ledger.pending().length,0);
});

test('rejected beacon falls back to keepalive request', async()=>{
  const f=await fresh();f.beacon=false;f.ledger.note('session_end',{});await f.ledger.flush(true);
  assert.equal(f.posts.length,1);assert.equal(f.posts[0].options.keepalive,true);assert.equal(f.ledger.pending().length,0);
});

test('HTTP failure, broken acknowledgement and network loss retain every event', async()=>{
  const f=await fresh();f.ledger.note('result_viewed',{id:'result1'});
  const id=f.ledger.pending()[0].event_id;
  for(const reply of ['500','invalid_json','network','unrelated_ack']) {
    f.reply=reply;await f.ledger.flush();assert.equal(f.ledger.pending().length,1);
    assert.equal(f.ledger.pending()[0].event_id,id);
  }
  f.reply='ack';await f.ledger.flush();assert.equal(f.ledger.pending().length,0);
});

test('recording off stops new capture/transmission but preserves durable pending rows', async()=>{
  const f=await fresh();f.ledger.note('page_shown',{page:'work'});const id=f.ledger.pending()[0].event_id;
  f.ledger.setEnabled(false);f.ledger.note('page_shown',{page:'disabled'});await f.ledger.flush(true);
  assert.equal(f.posts.length+f.beacons.length,0);assert.equal(f.ledger.pending().length,1);
  f.ledger.setEnabled(true);await f.ledger.flush();assert.equal(f.posts[0].events[0].event_id,id);
  const off=fixture(f.storage);off.enabled=false;await off.ledger.init();await off.ledger.flush();
  assert.equal(off.posts.length,0);assert.equal(off.ledger.pending().length,0);
});

test('server switch-off rejection retains the attempted batch and suppresses retries', async()=>{
  const f=await fresh();f.ledger.note('page_shown',{});f.reply='off';await f.ledger.flush();
  assert.equal(f.ledger.enabled,false);assert.equal(f.ledger.pending().length,1);
  await f.ledger.flush();assert.equal(f.posts.length,1);assert.equal(f.timers.size,0);
});

test('new local store never drains an earlier store outbox', async()=>{
  const f=await fresh();f.ledger.note('document_opened',{id:'old_private_document'});
  const next=fixture(f.storage,SCOPE_B);await next.ledger.config();next.ledger.note('page_shown',{page:'new'});await next.ledger.flush();
  assert.equal(next.posts[0].events.length,1);assert.equal(next.posts[0].events[0].subject.page,'new');
  assert.equal(f.ledger.pending().length,1);
});

test('two tabs retain each other’s events despite concurrent acknowledgements', async()=>{
  const a=await fresh();const b=fixture(a.storage);await b.ledger.config();
  a.ledger.note('document_opened',{id:'a'});b.ledger.note('document_opened',{id:'b'});
  const before=a.ledger.pending();a.ledger.acknowledge([before[0].event_id],before);
  b.ledger.note('document_opened',{id:'c'});
  assert.equal(a.ledger.pending().length,2);assert.equal(b.ledger.pending().length,2);
  await a.ledger.flush();assert.equal(b.ledger.pending().length,0);
});

test('browser storage failure records an explicit memory-only capture gap', async()=>{
  const f=await fresh();f.storage.fail=true;f.reply='network';f.ledger.note('document_opened',{id:'memory'});
  const pending=f.ledger.pending();assert.equal(pending.filter(e=>e.type==='capture_gap').length,1);
  assert.equal(pending.find(e=>e.type==='capture_gap').subject.kind,'browser_storage_unavailable');
  await f.ledger.flush();assert.equal(f.ledger.pending().length,2);
  f.storage.fail=false;f.reply='ack';await f.ledger.flush();assert.equal(f.ledger.pending().length,0);
});

test('malformed outbox is preserved and disclosed without blocking good rows', async()=>{
  const f=await fresh();const key=f.ledger.prefix()+'bad';f.storage.setItem(key,'{broken');
  f.ledger.note('page_shown',{});
  assert.equal(f.ledger.pending().filter(e=>e.type==='capture_gap').length,1);
  await f.ledger.flush();assert.equal(f.storage.getItem(key),'{broken');
  assert.equal(f.posts[0].events.length,2);assert.equal(f.ledger.pending().length,0);
});

test('bounded outbox records a gap rather than dropping earlier activity', async()=>{
  const f=await fresh();f.ledger.maxPending=2;f.ledger.note('page_shown',{page:'one'});f.ledger.note('page_shown',{page:'two'});
  f.ledger.note('page_shown',{page:'three'});f.ledger.note('page_shown',{page:'four'});
  const pending=f.ledger.pending();assert.equal(pending.length,3);
  assert.equal(pending.filter(e=>e.type==='capture_gap'&&e.subject.kind==='outbox_full').length,1);
  assert.equal(pending.filter(e=>e.type==='page_shown').length,2);
});

test('long real document title is bounded before persistence and cannot poison delivery', async()=>{
  const f=await fresh();f.ledger.note('document_opened',{id:'doc1',title:'x'.repeat(200)});
  const pending=f.ledger.pending();assert.equal(pending.find(e=>e.type==='document_opened').subject.title.length,120);
  assert.equal(pending.filter(e=>e.type==='capture_gap'&&e.subject.kind==='metadata_shortened').length,1);
  await f.ledger.flush();assert.equal(f.ledger.pending().length,0);
});

test('body and authorization properties never enter browser storage or transport', async()=>{
  const f=await fresh();f.ledger.note('document_opened',{id:'doc1',body:'PRIVATE BODY',Authorization:'Bearer SECRET',nested:{Cookie:'SECRET'}});
  const stored=JSON.stringify([...f.storage.rows]);assert.ok(!stored.includes('PRIVATE BODY'));assert.ok(!stored.includes('SECRET'));
  await f.ledger.flush();assert.deepEqual(f.posts[0].events[0].subject,{id:'doc1'});
});

test('valid JSON poison pills remain preserved but are quarantined from good delivery', async()=>{
  const f=await fresh();
  const bad=[{type:'unknown'},{subject:{title:'x'.repeat(121)}},{subject:{body:'DO NOT TRANSMIT'}},{session_id:123}];
  for(const [index,changes] of bad.entries()) {
    const event={event_id:'event_bad_'+index,session_id:f.ledger.session,scope_id:f.scope,type:'page_shown',at:'2026-10-18',subject:{},...changes};
    f.storage.setItem(f.ledger.prefix()+event.event_id,JSON.stringify(event));
  }
  f.ledger.note('page_shown',{page:'good'});await f.ledger.flush();
  assert.equal(f.posts[0].events.length,2);assert.equal(f.ledger.pending().length,0);
  assert.equal(f.storage.rows.size,4);assert.ok(!JSON.stringify(f.posts).includes('DO NOT TRANSMIT'));
  const reloaded=fixture(f.storage);await reloaded.ledger.config();reloaded.ledger.note('page_shown',{page:'still_good'});await reloaded.ledger.flush();
  assert.equal(reloaded.posts[0].events.length,2);assert.equal(reloaded.storage.rows.size,4);
});

test('page lifecycle records observed boundaries only', async()=>{
  const f=fixture();await f.ledger.init();assert.equal(f.ledger.pending()[0].type,'session_start');
  assert.deepEqual(Object.keys(f.listeners).sort(),['pagehide','visibilitychange']);
  f.listeners.pagehide();assert.equal(f.beacons.length,1);
  assert.equal(f.ledger.pending().filter(e=>e.type==='session_end').length,1);
});

test('delivery status is read-only and exposes IDs rather than captured metadata', async()=>{
  const f=await fresh();f.ledger.note('document_opened',{id:'private_doc',title:'private title'});
  const before=JSON.stringify([...f.storage.rows]);const count=f.ledger.queue.length;
  const id=f.ledger.pending()[0].event_id;const status=f.ledger.status();
  assert.equal(status.pending_count,1);assert.equal(status.durable_count,1);assert.equal(status.memory_only_count,0);
  assert.deepEqual(Array.from(status.event_ids),[id]);assert.ok(!JSON.stringify(status).includes('private'));
  assert.equal(JSON.stringify([...f.storage.rows]),before);assert.equal(f.ledger.queue.length,count);assert.equal(f.posts.length,0);
  f.reply='network';await f.ledger.flush();assert.match(f.ledger.status().last_error,/not acknowledge/);
  f.reply='ack';await f.ledger.flush();assert.equal(f.ledger.status().pending_count,0);assert.equal(f.ledger.status().last_error,'');
});

test('a reloaded recording-off page can inspect its existing scoped outbox without sending', async()=>{
  const f=await fresh();f.ledger.note('page_shown',{page:'work'});const id=f.ledger.status().event_ids[0];
  const off=fixture(f.storage);off.enabled=false;await off.ledger.init();
  assert.equal(off.ledger.status().enabled,false);assert.equal(off.ledger.status().pending_count,1);
  assert.equal(off.ledger.status().event_ids[0],id);assert.equal(off.posts.length,0);
  await off.ledger.flush();assert.equal(off.posts.length,0);
});

test('delivery status reports malformed and unavailable storage without mutating it', async()=>{
  const f=await fresh();f.storage.setItem(f.ledger.prefix()+'bad','{broken');
  const before=JSON.stringify([...f.storage.rows]);const status=f.ledger.status();
  assert.equal(status.invalid_count,1);assert.equal(status.pending_count,0);
  assert.equal(f.ledger.gaps.size,0);assert.equal(JSON.stringify([...f.storage.rows]),before);
  f.storage.fail=true;f.ledger.note('page_shown',{page:'work'});
  const unavailable=f.ledger.status();assert.equal(unavailable.storage_available,false);
  assert.ok(unavailable.memory_only_count>=1);assert.ok(unavailable.gaps.includes('browser_storage_unavailable'));
});

test('unknown server scope exposes safe unconfirmed counts without assigning or transmitting', async()=>{
  const f=await fresh();f.ledger.note('page_shown',{page:'work'});const id=f.ledger.status().event_ids[0];
  const offline=fixture(f.storage);offline.ledger.config=async()=>false;
  const before=JSON.stringify([...f.storage.rows]);const s=offline.ledger.status();
  assert.equal(s.scope_confirmed,false);assert.equal(s.unconfirmed_scope_count,1);assert.equal(s.pending_count,1);
  assert.equal(s.event_ids[0],id);assert.equal(offline.ledger.scope,'');
  await offline.ledger.flush();assert.equal(offline.posts.length,0);assert.equal(JSON.stringify([...f.storage.rows]),before);
});

test('recording off retains previously captured memory-only rows until acknowledged', async()=>{
  const f=await fresh();f.storage.fail=true;f.ledger.note('page_shown',{page:'captured-while-on'});
  const ids=Array.from(f.ledger.status().event_ids);assert.ok(ids.length>=1);
  f.ledger.setEnabled(false);assert.deepEqual(Array.from(f.ledger.status().event_ids),ids);
  await f.ledger.flush();assert.equal(f.posts.length,0);
  f.storage.fail=false;f.ledger.setEnabled(true);await f.ledger.flush();
  assert.deepEqual(f.posts[0].events.map(e=>e.event_id).sort(),ids);assert.equal(f.ledger.status().pending_count,0);
});

let passed=0;
for(const [name,fn] of tests) {
  try {await fn();console.log('PASS '+name);passed++;}
  catch(e) {console.error('FAIL '+name);console.error(e);process.exitCode=1;}
}
console.log(`${passed}/${tests.length} capture outbox fixtures passed`);
