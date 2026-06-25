"""异常流测试 — 非法输入/缺失/冲突/超时等异常场景。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.services.artifact_service import (
    collect_task_artifacts,
    parse_artifact_ref,
    resolve_artifact_ref,
    promote_artifact,
    upload_artifacts,
)


class TestDownloadNonexistent:
    @pytest.mark.zentao("TC-E0001", domain="server/artifacts", priority="P1")
    async def test_download_nonexistent_artifact(self, app, sample_run, artifacts_dir, default_artifacts, db_engine):
        """异常: 下载不存在的 artifact 路径返回 404。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/runs/{sample_run.id}/artifacts/nonexistent/missing.txt"
            )
            assert resp.status_code == 404

    @pytest.mark.zentao("TC-E0001", domain="server/artifacts", priority="P1")
    async def test_download_nonexistent_run(self, app, db_engine):
        """异常: 不存在的 run_id 返回 404。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/fake_run/artifacts/build/app.tar.gz")
            assert resp.status_code == 404


class TestCrossRunExpired:
    @pytest.mark.zentao("TC-E0002", domain="server/artifacts", priority="P1")
    def test_cross_run_ref_expired_run(self, tmp_path):
        """异常: 跨 run 引用已过期/清理的 run → 返回 None。"""
        ref = parse_artifact_ref("${artifact:run_xxx/expired_run_999/build/package/app.jar}")
        assert ref is not None
        assert ref.run_id == "run_xxx"

        resolved = resolve_artifact_ref(ref, current_run_id="current_run")
        assert resolved is None


class TestPromoteErrors:
    @pytest.mark.zentao("TC-E0003", domain="server/artifacts", priority="P1")
    async def test_promote_nonexistent_source(self, app, sample_run, artifacts_dir, default_artifacts, db_engine):
        """异常: promote 不存在的源文件 → 404。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/promote",
                json={
                    "task_name": "build",
                    "path": "/tmp/definitely_nonexistent_file_12345.txt",
                    "move": False,
                },
            )
            assert resp.status_code == 404

    @pytest.mark.zentao("TC-E0004", domain="server/artifacts", priority="P1")
    async def test_promote_conflict_existing_artifact(
        self, app, sample_run, artifacts_dir, default_artifacts, db_engine, tmp_path
    ):
        """异常: promote 到已存在的 artifact → 409 冲突。"""
        source = tmp_path / "dup.txt"
        source.write_bytes(b"duplicate-content")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/promote",
                json={"task_name": "build", "path": str(source), "move": False},
            )
            assert resp1.status_code == 200

            resp2 = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/promote",
                json={"task_name": "build", "path": str(source), "move": False},
            )
            assert resp2.status_code == 409


class TestInvalidArtifactSyntax:
    @pytest.mark.zentao("TC-E0005", domain="server/artifacts", priority="P2")
    def test_parse_ref_single_part(self):
        """异常: ${artifact:taskonly} 缺少 path → 返回 None。"""
        ref = parse_artifact_ref("${artifact:taskonly}")
        assert ref is None

    @pytest.mark.zentao("TC-E0005", domain="server/artifacts", priority="P2")
    def test_parse_ref_empty(self):
        """异常: ${artifact:} 空引用 → 返回 None。"""
        ref = parse_artifact_ref("${artifact:}")
        assert ref is None

    @pytest.mark.zentao("TC-E0005", domain="server/artifacts", priority="P2")
    def test_parse_ref_no_braces(self):
        """异常: 非标准语法无花括号 → 返回 None。"""
        ref = parse_artifact_ref("artifact:build/dist/app.tar.gz")
        assert ref is None

    @pytest.mark.zentao("TC-E0005", domain="server/artifacts", priority="P2")
    def test_parse_ref_malformed(self):
        """异常: 各种畸形语法 → 返回 None。"""
        for bad in [
            "${artifact:}",
            "${artifact:/}",
            "${not_artifact:build/app}",
            "",
            "plain text",
            "${artifact:build}",
        ]:
            ref = parse_artifact_ref(bad)
            assert ref is None, f"Expected None for: {bad!r}"


class TestUploadErrors:
    @pytest.mark.zentao("TC-E0006", domain="server/artifacts", priority="P1")
    async def test_upload_missing_task_name(self, app, sample_run, artifacts_dir, default_artifacts, db_engine):
        """异常: upload 缺少 task_name → 422。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/upload",
                data={"paths": json.dumps(["file.txt"])},
                files=[("files", ("file.txt", b"content", "text/plain"))],
            )
            assert resp.status_code == 422

    @pytest.mark.zentao("TC-E0007", domain="server/artifacts", priority="P1")
    async def test_upload_empty_files(self, app, sample_run, artifacts_dir, default_artifacts, db_engine):
        """异常: upload files 为空 → 422。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/upload",
                data={
                    "task_name": "build",
                    "paths": json.dumps(["file.txt"]),
                },
            )
            assert resp.status_code == 422

    @pytest.mark.zentao("TC-E0006", domain="server/artifacts", priority="P1")
    async def test_upload_paths_files_count_mismatch(self, app, sample_run, artifacts_dir, default_artifacts, db_engine):
        """异常: paths 数组长度与 files 不匹配 → 400。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/upload",
                data={
                    "task_name": "build",
                    "paths": json.dumps(["a.txt", "b.txt"]),
                },
                files=[("files", ("a.txt", b"content-a", "text/plain"))],
            )
            assert resp.status_code == 400

    @pytest.mark.zentao("TC-E0006", domain="server/artifacts", priority="P1")
    async def test_upload_invalid_paths_json(self, app, sample_run, artifacts_dir, default_artifacts, db_engine):
        """异常: paths 不是合法 JSON → 400。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/runs/{sample_run.id}/artifacts/upload",
                data={
                    "task_name": "build",
                    "paths": "not-json",
                },
                files=[("files", ("a.txt", b"content", "text/plain"))],
            )
            assert resp.status_code == 400


class TestCrossRunWithoutDependencies:
    @pytest.mark.zentao("TC-E0008", domain="server/artifacts", priority="P2")
    def test_cross_run_ref_no_dependency_declaration(self):
        """异常: 跨 run 引用但未声明 dependencies → 引用解析仍尝试但可能失败。"""
        ref = parse_artifact_ref("${artifact:run_abc/run_123/build/package/app.jar}")
        assert ref is not None
        assert ref.run_id == "run_abc"

        resolved = resolve_artifact_ref(ref, current_run_id="current")
        assert resolved is None


class TestNonexistentSubpipeline:
    @pytest.mark.zentao("TC-E0009", domain="server/artifacts", priority="P2")
    def test_ref_to_nonexistent_subpipeline(self):
        """异常: 引用不存在的 subpipeline 中的 artifact。"""
        ref = parse_artifact_ref("${artifact:fake-sub/task/deep/path.txt}")
        assert ref is not None
        assert ref.subpipeline == "fake-sub"

        resolved = resolve_artifact_ref(ref, current_run_id="test_run_001")
        assert resolved is None


class TestPromoteToNonexistentRun:
    @pytest.mark.zentao("TC-E0003", domain="server/artifacts", priority="P1")
    async def test_promote_to_nonexistent_run(self, app, db_engine, tmp_path):
        """异常: promote 到不存在的 run → 404。"""
        source = tmp_path / "file.txt"
        source.write_bytes(b"content")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/runs/nonexistent_run/artifacts/promote",
                json={"task_name": "build", "path": str(source), "move": False},
            )
            assert resp.status_code == 404


class TestListArtifactsNonexistentRun:
    @pytest.mark.zentao("TC-E0001", domain="server/artifacts", priority="P1")
    async def test_list_artifacts_nonexistent_run(self, app, db_engine):
        """异常: 列出不存在的 run 的 artifacts → 404。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/nonexistent_run/artifacts")
            assert resp.status_code == 404
