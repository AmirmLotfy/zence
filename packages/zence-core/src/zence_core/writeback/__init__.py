"""Writing decisions back into DataHub.

One document per session, upserted under a deterministic id so finalizing twice
updates one record rather than creating two.
"""

from zence_core.writeback.document import (
    DOCUMENT_SUBTYPE,
    PROVENANCE,
    REVIEW_PROPERTY,
    WriteBackResult,
    idempotency_key,
    write_session_document,
)

__all__ = [
    "DOCUMENT_SUBTYPE",
    "PROVENANCE",
    "REVIEW_PROPERTY",
    "WriteBackResult",
    "idempotency_key",
    "write_session_document",
]
