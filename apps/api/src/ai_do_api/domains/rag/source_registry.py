from __future__ import annotations

RAG_SCOPE_OFFICIAL = "official"
RAG_SCOPE_PERSONAL = "personal"
RAG_SCOPE_EXCLUDED = "excluded"
RAG_SCOPE_VALUES = frozenset(
    {
        RAG_SCOPE_OFFICIAL,
        RAG_SCOPE_PERSONAL,
        RAG_SCOPE_EXCLUDED,
    }
)

OFFICIAL_NATIVE_DOC_SOURCE_KIND_LABELS = {
    "manual": "Docs / Manual",
    "meeting_notes": "Docs / Meeting Notes",
    "app_generated": "Meeting / Minutes",
    "raw_transcript": "Meeting / Transcript",
    "minutes": "Meeting / Minutes",
}

OFFICIAL_NATIVE_DOC_SOURCE_KINDS = frozenset(OFFICIAL_NATIVE_DOC_SOURCE_KIND_LABELS)
