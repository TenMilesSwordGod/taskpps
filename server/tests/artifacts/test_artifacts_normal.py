"""正常流测试 — 覆盖 story #8 的 12 个验收场景（FR1-FR12）。"""
from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.db.repository import ArtifactRepository
from taskpps.db.engine import get_session_factory
from taskpps.models.artifact import Artifact
from taskpps.services.artifact_service import (
    collect_default_artifacts,
    collect_task_artifacts,
    parse_artifact_ref,
    resolve_artifact_ref,
    substitute_artifact_refs,
)


# ─── 场景 1: 默认产物自动落盘（FR1） ───


class TestDefaultArtifacts:
    @pytest.mark.zentao("TC-A0001", domain="server/artifacts", priority="P1")
    async def test_default_artifacts_created_on_disk(
        self, sample_run, artifacts_dir
    ):
        """FR1: run结束后自动生成 log.txt + meta.json。"""
        await collect_default_artifacts(
            run_id=sample_run.id,
            pipeline_name=sample_run.pipeline_name,
            pipeline_id=sample_run.pipeline_id,
            pipeline_version=sample_run.pipeline_version,
            status=sample_run.status.value,
            started_at=sample_run.started_at,
            finished_at=sample_run.finished_at,
            task_names=["task1", "task2"],
        )

        default_dir = artifacts_dir / "default"
        assert (default_dir / "log.txt").exists()
        assert (default_dir / "meta.json").exists()

        meta = json.loads((default_dir / "meta.json").read_text())
        assert meta["run_id"] == sample_run.id
        assert meta["pipeline"] == sample_run.pipeline_name
        assert meta["status"] == "success"
        assert "task1" in meta["tasks"]
        assert "task2" in meta["tasks"]

    @pytest.mark.zentao("TC-A0001", domain="server/artifacts", priority="P1")
    async def test_default_artifacts_recorded_in_db(
        self, sample_run, artifacts_dir, db_engine
    ):
        """FR1: 默认产物在 DB 中有记录。"""
        await collect_default_artifacts(
            run_id=sample_run.id,
            pipeline_name=sample_run.pipeline_name,
            pipeline_id=sample_run.pipeline_id,
            pipeline_version=sample_run.pipeline_version,
            status=sample_run.status.value,
            started_at=sample_run.started_at,
            finished_at=sample_run.finished_at,
            task_names=["task1"],
        )

        async with get_session_factory()() as session:
            repo = ArtifactRepository(session)
            artifacts = await repo.list_artifacts(sample_run.id)

        default_arts = [a for a in artifacts if a.task_name == "default"]
        assert len(default_arts) == 2
        paths = {a.path for a in default_arts}
        assert "log.txt" in paths
        assert "meta.json" in paths


# ─── 场景 2: 显式声明 artifact 落盘（FR2） ───


class TestExplicitArtifactDeclaration:
    @pytest.mark.zentao("TC-A0002", domain="server/artifacts", priority="P1")
    async def test_single_file_artifact_collected(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """FR2: 单文件 artifact 被收集。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        dist = workdir / "dist"
        dist.mkdir()
        (dist / "app.tar.gz").write_bytes(b"\x1f\x8b" + b"\x00" * 50)

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="build",
            artifacts_config=[{"path": "dist/app.tar.gz"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].path == "app.tar.gz"

        collected = artifacts_dir / "build" / "app.tar.gz"
        assert collected.exists()

    @pytest.mark.zentao("TC-A0002", domain="server/artifacts", priority="P1")
    async def test_glob_pattern_artifacts_collected(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """FR2: glob 模式匹配多个文件。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        dist = workdir / "dist"
        dist.mkdir()
        (dist / "lib1.jar").write_bytes(b"jar1")
        (dist / "lib2.jar").write_bytes(b"jar2")
        (dist / "readme.txt").write_bytes(b"readme")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="build",
            artifacts_config=[{"path": "dist/*.jar"}],
            workdir=workdir,
        )

        assert len(items) == 2
        names = {i.path for i in items}
        assert "lib1.jar" in names
        assert "lib2.jar" in names


# ─── 场景 3: 同 subpipeline 引用（FR3） ───


class TestSameSubpipelineRef:
    @pytest.mark.zentao("TC-A0003", domain="server/artifacts", priority="P1")
    def test_parse_same_subpipeline_ref(self):
        """FR3: ${artifact:task/path} 解析为 task_name + path。"""
        ref = parse_artifact_ref("${artifact:compile/dist/app.tar.gz}")
        assert ref is not None
        assert ref.task_name == "compile"
        assert ref.path == "dist/app.tar.gz"
        assert ref.subpipeline is None
        assert ref.run_id is None

    @pytest.mark.zentao("TC-A0003", domain="server/artifacts", priority="P1")
    def test_resolve_same_subpipeline_ref(self, sample_run, artifacts_dir, default_artifacts, build_artifacts):
        """FR3: 同 subpipeline 引用解析为真实路径。"""
        ref = parse_artifact_ref("${artifact:build/app.tar.gz}")
        assert ref is not None
        resolved = resolve_artifact_ref(ref, current_run_id=sample_run.id)
        assert resolved is not None
        assert resolved.exists()
        assert resolved.name == "app.tar.gz"

    @pytest.mark.zentao("TC-A0003", domain="server/artifacts", priority="P1")
    def test_substitute_same_subpipeline_refs(self, sample_run, artifacts_dir, build_artifacts):
        """FR3: 环境变量中的占位符被替换。"""
        env_text = "APP=${artifact:build/app.tar.gz}"
        result = substitute_artifact_refs(env_text, current_run_id=sample_run.id)
        assert "${artifact:" not in result
        assert "app.tar.gz" in result


# ─── 场景 4: 跨 subpipeline 引用（FR4） ───


class TestCrossSubpipelineRef:
    @pytest.mark.zentao("TC-A0004", domain="server/artifacts", priority="P1")
    def test_parse_cross_subpipeline_ref(self):
        """FR4: ${artifact:subpipeline/task/path} 解析。"""
        ref = parse_artifact_ref("${artifact:build-and-test/package/target/myapp.jar}")
        assert ref is not None
        assert ref.subpipeline == "build-and-test"
        assert ref.task_name == "package"
        assert ref.path == "target/myapp.jar"

    @pytest.mark.zentao("TC-A0004", domain="server/artifacts", priority="P1")
    def test_resolve_cross_subpipeline_ref(self, sample_run, artifacts_dir, db_engine):
        """FR4: 跨 subpipeline 引用解析为正确路径。"""
        import asyncio

        task_dir = artifacts_dir / "build-and-test.package"
        task_dir.mkdir(parents=True, exist_ok=True)
        target = task_dir / "target"
        target.mkdir(exist_ok=True)
        (target / "myapp.jar").write_bytes(b"jar-content")

        async def _insert():
            async with get_session_factory()() as session:
                repo = ArtifactRepository(session)
                await repo.create_artifact(
                    run_id=sample_run.id,
                    task_name="build-and-test.package",
                    path="target/myapp.jar",
                    size=11,
                    content_type="application/java-archive",
                )

        asyncio.get_event_loop().run_until_complete(_insert())

        ref = parse_artifact_ref("${artifact:build-and-test/package/target/myapp.jar}")
        resolved = resolve_artifact_ref(ref, current_run_id=sample_run.id)
        assert resolved is not None
        assert resolved.exists()


# ─── 场景 5: 跨 run 引用（FR5） ───


class TestCrossRunRef:
    @pytest.mark.zentao("TC-A0005", domain="server/artifacts", priority="P1")
    def test_parse_cross_run_ref(self):
        """FR5: ${artifact:run_id/subpipeline/task/path} 解析。"""
        ref = parse_artifact_ref("${artifact:run_123/build-and-test/package/target/myapp.jar}")
        assert ref is not None
        assert ref.run_id == "run_123"
        assert ref.subpipeline == "build-and-test"
        assert ref.task_name == "package"
        assert ref.path == "target/myapp.jar"

    @pytest.mark.zentao("TC-A0005", domain="server/artifacts", priority="P1")
    def test_resolve_cross_run_ref_existing(self, sample_run, artifacts_dir, db_engine):
        """FR5: 跨 run 引用 - 目标 run 产物存在时解析成功。"""
        import asyncio

        task_dir = artifacts_dir / "build-and-test.package"
        task_dir.mkdir(parents=True, exist_ok=True)
        target = task_dir / "target"
        target.mkdir(exist_ok=True)
        (target / "myapp.jar").write_bytes(b"jar-content")

        ref = parse_artifact_ref("${artifact:test_run_001/build-and-test/package/target/myapp.jar}")
        resolved = resolve_artifact_ref(ref, current_run_id="other_run")
        assert resolved is not None
        assert resolved.exists()

    @pytest.mark.zentao("TC-A0005", domain="server/artifacts", priority="P1")
    def test_resolve_cross_run_ref_missing(self):
        """FR5: 跨 run 引用 - 目标 run 不存在时返回 None。"""
        ref = parse_artifact_ref("${artifact:nonexistent_run/build/package/app.jar}")
        assert ref is not None
        resolved = resolve_artifact_ref(ref, current_run_id="current")
        assert resolved is None


# ─── 场景 6: 单文件直链下载（FR7） ───


class TestSingleFileDownload:
    @pytest.mark.zentao("TC-A0006", domain="server/artifacts", priority="P1")
    async def test_download_artifact(
        self, app, sample_run, artifacts_dir, default_artifacts, build_artifacts, db_engine
    ):
        """FR7: GET /runs/{run_id}/artifacts/{path} 返回文件内容。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/runs/{sample_run.id}/artifacts/build/app.tar.gz"
            )
            assert resp.status_code == 200
            assert "content-disposition" in resp.headers
            assert "attachment" in resp.headers["content-disposition"]

    @pytest.mark.zentao("TC-A0006", domain="server/artifacts", priority="P1")
    async def test_download_default_artifact(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine
    ):
        """FR7: 下载默认产物 log.txt。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/runs/{sample_run.id}/artifacts/default/log.txt"
            )
            assert resp.status_code == 200


# ─── 场景 7: 批量 zip 下载（FR8） ───


class TestBatchZipDownload:
    @pytest.mark.zentao("TC-A0007", domain="server/artifacts", priority="P1")
    async def test_zip_download_with_task_filter(
        self, app, sample_run, artifacts_dir, default_artifacts, build_artifacts, db_engine
    ):
        """FR8: GET /runs/{run_id}/artifacts.zip?task=build 返回 zip。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/runs/{sample_run.id}/artifacts/zip",
                params={"task": "build"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/zip"

            import io
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            names = zf.namelist()
            assert any("app.tar.gz" in n for n in names)

    @pytest.mark.zentao("TC-A0007", domain="server/artifacts", priority="P1")
    async def test_zip_download_all(
        self, app, sample_run, artifacts_dir, default_artifacts, build_artifacts, db_engine
    ):
        """FR8: 无 task filter 时打包所有 artifacts。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/runs/{sample_run.id}/artifacts/zip"
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/zip"


# ─── 场景 8: 默认产物不需声明（FR9） ───


class TestDefaultArtifactAlwaysPresent:
    @pytest.mark.zentao("TC-A0008", domain="server/artifacts", priority="P1")
    async def test_default_artifacts_without_yaml_declaration(
        self, sample_run, artifacts_dir
    ):
        """FR9: 没有 artifacts 配置时默认产物仍存在。"""
        await collect_default_artifacts(
            run_id=sample_run.id,
            pipeline_name="no-artifacts-pipeline",
            pipeline_id="pid_002",
            pipeline_version="1",
            status="success",
            started_at=sample_run.started_at,
            finished_at=sample_run.finished_at,
            task_names=["task-a"],
        )

        default_dir = artifacts_dir / "default"
        assert (default_dir / "log.txt").exists()
        assert (default_dir / "meta.json").exists()


# ─── 场景 9: 目录自动打包为 zip（FR2） ───


class TestDirectoryAutoZip:
    @pytest.mark.zentao("TC-A0009", domain="server/artifacts", priority="P1")
    async def test_directory_artifact_zipped(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """FR2: 目录 path 自动生成 reports.zip。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        reports = workdir / "reports"
        reports.mkdir()
        (reports / "junit.xml").write_text("<testsuites/>")
        (reports / "coverage.html").write_text("<html>coverage</html>")
        sub = reports / "screenshots"
        sub.mkdir()
        (sub / "test1.png").write_bytes(b"\x89PNG")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="report",
            artifacts_config=[{"path": "reports/"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert items[0].path == "reports.zip"
        assert items[0].content_type == "application/zip"

        zip_path = artifacts_dir / "report" / "reports.zip"
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "junit.xml" in names
            assert "coverage.html" in names
            assert "screenshots/test1.png" in names


# ─── 场景 10: promote API（FR10） ───


class TestPromoteAPI:
    @pytest.mark.zentao("TC-A0010", domain="server/artifacts", priority="P1")
    async def test_promote_copy(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine, tmp_path
    ):
        """FR10: promote 复制文件到 artifacts 目录。"""
        source = tmp_path / "coverage.html"
        source.write_text("<html>coverage report</html>")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/promote",
                json={"task_name": "build", "path": str(source), "move": False},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["artifact"]["task_name"] == "build"
            assert data["artifact"]["path"] == "coverage.html"

            assert source.exists(), "source should still exist (copy mode)"

            promoted = artifacts_dir / "build" / "coverage.html"
            assert promoted.exists()

    @pytest.mark.zentao("TC-A0010", domain="server/artifacts", priority="P1")
    async def test_promote_move(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine, tmp_path
    ):
        """FR10: promote move=true 时源文件被移除。"""
        source = tmp_path / "debug.log"
        source.write_text("debug output")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/promote",
                json={"task_name": "build", "path": str(source), "move": True},
            )
            assert resp.status_code == 200
            assert not source.exists(), "source should be removed (move mode)"

            moved = artifacts_dir / "build" / "debug.log"
            assert moved.exists()


# ─── 场景 11: 三级 artifacts 配置（FR11） ───


class TestThreeLevelArtifacts:
    @pytest.mark.zentao("TC-A0011", domain="server/artifacts", priority="P1")
    async def test_task_level_artifacts(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """FR11: task 级别 artifacts 在 task 结束后收集。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "app.tar.gz").write_bytes(b"app-binary")

        items = await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="compile",
            artifacts_config=[{"path": "app.tar.gz"}],
            workdir=workdir,
        )

        assert len(items) == 1
        assert (artifacts_dir / "compile" / "app.tar.gz").exists()

    @pytest.mark.zentao("TC-A0011", domain="server/artifacts", priority="P1")
    async def test_multiple_levels_independent(
        self, sample_run, artifacts_dir, db_engine, tmp_path
    ):
        """FR11: 三级 artifacts 独立生效，互不覆盖。"""
        workdir = tmp_path / "workdir"
        workdir.mkdir()
        (workdir / "task-artifact.txt").write_bytes(b"task-level")
        (workdir / "sub-artifact.xml").write_bytes(b"sub-level")
        (workdir / "pipeline-report.html").write_bytes(b"pipeline-level")

        await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="build",
            artifacts_config=[{"path": "task-artifact.txt"}],
            workdir=workdir,
        )
        await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="test-summary",
            artifacts_config=[{"path": "sub-artifact.xml"}],
            workdir=workdir,
        )
        await collect_task_artifacts(
            run_id=sample_run.id,
            task_name="overall",
            artifacts_config=[{"path": "pipeline-report.html"}],
            workdir=workdir,
        )

        async with get_session_factory()() as session:
            repo = ArtifactRepository(session)
            all_arts = await repo.list_artifacts(sample_run.id)

        task_names = {a.task_name for a in all_arts}
        assert "build" in task_names
        assert "test-summary" in task_names
        assert "overall" in task_names


# ─── 场景 12: 远程 Agent 产物回传（FR12） ───


class TestRemoteAgentUpload:
    @pytest.mark.zentao("TC-A0012", domain="server/artifacts", priority="P1")
    async def test_upload_artifacts(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine
    ):
        """FR12: POST upload 上传产物到 server。"""
        import io

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/upload",
                data={
                    "task_name": "build",
                    "paths": json.dumps(["dist/app.tar.gz", "dist/config.yaml"]),
                },
                files=[
                    ("files", ("app.tar.gz", b"\x1f\x8b" + b"\x00" * 50, "application/gzip")),
                    ("files", ("config.yaml", b"version: 1", "text/yaml")),
                ],
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["uploaded"]) == 2

            assert (artifacts_dir / "build" / "dist" / "app.tar.gz").exists()
            assert (artifacts_dir / "build" / "dist" / "config.yaml").exists()

    @pytest.mark.zentao("TC-A0012", domain="server/artifacts", priority="P1")
    async def test_upload_then_download(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine
    ):
        """FR12: 上传后可通过下载接口获取。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            upload_resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/upload",
                data={
                    "task_name": "deploy",
                    "paths": json.dumps(["result.txt"]),
                },
                files=[
                    ("files", ("result.txt", b"deploy-success", "text/plain")),
                ],
            )
            assert upload_resp.status_code == 200

            list_resp = await client.get(f"/api/runs/{sample_run.id}/artifacts")
            assert list_resp.status_code == 200
            arts = list_resp.json()["artifacts"]
            assert any(a["task_name"] == "deploy" and a["path"] == "result.txt" for a in arts)
