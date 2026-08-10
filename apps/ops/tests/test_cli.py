from ai_do_ops.cli import list_scenarios


def test_list_scenarios_prints_catalog_results(tmp_path, capsys):
    (tmp_path / "second.json").write_text('{"scenario_id": "beta"}', encoding="utf-8")
    (tmp_path / "first.json").write_text('{"scenario_id": "alpha"}', encoding="utf-8")

    assert list_scenarios(tmp_path) == 0

    captured = capsys.readouterr()
    assert captured.out == "alpha\nbeta\n"
    assert captured.err == ""
