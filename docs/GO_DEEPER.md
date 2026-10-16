# Go deeper

Go deeper follows a particular person, work or idea from a saved Sprout thread. Sprout continues to find parallels across fields. The two actions have different purposes and keep their own saved runs.

## The first slice

Each saved thread in the original desk offers **↓ Go deeper**, including threads whose original analogy was rated strained or suspect. The button prepares a local proposal; it does not call a model. The proposal shows the frozen source thread and question, model lane, outbound fields, call allowance, cost disclosure and source standing. Only **Start** dispatches work.

The result offers an explanation, surrounding context, guidance for entering the work itself, returned source leads, suggested next questions and a free question field. Every follow-up gets another proposal. The root thread remains the subject; the source identity comes from its saved run and position, never from a title match. A trail reopens the original run and earlier answers without generating them again. Completed runs also reopen through the usual history and workspace result views.

The model receives the exact root selection and a bounded history of earlier questions and answers. The proposal discloses omissions, and the exact context is inspectable before Start. The saved trail remains available when older steps no longer fit in the request.

## What the result means

A Sprout quotation remains recall-unverified or a paraphrase. A reviewer saying an analogy is strained does not mean the author or work is unworthy of study. Go deeper carries that distinction through the result.

The configured gateway may use its search capability and return citations. Those links are leads for reading; they do not verify every generated assertion, establish an edition or admit a passage to a source work room. An answer without returned citations explicitly says it is a model reading from recall. The mock lane is visibly marked as a fixture and makes no live provider calls.

Following a question is curiosity, not endorsement. This action does not accept concepts, change a keeper judgment, alter a document or import a source. It records the operation, frozen request, response and ancestry through the existing durable stores. It does not infer reading time, record cursor activity or start a personal-model training pipeline.

## Dispatch and recovery

One proposal retains one request key across uncertain Start responses. Double clicks and retries with that key address the same operation. Closing an unconfirmed Start hides its card without discarding its proposal or key. The original thread and follow-up controls recover that request before offering another; browser session storage also retains it across a tab reload. Polling reads its durable status. A failed or unknown operation is displayed honestly and never automatically started again. A completed answer can be reopened after a server restart from the saved result.

This slice starts from saved Sprout threads and continues from saved Go deeper answers. It does not add entry buttons to every concept or library object, automatically fetch full texts, fuse Deflate, or provide a separate multi-provider comparison service.

## Integration surface

- `explore.deepen` prepares a `result` subject with `trace_id` and the original `thread_index`; follow-ups use the deeper result's `trace_id` and an explicit `inputs.question`.
- A hash-covered context snapshot binds the exact source, question and prior steps before dispatch.
- `/api/operations` starts the prepared proposal with `prepared_id` and `request_key`; `/api/operations/<id>` and `/api/result/<trace_id>` read status and saved results.
- `webapp/deeper.js` renders the proposal, result, trail and follow-up controls; the original desk supplies its Sprout and saved-result hooks.

The integration should be applied to the owner's current checkout and exercised there before replacing a beta launcher. This implementation was prepared against the saved r88 baseline; newer local changes must be preserved.

## Verification and applying the patch

Baseline: `7bd14ee9fdaf296728d8b2e4f26f669c16eb7453` (saved r88). No schema file or migration changes. The root README is unchanged. This build has not replaced a Mac checkout or launcher, and has made no live model calls.

Verified on Linux: **46 focused Python tests** and **26 Chromium journey checks** pass. The existing global constraint suite exits 0, with three disclosed skips: optional python-docx opening of exported DOCX, and two checks requiring the private corpus. The whole pre-existing browser journey suite was not rerun. The new journey is included in its mock-lane phase.

The secret scan passes. A pre-existing test-only key-shaped sentinel triggered that scan; its value is now an explicitly invalid test string. The fail-closed test still verifies that a present key cannot switch test mode to live. No scanner exception was added.

The focused checks and Chromium journey use temporary stores. The journey covers proposal/cancel, exact subject, duplicate Start, custom follow-up, unchanged writing, Recent, saved reopening, phone width, and a Start whose response disappears after the server accepts it. Close, reopening and reloading must reuse the same request key. Storage refusal must send nothing.

```sh
python -m pytest tests/test_deeper.py tests/test_deeper_integration.py -q
python tests/test_global_constraints.py
# Requires the pinned Playwright in tests/journeys and its Chromium browser.
PYTHON=python bash tests/journeys/run-deeper.sh
```

The Python tests also cover altered source/snapshot refusal, changed-provider retries, raw reply retention, and recovery after a provider reply and saved result but before operation completion. Tests use the existing test-mode egress guard; they need no provider credentials.

Apply the exported patch on a new branch from the current Mac checkout, using `git am --3way`. Resolve any overlaps against that checkout's newer Ledger, backup and front-door changes. Keep its existing store and launcher configuration. Run these checks there and exercise the actual Safari UI before selecting the candidate build. Do not reset the checkout to r88: r88 is the patch's base, not a deployment recommendation.

Live usefulness and source-retrieval quality remain unverified until an explicitly started live proposal returns. WebKit could not be exercised in the Linux build environment because required system libraries could not be installed. This feature uses the configured gateway's existing search capability; it does not silently switch providers when that capability is unavailable.
