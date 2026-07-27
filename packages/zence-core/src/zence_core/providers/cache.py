"""A small TTL cache for resolved evidence.

A PreToolUse hook has a budget of roughly 2.5 seconds and Claude will often
reference the same three tables a dozen times in one turn. Without caching, each
mention costs a round trip and the session feels broken.

Two decisions worth stating:

* **Failures are cached, briefly.** When DataHub is down, every reference in a
  turn would otherwise wait for its own timeout, and a 30-second hook budget
  disappears in three lookups. Negative entries expire much faster than positive
  ones so recovery is quick.

* **Nothing is cached to disk.** The cache lives for the life of one hook
  process. Evidence on disk would be evidence that could go stale silently, and
  a decision made from a stale catalog is exactly the failure Zence is supposed
  to prevent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from zence_core.schemas import Evidence, EvidenceStatus

#: How long a successful lookup stays usable.
DEFAULT_TTL_SECONDS = 60.0

#: How long a failure stays usable. Deliberately short — a recovered DataHub
#: should be noticed within a turn or two, not a minute later.
DEFAULT_NEGATIVE_TTL_SECONDS = 5.0


@dataclass(slots=True)
class _Entry:
    evidence: Evidence
    expires_at: float


@dataclass(slots=True)
class EvidenceCache:
    """In-process, time-bounded, keyed by the reference text."""

    ttl_seconds: float = DEFAULT_TTL_SECONDS
    negative_ttl_seconds: float = DEFAULT_NEGATIVE_TTL_SECONDS
    _entries: dict[str, _Entry] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    @staticmethod
    def key(raw_text: str) -> str:
        return raw_text.strip().lower()

    def _ttl_for(self, evidence: Evidence) -> float:
        if evidence.status is EvidenceStatus.RESOLVED:
            return self.ttl_seconds
        return self.negative_ttl_seconds

    def get(self, raw_text: str) -> Evidence | None:
        entry = self._entries.get(self.key(raw_text))
        if entry is None:
            self.misses += 1
            return None

        if time.monotonic() >= entry.expires_at:
            del self._entries[self.key(raw_text)]
            self.misses += 1
            return None

        self.hits += 1
        return entry.evidence

    def put(self, raw_text: str, evidence: Evidence) -> None:
        self._entries[self.key(raw_text)] = _Entry(
            evidence=evidence,
            expires_at=time.monotonic() + self._ttl_for(evidence),
        )

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
