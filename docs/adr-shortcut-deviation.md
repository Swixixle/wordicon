# Deviation record — the paragraph shortcut is ⌘⇧⏎, not ⌘⇧T

**Ruled:** ⌘⇧P for the whole draft, **⌘⇧T** for the current paragraph.
**Built:** ⌘⇧P for the whole draft, **⌘⇧⏎** for the current paragraph.
**Commit:** `76a8b54` (pass 2). **Recorded:** 2026-09-04.

## The conflict

⌘⇧T is **Reopen Last Closed Tab** in Safari and in Chrome. It is a
browser-chrome binding, not a page binding: the page receives the keydown, and
`preventDefault()` does not stop the browser from also acting on it. So the
ruled chord would have opened a stray tab every time the owner asked for a
workup on the paragraph he was writing in — silently, alongside the intended
behaviour, with no error to notice.

## Why it was replaced rather than referred back

The ruling that authorised the chords anticipated this case and delegated it:

> If Safari or macOS reserves either shortcut, prove that in the real browser
> and choose a safe replacement. Keep a visible menu/button alternative for
> discoverability and accessibility.

## What was and was not proved

**Proved, in real WebKit:** ⌘⇧P and ⌘⇧⏎ both reach the page, are cancelable,
and open the invocation panel without starting a run
(`tests/journeys/deep.js`, in Safari's own engine).

**Not proved here, and stated plainly:** headless WebKit carries none of
Safari's application-level menu bindings, so this environment cannot
demonstrate that ⌘⇧T is taken. That claim rests on the documented Safari and
Chrome menu binding, not on a measurement made here. It is the one part of
this record that is documentation rather than evidence. Ten seconds in the
owner's own Safari would settle it either way.

⌘⇧⏎ is unbound in both browsers' menus.

## The mitigation the ruling required

Neither chord is load-bearing. The same two doors — *This paragraph* and *The
whole draft*, each showing its chord — sit in the panel behind **Aa**, which is
the room's existing quiet furniture. A capability reachable only by a keystroke
is a capability most people never have, so the chord is an accelerator and
never the only route.

## If the owner wants ⌘⇧T back

`DEEP_CHORDS.paragraph.key` in `webapp/index.html` is a one-line change, and
the suite pins the refusal deliberately: a mutation restoring `key: 't'` fails
by name, with the reason. Changing it means changing that pin too, which is the
intended friction.

---

## Addendum, 2026-09-04: the arrival styles, reconciled

The owner asked for letters that "splatter and drip into place," describing it
as closer to the Aperture Writer concept. His own Aperture brief says the
opposite in as many words — *"letters do not splatter, drip, smear, or decay
after they form. They arrive beautifully and then they are simply words"* —
and the drip language in that document belongs to a different layer of it, the
optional momentum feeling, not to the letters.

Both memories are real and neither is rewritten here. The narrow Aperture
brief governs the DEFAULT; the broader writing-system concept, which envisaged
several arrival styles, governs what may be offered beside it.

- **Settle** is the default and is not new. It is the motion that has been
  shipping since the room existed: a quick drop, soft mass, a slight
  overshoot, blur resolving into clarity, then complete rest. What this block
  added was the name and the list around it, not the animation.
- **Ink** is optional and its whole licence is the word *during*. It may
  splatter on the way in; when the 360–420 ms animation ends the class comes
  off, the out-of-flow copy stops existing, and what remains is ordinary
  settled text. Nothing crawls, drips or decays after the landing.
- **Plain** is the non-animated option, and is what a reduced-motion setting
  produces regardless of the choice stored.

All three obey the paint contract: *paint may mirror the writing, but it may
never own layout, selection, input, pointer behavior, clipboard content, or
accessibility meaning.* Ink is cheap only because of the caret repair — the
animated copy is an out-of-flow `::before` that occupies no space, so it can
overshoot, scale and blur without moving a single wrap point. Before that fix
this style could not have been built without breaking the room.

The preference lives behind **Aa** beside the face, the size and the view. It
is a device preference: never part of a draft, never a record event.

**Stated plainly, and not proved here:** Ink is a first visual cut. It has been
tested for containment and for obeying the reduced-motion setting, not for
whether it is pleasant to type behind for an hour.

---

# Deviation record — the acquisition record has two observations, not five stages

**Ruled:** *"per-thread acquisition facts; `returned` / `fetched` / `examined` /
`anchored` / `used` are distinct."*
**Built:** two recorded observations — `returned_by_provider_search` and
`cited_in_generated_prose` — and five *rendered* facts, three of which are
printed as words because there is no event to record.
**Commit:** block 113 phase 1. **Recorded:** 2026-09-05.

## The conflict

The ruling names five stages. Two of them are observable from where this client
sits: the provider's search-result block says what came back, and the citing
text block says what the prose cited. The other three are not.

- **fetched** — the search runs *inside* the provider. Nikodemus never issues
  the request, never sees a status code, never holds the bytes.
- **examined** — what entered the model's context, and what it read there, is
  not reported in the response at any level of detail.
- **anchored** — on the provider route Nikodemus anchors nothing. This one is
  observable and its value is always the same: none.

## Why fields were not created for them

A schema field is a promise that a value can be filled. Three of the five could
only ever be filled with `0`, `null` or `unknown`, and `0` is the dangerous one:
it reads as a measurement. The record would then contain three columns that look
like counts and are not, and the first surface to sum them would be printing a
lie with a straight face — which is precisely the failure mode the ruling was
written to end.

So the distinction the ruling asks for is kept **in the presentation**, where
all five facts appear by name and in the same order on every panel, and the
three unobservable ones say *not applicable*, *unknown* and *none* in words.
The record carries only what was observed.

## What this costs

If the provider ever begins reporting fetches or context admissions, the record
has no place to put them and the schema will need a versioned addition. That is
a smaller cost than shipping three fields that can only ever hold a fiction, and
it is a recorded cost rather than a discovered one.

## The dedup defect this record replaces

The first version of the collector deduplicated by URL keeping the first label
seen, in a single ordered walk. Because the provider's documented response puts
the search-result block before the citing text block, the citation observation
was discarded on **every run this application has ever made**: 3,781 rows, all
`searched`, none `cited`. The correction is two independent passes and an
`observed` list. **No historical row is rewritten**, and the surfaces read a
missing `observed` as *not recorded* rather than as *not cited*.
