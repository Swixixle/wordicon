// Isolated browser checks: all routes are intercepted; no app store or provider.
// Run with: node tests/journeys/deeper-evidence.js
const assert = require('assert/strict');
const path = require('path');
const {chromium} = require('playwright');
let checks = 0;
const ok = (condition, label) => { assert.ok(condition, label); checks++; console.log('ok   ' + label); };

(async () => {
  const browser = await chromium.launch(process.env.JOURNEY_CHROME ? {executablePath:process.env.JOURNEY_CHROME} : {});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    const requests = [], errors = [];
    let proposalVersion = 4;
    page.on('pageerror', error => { if (!require('./lib').benignPageError(error)) errors.push(String(error)); });
    await page.route('**/*', async route => {
      const request = route.request();
      requests.push({url:request.url(), method:request.method(), body:request.postDataJSON()});
      if (new URL(request.url()).pathname === '/api/actions/prepare') {
        return route.fulfill({contentType:'application/json', body:JSON.stringify({prepared_id:'prep_fixture', disclosure:{
          available:true, calls:4, cost:'unknown', lane:{external:true, model:'fixture-model'},
          exploration:{question:request.postDataJSON().inputs.question, root:{trace_id:'root_fixture'},
            research_goal:request.postDataJSON().inputs.continue_evidence ? {kind:'continue_evidence',question:'What does the later chapter say about memory?'} : {kind:'followup_question',question:request.postDataJSON().inputs.question},
            research_plan:{version:proposalVersion,limits:{max_search_rounds:3,max_source_reads:6,max_model_calls:4}}},
        }})});
      }
      return route.fulfill({contentType:'text/html', body:'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><main id="result"></main>'});
    });
    await page.goto('http://127.0.0.1:8499/deeper-evidence-fixture');
    await page.addScriptTag({path:path.resolve(__dirname, '../../webapp/deeper.js')});
    const base = {trace_id:'trace_current', title:'A saved source question', explanation:'Every search attempt failed.', context:{root:{trace_id:'root_fixture',selection:{anchor_name:'A subject'}},focus:{title:'A subject'}},
      citations:[{url:'https://example.test/book',title:'Book'}, {url:'https://example.test/book',title:'Duplicate'}, {url:'https://example.test/other'}, {url:'javascript:alert(1)'}]};
    async function render(extra) {
      await page.evaluate(result => {document.querySelector('#result').innerHTML = window.buildDeeperHtml(result);}, {...base,...extra});
      return page.locator('.deeper-result').innerText();
    }
    const acquisition = {web_search_requests:1,max_uses_requested:1,block_types:{server_tool_use:7},
      search_tool_uses:[{id:'search_a'},{id:'search_b'}], search_outcomes_recorded:true,
      search_result_outcomes:[{outcome:'results_returned',result_count:9,tool_use_id:'search_a'}, {outcome:'error',error_code:'max_uses_exceeded',tool_use_id:'search_b'}]};
    let text = await render({acquisition_usage:acquisition});
    ok(text.includes('Provider reports 1 search') && text.includes('1 allowed across recorded acquisitions'), 'legacy provider count and allowance are shown');
    ok(text.includes('2 distinct source leads attached'), 'lead count deduplicates safe URLs');
    ok(!text.includes('7 search'), 'generic server tool blocks are never counted as searches');
    ok(await page.locator('.deeper-acquisition').evaluate(el => el.nextElementSibling.textContent.includes('Source leads returned')), 'acquisition line immediately precedes source leads');
    await page.getByText('Search acquisition record', {exact:true}).click();
    text = await page.locator('.deeper-acquisition').innerText();
    ok(text.includes('Results returned · 9 result(s)') && text.includes('error code: max_uses_exceeded') && text.includes('attempt: search_b'), 'search outcomes and attempt error codes are inspectable');
    ok(text.includes('2 identified search tool attempt(s)'), 'only named web-search uses provide attempt count');
    ok(await page.getByText('Every search attempt failed.', {exact:true}).count() === 1, 'model prose is preserved separately from acquisition observations');
    text = await render({acquisition_records:[acquisition,{...acquisition,web_search_requests:2,max_uses_requested:2}]});
    ok(text.includes('Provider reports 3 searches') && text.includes('3 allowed across recorded acquisitions'), 'known provider counts sum over acquisition records');
    text = await render({acquisition_records:[acquisition,{web_search_requests:null}]});
    ok(text.includes('Provider reports at least 1 search; count unknown for 1 acquisition(s)'), 'partial usage never becomes a false complete total');
    text = await render({acquisition_usage:{block_types:{server_tool_use:7}}});
    ok(text.includes('Provider search count not recorded') && !text.includes('reports 0'), 'missing usage remains unknown');
    text = await render({acquisition_usage:{web_search_requests:0,max_uses_requested:1}});
    ok(text.includes('Provider reports 0 searches'), 'an explicit provider zero remains distinguishable from unknown');
    const research = {status:'quote_located',target_quote:'The exact source wording.',source_count:1,rounds_used:1,sources_tried:2,checkpoint_id:'checkpoint_fixture',
      proofs:[{url:'https://example.test/book',final_url:'https://example.test/book-x',body_sha256:'a'.repeat(64),match:{match_type:'exact',section_path:['Book X','Chapter 8'],start:42,end:67,excerpt:'Before. The exact source wording. After.'}}],
      steps:[{kind:'read',status:'retrieved',url:'https://example.test/book-x'}]};
    const noSources = {...research,status:'needs_more_evidence',source_count:0,usable_source_count:0,proofs:[],sources_tried:6};
    text = await render({evidence_research:noSources});
    ok(await page.locator('.deeper-evidence-notice').isVisible() && text.includes('No source text retrieved — model explanation, unverified.'), 'explicit zero retrieved texts visibly labels the model explanation as unverified');
    ok(await page.locator('.deeper-evidence-notice').evaluate(el => el.nextElementSibling.textContent === 'Every search attempt failed.'), 'the evidence notice immediately precedes the preserved explanation');
    text = await render({evidence_research:{...noSources,final_answer_status:'unavailable'}});
    ok(text.includes('No source text retrieved — no model explanation available.') && !text.includes('model explanation, unverified'), 'an unavailable answer is not presented as an available explanation');
    await render({explanation:'',evidence_research:noSources});
    ok(await page.locator('.deeper-evidence-notice').innerText() === 'No source text retrieved.', 'an absent explanation does not gain a claim that an explanation is available');
    let missingOrInvalidCountsUnlabeled = true;
    for (const source_count of [undefined,null,'0',false,-1,1.5]) {
      await render({evidence_research:{...noSources,source_count}});
      missingOrInvalidCountsUnlabeled &&= await page.locator('.deeper-evidence-notice').count() === 0;
    }
    ok(missingOrInvalidCountsUnlabeled, 'missing and malformed source counts never become a false zero-source claim');
    await render({evidence_research:undefined});
    ok(await page.locator('.deeper-evidence-notice').count() === 0, 'legacy results without research records have no invented source status');
    await render({is_fixture:true,evidence_research:noSources});
    ok(await page.locator('.deeper-evidence-notice').count() === 0, 'fixture zero-source counts never imply a live retrieval attempt');
    text = await render({evidence_research:{...noSources,source_count:2}});
    ok(text.includes('No retrieved text retained for grounding — explanation remains unverified.') && !text.includes('No source text retrieved'), 'readable but weak pages are distinguished from retrieval failure');
    await render({evidence_research:{...noSources,source_count:2,usable_source_count:1,fresh_source_count:0,sources_tried:0}});
    ok(await page.locator('.deeper-evidence-notice').count() === 0, 'saved usable text is not mislabeled as missing evidence when no new sources were read');
    await render({explanation:'<img src=x onerror=alert(1)>',evidence_research:noSources});
    ok(await page.locator('.deeper-result img').count() === 0 && (await page.locator('.deeper-result').innerText()).includes('<img src=x onerror=alert(1)>'), 'explanation content remains escaped beside the evidence notice');
    text = await render({acquisition_usage:acquisition,evidence_research:research});
    ok(text.includes('Quotation wording located in retrieved text') && text.includes('does not by itself establish authorship'), 'located wording has a precise limited evidence claim');
    ok(text.includes('Before. The exact source wording. After.'), 'source excerpt is visible beside its safe source link');
    await page.getByText('Passage record',{exact:true}).click();
    text = await page.locator('.deeper-evidence').innerText();
    ok(text.includes('42–67') && text.includes('Book X → Chapter 8') && text.includes('a'.repeat(64)), 'saved offsets, section and body hash are inspectable');
    ok(await page.locator('.deeper-evidence a').getAttribute('href') === 'https://example.test/book-x', 'final retrieved URL is used');
    await page.getByText('What this reading rests on',{exact:true}).click();
    text = await page.locator('.deeper-result').innerText();
    ok(text.includes('No source admission or interpretive support ruling') && text.includes('quotation has not been verified against an admitted passage'), 'mechanical wording checks preserve the original source standing');
    text = await render({citations:[{url:'https://a:private-password@example.test/book'}], evidence_research:{...research,
      proofs:[{...research.proofs[0],final_url:'https://a:private-password@example.test/book'}],
      steps:[{kind:'read',status:'rejected',url:'https://a:private-password@example.test/book'}]}});
    ok(await page.locator('.deeper-result a').count() === 0 && !(await page.locator('.deeper-result').textContent()).includes('private-password'), 'credential-bearing source URLs are neither linked nor displayed');
    text = await render({is_fixture:true,evidence_research:research});
    ok(text.includes('Simulated evidence only — no live source check was performed.') && !text.includes('Quotation wording located in retrieved text'), 'fixture evidence never claims a real source check');
    text = await render({evidence_research:{...research,status:'source_text_obtained',proofs:[],remaining_requirement:'Locate the exact sentence.'}});
    ok(text.includes('Legacy record: source text obtained; relevance and answer support were not established') && text.includes('Locate the exact sentence.'), 'legacy retrieval alone does not claim quotation or answer proof');
    ok(await page.getByRole('button',{name:'Continue checking',exact:true}).count() === 1, 'legacy retrieval records retain their continuation control');
    const candidates = {...research,status:'candidate_passages_found',target_quote:'',proofs:[],source_count:3,usable_source_count:2,
      retrieval_policy_rev:2,retrieval_pass_complete:true,stop_reason:'source_read_budget_reached',sources:[
        {url:'https://example.test/audiobooks/book-x',assessment:{weak:true,candidate_kind:'catalog_like',matched_question_terms:[],matched_work_terms:['confessions'],reason:['Catalog-like page; seek an edition with the passage.']}},
        {url:'https://example.test/book-x',assessment:{weak:false,candidate_kind:'text_indicated',matched_question_terms:['memory','happiness'],matched_work_terms:['confessions','augustine'],reason:['Relevant terms found; support still requires inspection.']}}
      ]};
    text = await render({evidence_research:candidates});
    ok(text.includes('Candidate passages collected; answer support remains unverified') && !text.includes('Quotation wording located'), 'candidate passages have no wording or answer-proof claim');
    ok(text.includes('3 readable source texts obtained') && text.includes('2 source texts retained as candidates'), 'readable source count stays distinct from screened candidate count');
    ok(text.includes('This pass reached its source-read allowance. The research question remains open.'), 'read allowance ends the pass without declaring the question answered');
    ok(await page.getByRole('button',{name:'Continue checking',exact:true}).count() === 1, 'candidate passages offer Continue checking');
    ok(!(await page.locator('.deeper-source-screening').getAttribute('open')), 'source screening starts collapsed');
    await page.getByText('Source screening · 2',{exact:true}).click();
    text = await page.locator('.deeper-source-screening').innerText();
    ok(text.includes('Weak candidate · Catalog or landing page') && text.includes('Question terms found: none recorded'), 'a weak landing page is visible as weak rather than proof');
    ok(text.includes('Question terms found: memory, happiness') && text.includes('Work terms found: confessions, augustine'), 'meaningful matching terms remain inspectable');
    ok(text.includes('automatic clues for choosing passages to inspect, not verification') && text.includes('do not establish authorship, relevance, or support for the answer'), 'screening is explicitly heuristic');
    await render({question:'Explain more.',evidence_research:{...candidates,screening_basis:'frozen_focus_fallback',sources:[{...candidates.sources[1],assessment:{...candidates.sources[1].assessment,question_basis:'frozen_focus_fallback',matched_question_terms:['augustine','confessions']}}]}});
    await page.getByText('Source screening · 1',{exact:true}).click();
    text = await page.locator('.deeper-result').innerText();
    ok(text.includes('Frozen subject terms found: augustine, confessions') && !text.includes('Question terms found:') && text.includes('Source screening used the saved subject and work') && text.includes('Your question · Explain more.'), 'generic questions disclose frozen-subject screening without attributing its terms to the question');
    text = await render({evidence_research:{...candidates,stop_reason:'search_budget_reached'}});
    ok(text.includes('This pass reached its search allowance. The research question remains open.'), 'search allowance stopping reason does not claim a resolved question');
    text = await render({evidence_research:{...candidates,stop_reason:'reused_complete_pass_for_answer_retry'}});
    ok(text.includes('Saved source screening was reused for another answer attempt. The research question remains open.') && !text.includes('complete pass'), 'saved-pass reuse describes an answer retry without calling research complete');
    text = await render({evidence_research:{...candidates,stop_reason:undefined}});
    ok(text.includes('This bounded retrieval pass has ended; that does not establish that the research question is answered.'), 'a completed retrieval pass remains distinct from an answered question');
    text = await render({evidence_research:{...research,stop_reason:'quotation_located'}});
    ok(text.includes('Checking stopped after locating the requested wording. Broader answer support remains unverified.'), 'quotation stopping reason preserves its narrow scope');
    text = await render({is_fixture:true,evidence_research:{...research,stop_reason:'quotation_located'}});
    ok(!text.includes('Checking stopped after locating the requested wording.'), 'fixture stop reason never suggests a live quotation check');
    text = await render({evidence_research:{...candidates,sources:[{url:'https://a:private-password@example.test/book',assessment:{weak:true,candidate_kind:'catalog_like',matched_question_terms:['<img src=x onerror=alert(1)>'],matched_work_terms:[],reason:['<script>alert(1)</script>']}}]}});
    await page.getByText('Source screening · 1',{exact:true}).click();
    ok(!(await page.locator('.deeper-source-screening').textContent()).includes('private-password') && await page.locator('.deeper-source-screening a').count() === 0, 'screening does not display or link credential-bearing URLs');
    ok(await page.locator('.deeper-source-screening img, .deeper-source-screening script').count() === 0 && (await page.locator('.deeper-source-screening').innerText()).includes('<script>alert(1)</script>'), 'source screening terms and reasons are escaped');
    text = await render({evidence_research:{...research,final_answer_status:'unavailable'}});
    ok(text.includes('A grounded answer is not yet available.') && await page.getByRole('button',{name:'Continue checking',exact:true}).count() === 1, 'a saved quotation match still offers continuation when the grounded answer is unavailable');
    await render({evidence_research:{...research,status:'needs_more_evidence',proofs:[],remaining_requirement:'Read the next available edition.'}});
    ok(await page.getByRole('button',{name:'Continue checking',exact:true}).count() === 1, 'unresolved evidence retains its continuation control');
    await render({evidence_research:candidates});
    const requestsBefore = requests.length;
    ok(requests.filter(r => r.method === 'POST').length === 0, 'rendering all saved evidence states performs no model or preparation request');
    await page.getByRole('button',{name:'Continue checking',exact:true}).click();
    await page.locator('.deeper-proposal').waitFor();
    const post = requests.find(r => r.method === 'POST');
    ok(requests.length === requestsBefore + 1 && post.url.endsWith('/api/actions/prepare'), 'Continue checking only prepares the next proposal');
    ok(post.body.subject.trace_id === 'trace_current' && post.body.inputs.question === 'Continue checking the quotation against source texts using the saved evidence.', 'continuation binds to the exact saved parent result');
    ok(post.body.inputs.continue_evidence === true, 'Continue checking explicitly identifies continuation of the existing evidence goal');
    text = await page.locator('.deeper-proposal').innerText();
    ok(text.includes('Evidence question · What does the later chapter say about memory?'), 'continuation proposal exposes the substantive frozen evidence question');
    ok(text.includes('3 search rounds, 6 direct source reads, 4 model calls') && text.includes('actual cost is unknown'), 'proposal states the frozen contingency and cost limits');
    ok(text.includes('For a question without exact quoted wording, checking continues through the available source-read or search allowance.') && text.includes('matching topic terms does not establish that the answer is supported'), 'revision-two proposal states the quoteless continuation and support limit');
    ok(text.includes('Links that look like readable pages are tried first.') && text.includes('Some reads are kept for later search approaches'), 'revision-three proposal explains heuristic readable-page ordering and reserved reads in plain language');
    ok(text.includes("If none of the carried-over links matches the question's own terms, the first reads wait for fresh search results instead"), 'revision-four proposal explains the question-blind deferral in plain language');
    ok(text.includes('Public source hosts receive bounded unauthenticated GETs') && text.includes('retrieved excerpts and failure summaries go to the configured model'), 'proposal discloses source requests and model-bound evidence');
    ok(text.includes('Nothing has started.') && requests.every(r => !r.url.endsWith('/api/operations')), 'continuation retains the explicit Start gate');
    await page.locator('.deeper-proposal [data-deeper-action="cancel"]').click();
    proposalVersion = 2;
    await page.locator('.deeper-result textarea').fill('How does the argument differ in the next book?');
    await page.getByRole('button',{name:'Review next step',exact:true}).click();
    await page.locator('.deeper-proposal').waitFor();
    const newQuestion = requests.filter(r => r.method === 'POST').at(-1).body;
    ok(newQuestion.inputs.question === 'How does the argument differ in the next book?' && !Object.prototype.hasOwnProperty.call(newQuestion.inputs, 'continue_evidence'), 'a new follow-up resets continuation intent and has no continuation flag');
    ok(!(await page.locator('.deeper-proposal').innerText()).includes('Some reads are kept for later search approaches'), 'an older frozen proposal does not promise revision-three allocation');
    ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'evidence and proposal fit a phone-width viewport');
    ok(errors.length === 0, 'no browser script errors');
    ok(requests.every(r => new URL(r.url).origin === 'http://127.0.0.1:8499'), 'no request leaves the intercepted fixture origin');
    console.log(`CHECKS ${checks}\nJOURNEY deeper-evidence OK`);
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode = 1;});
