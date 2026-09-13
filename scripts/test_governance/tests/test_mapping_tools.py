"""test_mapping_tools.py — 测试治理脚本的单测（issue #223）。

运行：
    server/.venv/bin/python -m pytest scripts/test_governance/tests -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PKG_DIR))

import backfill_pending_mappings as backfill  # noqa: E402
import check_mapping_consistency as checker  # noqa: E402


def write_go_test_file(root: Path, rel: str, test_names) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"func {name}(t *testing.T) {{}}\n" for name in test_names)
    path.write_text("package sample\n\nimport \"testing\"\n\n" + body, encoding="utf-8")


def make_map(tmp_path: Path, mappings: dict, total=None) -> Path:
    map_path = tmp_path / "zentao_testcase_map.json"
    map_path.write_text(
        json.dumps({"total": len(mappings) if total is None else total, "mappings": mappings}, indent=2),
        encoding="utf-8",
    )
    return map_path


def active_entry(tc_id: str, zentao_id: int, file: str, name: str) -> dict:
    return {
        "tc_local_id": tc_id,
        "zentao_id": zentao_id,
        "sync_status": "active",
        "domain": "sample",
        "source": "sample",
        "test_name": name,
        "file": file,
        "priority": "P2",
    }


# ---------------------------------------------------------------- checker


def test_collect_go_tests(tmp_path):
    write_go_test_file(tmp_path, "pkg/a_test.go", ["TestOne", "TestTwo"])
    (tmp_path / "pkg" / "helpers.go").write_text("func TestNotATest() {}\n", encoding="utf-8")

    tests = checker.collect_go_tests(tmp_path)
    assert set(tests) == {"pkg/a_test.go::TestOne", "pkg/a_test.go::TestTwo"}
    assert tests["pkg/a_test.go::TestOne"].line > 0


def test_check_mapping_clean(tmp_path):
    write_go_test_file(tmp_path, "pkg/a_test.go", ["TestOne", "TestTwo"])
    make_map(
        tmp_path,
        {
            "pkg/a_test.go::TestOne": active_entry("TC-A0001", 100, "pkg/a_test.go", "TestOne"),
            "pkg/a_test.go::TestTwo": active_entry("TC-A0002", 101, "pkg/a_test.go", "TestTwo"),
        },
    )
    report = checker.check_mapping("execution_agent", tmp_path)
    assert report.ok, report.format()
    assert report.active == 2
    assert report.pending == 0


def test_check_mapping_detects_all_inconsistencies(tmp_path):
    write_go_test_file(
        tmp_path,
        "pkg/a_test.go",
        ["TestOne", "TestTwo", "TestUnmapped", "TestPendingBad", "TestActiveNoId"],
    )
    make_map(
        tmp_path,
        {
            # 失效：文件里没有 TestGone
            "pkg/a_test.go::TestGone": active_entry("TC-A0001", 100, "pkg/a_test.go", "TestGone"),
            # 未映射：TestUnmapped 不在 map
            "pkg/a_test.go::TestOne": active_entry("TC-A0003", 100, "pkg/a_test.go", "TestOne"),
            # key 与 value.file/test_name 不一致 + tc_local_id 重复
            "pkg/a_test.go::TestTwo": {
                **active_entry("TC-A0003", 101, "other_test.go", "TestRenamed"),
            },
            # pending 但带 zentao_id
            "pkg/a_test.go::TestPendingBad": {
                **active_entry("TC-A0004", 999, "pkg/a_test.go", "TestPendingBad"),
                "sync_status": "pending",
            },
            # active 但缺 zentao_id
            "pkg/a_test.go::TestActiveNoId": {
                **active_entry("TC-A0005", 0, "pkg/a_test.go", "TestActiveNoId"),
                "zentao_id": None,
            },
        },
        total=99,
    )

    report = checker.check_mapping("execution_agent", tmp_path)

    assert not report.ok
    assert "pkg/a_test.go::TestGone" in report.stale
    assert report.unmapped == ["pkg/a_test.go::TestUnmapped"]
    assert "TC-A0003" in report.duplicate_tc_local_ids
    assert len(report.key_value_mismatch) == 1
    assert "pkg/a_test.go::TestPendingBad" in report.pending_with_zentao_id
    assert "pkg/a_test.go::TestActiveNoId" in report.active_without_zentao_id
    assert report.total_mismatch
    assert "FAIL" in report.format()


def test_check_mapping_detects_active_file_mismatch(tmp_path):
    write_go_test_file(tmp_path, "pkg/a_test.go", ["TestOne"])
    make_map(
        tmp_path,
        {"pkg/a_test.go::TestOne": active_entry("TC-A0001", 100, "pkg/a_test.go", "TestOne")},
    )
    (tmp_path / "TEST_CASE_ACTIVE.json").write_text(
        json.dumps([{"id": "TC-A9999"}, {"id": "TC-A0001"}]), encoding="utf-8"
    )

    report = checker.check_mapping(
        "execution_agent", tmp_path, active_path=tmp_path / "TEST_CASE_ACTIVE.json"
    )
    assert not report.ok
    assert report.active_file_extra == ["TC-A9999"]
    assert report.active_file_missing == []


def test_checker_cli_exit_codes(tmp_path):
    write_go_test_file(tmp_path, "pkg/a_test.go", ["TestOne"])
    make_map(
        tmp_path,
        {"pkg/a_test.go::TestOne": active_entry("TC-A0001", 100, "pkg/a_test.go", "TestOne")},
    )
    assert checker.main(["execution_agent", "--source-root", str(tmp_path)]) == 0

    make_map(tmp_path, {}, total=0)
    assert checker.main(["execution_agent", "--source-root", str(tmp_path)]) == 1


def test_real_execution_agent_mapping_is_consistent():
    """仓库真实数据必须通过校验（E 阶段验收命令的自动化版本）。"""
    assert (
        checker.main(
            ["execution_agent", "--source-root", str(REPO_ROOT / "execution_agent")]
        )
        == 0
    )


# ---------------------------------------------------------------- pytest 解析器


def write_pytest_file(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_collect_pytest_tests_keys_and_markers(tmp_path):
    write_pytest_file(
        tmp_path,
        "svc/test_sample.py",
        """
import pytest

@pytest.mark.zentao("TC-S0001", domain="server/svc", priority="P1")
def test_unique_name():
    assert True

class TestAlpha:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0002", domain="server/svc", priority="P2")
    async def test_same_name(self):
        assert True

    @pytest.mark.parametrize("x", [1, 2])
    @pytest.mark.zentao("TC-S0003", domain="server/svc", priority="P2")
    def test_parametrized(self, x):
        assert x

class TestBeta:
    @pytest.mark.zentao("TC-S0004", domain="server/svc", priority="P2")
    def test_same_name(self):
        assert True
""",
    )
    write_pytest_file(tmp_path, "svc/helper.py", "def test_not_collected():\n    pass\n")

    tests = checker.collect_pytest_tests(tmp_path)
    assert set(tests) == {
        "svc/test_sample.py::test_unique_name",
        "svc/test_sample.py::TestAlpha::test_same_name",
        "svc/test_sample.py::test_parametrized",
        "svc/test_sample.py::TestBeta::test_same_name",
    }
    assert tests["svc/test_sample.py::TestAlpha::test_same_name"].markers == ("TC-S0002",)
    assert tests["svc/test_sample.py::test_unique_name"].priority == "P1"
    assert tests["svc/test_sample.py::test_parametrized"].markers == ("TC-S0003",)


def test_check_server_mapping_clean_and_marker_alignment(tmp_path):
    write_pytest_file(
        tmp_path,
        "svc/test_sample.py",
        """
import pytest

@pytest.mark.zentao("TC-S0001", domain="server/svc", priority="P1")
def test_one():
    assert True

def test_two():
    assert True
""",
    )
    make_map(
        tmp_path,
        {
            "svc/test_sample.py::test_one": active_entry("TC-S0001", 100, "svc/test_sample.py", "test_one"),
            "svc/test_sample.py::test_two": {
                **active_entry("TC-S0002", 101, "svc/test_sample.py", "test_two"),
                "zentao_id": None,
                "sync_status": "pending",
            },
        },
    )
    report = checker.check_mapping("server", tmp_path)
    assert report.ok, report.format()
    assert report.active == 1 and report.pending == 1
    assert report.marker_mismatch == []


def test_check_server_mapping_detects_marker_mismatch(tmp_path):
    write_pytest_file(
        tmp_path,
        "svc/test_sample.py",
        """
import pytest

@pytest.mark.zentao("TC-S9999", domain="server/svc", priority="P1")
def test_one():
    assert True
""",
    )
    make_map(
        tmp_path,
        {"svc/test_sample.py::test_one": active_entry("TC-S0001", 100, "svc/test_sample.py", "test_one")},
    )
    report = checker.check_mapping("server", tmp_path)
    assert not report.ok
    assert len(report.marker_mismatch) == 1
    assert "TC-S9999" in report.marker_mismatch[0]


def test_check_active_file_field_mismatch(tmp_path):
    write_pytest_file(
        tmp_path,
        "svc/test_sample.py",
        """
@pytest.mark.zentao("TC-S0001", domain="server/svc", priority="P1")
def test_one():
    assert True
""",
    )
    make_map(
        tmp_path,
        {"svc/test_sample.py::test_one": active_entry("TC-S0001", 100, "svc/test_sample.py", "test_one")},
    )
    (tmp_path / "TEST_CASE_ACTIVE.json").write_text(
        json.dumps([{"id": "TC-S0001", "file": "wrong.py", "test_name": "test_one"}]), encoding="utf-8"
    )
    report = checker.check_mapping(
        "server", tmp_path, active_path=tmp_path / "TEST_CASE_ACTIVE.json"
    )
    assert not report.ok
    assert len(report.active_file_field_mismatch) == 1


def test_real_server_mapping_is_consistent():
    """server 端真实数据必须通过校验（issue #223 S1 验收命令的自动化版本）。"""
    assert (
        checker.main(["server", "--source-root", str(REPO_ROOT / "server" / "tests")])
        == 0
    )


# ---------------------------------------------------------------- backfill


def make_meta(tc_id="TC-A0076", priority="P1", source="execution_agent", name="TestFoo") -> dict:
    return {
        "tc_local_id": tc_id,
        "zentao_id": None,
        "sync_status": "pending",
        "domain": "execution_agent/agent",
        "source": source,
        "test_name": name,
        "file": "agent/foo_test.go",
        "priority": priority,
    }


def test_find_pending_sorted():
    mappings = {
        "b::TestB": {"sync_status": "pending"},
        "a::TestA": {"sync_status": "pending"},
        "c::TestC": {"sync_status": "active"},
    }
    assert backfill.find_pending(mappings) == ["a::TestA", "b::TestB"]


def test_build_create_args():
    args = backfill.build_create_args(make_meta(priority="P1"), product_id=3)
    assert args[:2] == ["testcase", "create"]
    assert "--productID=3" in args
    assert "--pri=2" in args  # P1 -> Zentao 2
    assert "--type=unit" in args
    assert "--module=0" in args
    assert "--format=json" in args
    title = next(a for a in args if a.startswith("--title="))
    assert "TC-A0076" in title and "TestFoo" in title and "execution_agent" in title


@pytest.mark.parametrize(
    "priority,expected",
    [("P0", 1), ("P1", 2), ("P2", 3), ("P3", 4), ("", 3), ("unknown", 3), (None, 3)],
)
def test_priority_to_zentao(priority, expected):
    assert backfill.priority_to_zentao(priority) == expected


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ('{"id": 12345}', 12345),
        ('{"data": {"id": 777}}', 777),
        ('{"id": "888"}', 888),
        ("Created testcase ID: 4321", 4321),
        ("id=5555", 5555),
        ("no id here", None),
        ("", None),
        ("{not-json", None),
    ],
)
def test_parse_created_id(stdout, expected):
    assert backfill.parse_created_id(stdout) == expected


def test_backfill_updates_pending_and_keeps_failures(tmp_path):
    mappings = {
        "agent/a_test.go::TestA": make_meta("TC-A0076", "P1", name="TestA"),
        "agent/b_test.go::TestB": make_meta("TC-A0077", "P2", name="TestB"),
        "agent/c_test.go::TestC": {
            **make_meta("TC-A0001", "P2", name="TestC"),
            "zentao_id": 1429,
            "sync_status": "active",
        },
    }
    map_path = make_map(tmp_path, mappings)
    original_total = json.loads(map_path.read_text())["total"]
    calls = []

    def fake_runner(args):
        calls.append(args)
        if "TC-A0077" in " ".join(args):
            return subprocess.CompletedProcess(args, 1, "", "boom")
        return subprocess.CompletedProcess(args, 0, '{"id": 9001}', "")

    result = backfill.backfill(map_path, product_id=3, runner=fake_runner)

    assert len(calls) == 2  # 只处理 pending，active 不再调用
    assert result.created == [("agent/a_test.go::TestA", 9001)]
    assert len(result.failed) == 1 and result.failed[0][0] == "agent/b_test.go::TestB"

    updated = json.loads(map_path.read_text())
    assert updated["total"] == original_total
    assert updated["mappings"]["agent/a_test.go::TestA"]["zentao_id"] == 9001
    assert updated["mappings"]["agent/a_test.go::TestA"]["sync_status"] == "active"
    # 失败条目保持 pending，等待下次重试
    failed = updated["mappings"]["agent/b_test.go::TestB"]
    assert failed["zentao_id"] is None and failed["sync_status"] == "pending"
    # active 条目未被改动
    assert updated["mappings"]["agent/c_test.go::TestC"]["zentao_id"] == 1429


def test_backfill_dry_run_does_not_call_or_write(tmp_path):
    mappings = {"agent/a_test.go::TestA": make_meta("TC-A0076", name="TestA")}
    map_path = make_map(tmp_path, mappings)
    before = map_path.read_text()

    def forbidden_runner(args):  # pragma: no cover - dry-run 不得触达
        raise AssertionError("dry-run 不应调用 zentao CLI")

    result = backfill.backfill(map_path, product_id=3, runner=forbidden_runner, dry_run=True)

    assert result.planned and not result.created and not result.failed
    assert map_path.read_text() == before


def test_backfill_unparseable_output_stays_pending(tmp_path):
    mappings = {"agent/a_test.go::TestA": make_meta("TC-A0076", name="TestA")}
    map_path = make_map(tmp_path, mappings)

    def fake_runner(args):
        return subprocess.CompletedProcess(args, 0, "created something without id", "")

    result = backfill.backfill(map_path, product_id=3, runner=fake_runner)
    assert len(result.failed) == 1
    meta = json.loads(map_path.read_text())["mappings"]["agent/a_test.go::TestA"]
    assert meta["sync_status"] == "pending"


def test_backfill_main_requires_product_id(monkeypatch, tmp_path):
    monkeypatch.delenv("ZENTAO_PRODUCT_ID", raising=False)
    assert backfill.main(["--map", str(make_map(tmp_path, {}))]) == 2


# ------------------------------------------------- backfill server 适配


def test_resolve_map_path_by_source(tmp_path):
    assert backfill.resolve_map_path("server", None, tmp_path) == (
        tmp_path / "server" / "tests" / "zentao_testcase_map.json"
    ).resolve()
    assert backfill.resolve_map_path("execution_agent", None, tmp_path) == (
        tmp_path / "execution_agent" / "zentao_testcase_map.json"
    ).resolve()
    # 显式 --map 优先于 --source
    explicit = tmp_path / "custom.json"
    assert backfill.resolve_map_path("server", str(explicit), tmp_path) == explicit


def test_resolve_map_path_rejects_unknown_source():
    with pytest.raises(ValueError):
        backfill.resolve_map_path("web", None)
    with pytest.raises(ValueError):
        backfill.resolve_map_path(None, None)


def test_backfill_accepts_server_class_qualified_keys(tmp_path):
    """server 端 key 可能是 file.py::Class::method，回填逻辑对 key 保持 opaque。"""
    key = "services/test_plugin_center.py::TestPluginCenterAPI::test_list_plugins_empty"
    meta = make_meta("TC-S3519", "P2", source="server", name="TestPluginCenterAPI::test_list_plugins_empty")
    meta["file"] = "services/test_plugin_center.py"
    map_path = make_map(tmp_path, {key: meta})

    def fake_runner(args):
        return subprocess.CompletedProcess(args, 0, '{"id": 9001}', "")

    result = backfill.backfill(map_path, product_id=3, runner=fake_runner)
    assert result.created == [(key, 9001)]
    title = next(a for a in result.planned[0][1] if a.startswith("--title="))
    assert "TC-S3519" in title and "server" in title

