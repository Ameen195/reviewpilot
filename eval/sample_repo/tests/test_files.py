from shop.files import read_lines, write_report


def test_report_roundtrip(tmp_path):
    p = tmp_path / "r.csv"
    write_report(p, [["ana", 3]])
    assert read_lines(p) == ["name,total", "ana,3"]
