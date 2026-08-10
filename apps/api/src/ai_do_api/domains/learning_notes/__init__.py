"""Personal learning notes.

Each authenticated user can keep up to **one** note per lesson, with a
per-note public/private visibility toggle. Notes are stored as
``NativeDoc`` + ``NativeDocPage`` pairs (no new tables, no Alembic
migration), keyed by ``(owner_id, source_ref='{course_slug}:{lesson_id}')``.

Visibility is encoded in ``NativeDoc.source_kind``:

* ``lesson_note_public``  — visible to every authenticated user
* ``lesson_note_private`` — visible only to the author (admin included
  cannot read it)
"""
