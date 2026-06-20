from pathlib import Path

from mikraw import batch
from mikraw.cli import main
from mikraw.errors import Status
from mikraw.pipeline import Options, convert_one, output_path


def _touch(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")


def test_discover_filters_to_raw(tmp_path):
    _touch(tmp_path / "a.RW2")
    _touch(tmp_path / "b.rw2")
    _touch(tmp_path / "note.txt")
    _touch(tmp_path / "c.jpg")
    found = batch.discover([str(tmp_path)], recursive=False)
    names = sorted(Path(f).name.lower() for f in found)
    assert names == ["a.rw2", "b.rw2"]


def test_discover_recursive(tmp_path):
    _touch(tmp_path / "top.RW2")
    _touch(tmp_path / "sub" / "deep.ARW")
    flat = batch.discover([str(tmp_path)], recursive=False)
    deep = batch.discover([str(tmp_path)], recursive=True)
    assert len(flat) == 1
    assert len(deep) == 2


def test_discover_glob_and_dedup(tmp_path):
    _touch(tmp_path / "a.RW2")
    pattern = str(tmp_path / "*.RW2")
    # Same file reachable via dir + glob should appear once.
    found = batch.discover([str(tmp_path), pattern], recursive=False)
    assert len(found) == 1


def test_output_path_with_suffix(tmp_path):
    opts = Options(output_dir=str(tmp_path), suffix="_conv")
    out = output_path("/photos/DSC001.RW2", opts)
    assert out == tmp_path / "DSC001_conv.jpg"


def test_skip_when_output_exists(tmp_path):
    opts = Options(output_dir=str(tmp_path), overwrite=False)
    existing = output_path("X.RW2", opts)
    existing.write_bytes(b"")
    res = convert_one("X.RW2", opts)
    assert res.status is Status.SKIPPED


def test_dry_run_returns_zero(tmp_path, capsys):
    _touch(tmp_path / "a.RW2")
    rc = main(["--dry-run", "-o", str(tmp_path / "out"), str(tmp_path)])
    assert rc == 0
    assert "would be converted" in capsys.readouterr().out


def test_no_files_returns_one(tmp_path):
    rc = main(["-o", str(tmp_path), str(tmp_path / "empty")])
    assert rc == 1


def test_bad_quality_returns_two(tmp_path):
    _touch(tmp_path / "a.RW2")
    rc = main(["-q", "150", str(tmp_path)])
    assert rc == 2


def test_tiff_output_path(tmp_path):
    opts = Options(output_dir=str(tmp_path), output_format="tiff")
    out = output_path("/photos/DSC001.RW2", opts)
    assert out.suffix == ".tif"


def test_list_profiles_exits_zero(capsys):
    rc = main(["--list-profiles"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "vibrant" in out
    assert "neutral" in out
    assert "monochrome" in out


def test_profile_neutral_dry_run(tmp_path, capsys):
    _touch(tmp_path / "a.RW2")
    rc = main(["--dry-run", "--profile", "neutral", "-o", str(tmp_path / "out"), str(tmp_path)])
    assert rc == 0


def test_profile_override_contrast(tmp_path, capsys):
    _touch(tmp_path / "a.RW2")
    # neutral profile + explicit --contrast 2.0 should not crash
    rc = main(["--dry-run", "--profile", "neutral", "--contrast", "2.0",
               "-o", str(tmp_path / "out"), str(tmp_path)])
    assert rc == 0


def test_no_inputs_returns_two(capsys):
    rc = main([])
    assert rc == 2


def test_no_autoexp_flag_accepted(tmp_path):
    _touch(tmp_path / "a.RW2")
    rc = main(["--dry-run", "--no-autoexp", "-o", str(tmp_path / "out"), str(tmp_path)])
    assert rc == 0


def test_gpu_flag_accepted(tmp_path):
    _touch(tmp_path / "a.RW2")
    rc = main(["--dry-run", "--gpu", "-o", str(tmp_path / "out"), str(tmp_path)])
    assert rc == 0
