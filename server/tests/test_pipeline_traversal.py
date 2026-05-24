import pytest
from pathlib import Path
from taskpps.loaders.pipeline_loader import PipelineLoader


def test_path_traversal_upwards(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True)
    outside_file = tmp_path / "secret.yaml"
    outside_file.write_text("name: secret\noptions: {}\ntasks:\n  - name: t1\n    command: echo secret\n")
    loader = PipelineLoader(pipelines_dir)
    with pytest.raises(FileNotFoundError, match="路径遍历|流水线文件路径"):
        loader.load("../secret.yaml")


def test_path_traversal_deep(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True)
    loader = PipelineLoader(pipelines_dir)
    with pytest.raises(FileNotFoundError, match="路径遍历|流水线文件路径"):
        loader.load("../../etc/passwd")


def test_path_traversal_absolute(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True)
    loader = PipelineLoader(pipelines_dir)
    with pytest.raises(FileNotFoundError, match="路径遍历|流水线文件路径"):
        loader.load("/etc/passwd")


def test_path_traversal_symlink(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True)
    target = tmp_path / "actual.yaml"
    target.write_text("name: actual\noptions: {}\ntasks:\n  - name: t1\n    command: echo actual\n")
    link = pipelines_dir / "link.yaml"
    link.symlink_to(target)

    loader = PipelineLoader(pipelines_dir)

    if str(link.resolve()).startswith(str(pipelines_dir.resolve())):
        spec = loader.load("link.yaml")
        assert spec.name == "actual"
    else:
        with pytest.raises(FileNotFoundError, match="路径遍历|流水线文件路径"):
            loader.load("link.yaml")


def test_valid_file_passes(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True)
    valid_file = pipelines_dir / "valid.yaml"
    valid_file.write_text(
        "name: valid\n"
        "options: {}\n"
        "tasks:\n"
        "  - name: t1\n"
        "    command: echo ok\n"
    )
    loader = PipelineLoader(pipelines_dir)
    spec = loader.load("valid.yaml")
    assert spec.name == "valid"


def test_path_traversal_oserror(tmp_path):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True)
    loader = PipelineLoader(pipelines_dir)
    with pytest.raises(FileNotFoundError):
        loader.load("\x00invalid")
