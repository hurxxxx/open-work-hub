from open_alm_api.domains.files.archive_planner import (
    ArchivePlanFile,
    ArchivePlanFolder,
    PlannedArchiveEntry,
    plan_archive_entries,
)


def folder(
    id: str,
    name: str,
    *,
    parent_id: str | None = None,
) -> ArchivePlanFolder:
    return ArchivePlanFolder(id=id, parent_id=parent_id, name=name)


def file(
    id: str,
    filename: str,
    *,
    folder_id: str | None = None,
) -> ArchivePlanFile:
    return ArchivePlanFile(id=id, folder_id=folder_id, filename=filename)


def test_selected_folder_plans_directories_and_files_in_stable_path_order() -> None:
    entries = plan_archive_entries(
        selected_folder_ids={"root"},
        folders=[
            folder("root", "Project"),
            folder("notes", "Notes", parent_id="root"),
            folder("assets", "Assets", parent_id="root"),
        ],
        folder_files=[
            file("readme", "readme.txt", folder_id="root"),
            file("asset", "logo.png", folder_id="assets"),
            file("note", "daily.txt", folder_id="notes"),
        ],
        selected_files=[],
    )

    assert entries == [
        PlannedArchiveEntry("Project/", None),
        PlannedArchiveEntry("Project/Assets/", None),
        PlannedArchiveEntry("Project/Notes/", None),
        PlannedArchiveEntry("Project/readme.txt", "readme"),
        PlannedArchiveEntry("Project/Assets/logo.png", "asset"),
        PlannedArchiveEntry("Project/Notes/daily.txt", "note"),
    ]


def test_selected_folder_and_explicit_child_file_include_child_once() -> None:
    entries = plan_archive_entries(
        selected_folder_ids={"root"},
        folders=[folder("root", "Project")],
        folder_files=[file("nested", "nested.txt", folder_id="root")],
        selected_files=[file("nested", "nested.txt", folder_id="root")],
    )

    assert entries == [
        PlannedArchiveEntry("Project/", None),
        PlannedArchiveEntry("Project/nested.txt", "nested"),
    ]


def test_colliding_sanitized_file_paths_get_deterministic_suffixes() -> None:
    entries = plan_archive_entries(
        selected_folder_ids=set(),
        folders=[],
        folder_files=[],
        selected_files=[
            file("first", "..\\evil.txt"),
            file("second", "C:/evil.txt"),
            file("third", "evil.txt"),
        ],
    )

    assert entries == [
        PlannedArchiveEntry("evil.txt", "first"),
        PlannedArchiveEntry("evil (2).txt", "second"),
        PlannedArchiveEntry("evil (3).txt", "third"),
    ]


def test_empty_folder_selection_still_emits_directory_entry() -> None:
    entries = plan_archive_entries(
        selected_folder_ids={"empty"},
        folders=[folder("empty", "Empty")],
        folder_files=[],
        selected_files=[],
    )

    assert entries == [PlannedArchiveEntry("Empty/", None)]


def test_duplicate_explicit_file_ids_are_deduped_in_stable_order() -> None:
    entries = plan_archive_entries(
        selected_folder_ids=set(),
        folders=[],
        folder_files=[],
        selected_files=[
            file("first", "first.txt"),
            file("first", "first.txt"),
            file("second", "second.txt"),
        ],
    )

    assert entries == [
        PlannedArchiveEntry("first.txt", "first"),
        PlannedArchiveEntry("second.txt", "second"),
    ]
