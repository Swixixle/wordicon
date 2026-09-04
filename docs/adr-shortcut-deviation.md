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
