from open_work_hub_api.domains.recording.chunk_sequence import chunk_sequences, plan_chunk_assembly


def test_chunk_sequences_ignores_non_chunk_metadata_and_sorts_numeric_keys() -> None:
    assert chunk_sequences(
        {
            "10": {"size": 1},
            "2": {"size": 1},
            "__title": "Meeting",
            "not-a-number": {"size": 1},
        }
    ) == [2, 10]


def test_plan_chunk_assembly_reports_no_chunks_before_any_upload() -> None:
    assert plan_chunk_assembly(chunks_meta={}, highest_seq=-1).error == ("no_chunks_to_finalize")


def test_plan_chunk_assembly_requires_contiguous_numeric_chunks() -> None:
    missing_middle = plan_chunk_assembly(
        chunks_meta={"0": {}, "2": {}},
        highest_seq=2,
    )

    assert missing_middle.sequences == [0, 2]
    assert missing_middle.error == "chunks_incomplete"


def test_plan_chunk_assembly_returns_ordered_sequences_when_complete() -> None:
    plan = plan_chunk_assembly(
        chunks_meta={"2": {}, "0": {}, "1": {}, "__title": "Meeting"},
        highest_seq=2,
    )

    assert plan.sequences == [0, 1, 2]
    assert plan.error is None
