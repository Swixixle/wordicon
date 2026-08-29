"""
Wordicon Sovereign Corpus — Phase 0/1 reference implementation.

This package implements the vertical slice authorized by blueprint v1.2 §23:
schemas, permission profiles, a generalized dependency/revocation graph, a
mocked model gateway, one Forge operation, Bone claim validation, and
private/public receipt generation with revocation annotation.

Nothing in this package sends data to a real external model, ingests real
private material, or exposes a public interface. See docs/CHANGELOG.md and
the final delivery report for what remains out of scope.
"""

__version__ = "0.1.0"
