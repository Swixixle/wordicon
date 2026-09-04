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
