from __future__ import annotations

import asyncio
import logging
import os
import shlex
from pathlib import Path

from taskpps.executors.base import BaseExecutor, ExecutorResult
from taskpps.i18n import t

logger = logging.getLogger(__name__)


class GitExecutor(BaseExecutor):
    def __init__(
        self,
        repo: str,
        ref: str | None = None,
        credential: str | None = None,
        dest: str = "/workspace/repo",
        depth: int = 1,
        submodules: bool = False,
    ):
        self.repo = repo
        self.ref = ref or "main"
        self.credential = credential
        self.dest = dest
        self.depth = depth
        self.submodules = submodules
        self._cancelled = False

    async def execute(
        self,
        command: str,
        env: dict[str, str],
        log_path: Path,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> ExecutorResult:
        self._ensure_log_dir(log_path)
        self._cancelled = False

        merged_env = {**os.environ, **env}

        def _run_git_clone():
            dest_path = Path(self.dest)
            if dest_path.exists() and list(dest_path.iterdir()):
                logger.info("GitExecutor: dest exists, pulling latest on %s ref=%s", self.dest, self.ref)
                with open(log_path, "a") as f:
                    f.write(
                        t(
                            "Destination '{dest}' already exists and is not empty, pulling latest changes\n",
                            dest=self.dest,
                        )
                    )
                return _git_pull(self.dest, self.ref, log_path, merged_env, self.credential)

            logger.info("GitExecutor: cloning %s branch=%s depth=%d", self.repo, self.ref, self.depth)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            clone_args = ["git", "clone", "--depth", str(self.depth)]
            if self.ref:
                clone_args.extend(["--branch", self.ref])
            if self.submodules:
                clone_args.append("--recurse-submodules")

            repo_url = _apply_credential_to_url(self.repo, self.credential, merged_env)
            clone_args.extend([repo_url, str(dest_path)])

            return _run_subprocess(clone_args, log_path, merged_env, cwd=str(dest_path.parent))

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _run_git_clone)
            return result
        except asyncio.CancelledError:
            msg = t("Git task was cancelled")
            logger.info("GitExecutor: task cancelled repo=%s", self.repo)
            with open(log_path, "a") as f:
                f.write(msg)
            return ExecutorResult(exit_code=-1, stderr=msg)

    async def cancel(self) -> None:
        self._cancelled = True


def _apply_credential_to_url(repo_url: str, credential: str | None, env: dict[str, str]) -> str:
    if not credential:
        return repo_url

    token = env.get("GIT_TOKEN") or env.get(credential) or credential
    if repo_url.startswith("https://") and token:
        prefix = "https://"
        rest = repo_url[len(prefix) :]
        return f"{prefix}oauth2:{token}@{rest}"
    return repo_url


def _git_pull(dest: str, ref: str, log_path: Path, env: dict[str, str], credential: str | None) -> ExecutorResult:
    logger.info("GitExecutor._git_pull: dest=%s ref=%s", dest, ref)
    fetch_result = _run_subprocess(["git", "fetch", "origin", ref], log_path, env, cwd=dest)
    if not fetch_result.success:
        logger.warning("GitExecutor._git_pull: fetch failed exit_code=%d", fetch_result.exit_code)
        return fetch_result

    checkout_result = _run_subprocess(["git", "checkout", ref], log_path, env, cwd=dest)
    if not checkout_result.success:
        logger.warning("GitExecutor._git_pull: checkout failed exit_code=%d", checkout_result.exit_code)
        return checkout_result

    return _run_subprocess(["git", "pull", "origin", ref], log_path, env, cwd=dest)


def _run_subprocess(args: list, log_path: Path, env: dict[str, str], cwd: str | None = None) -> ExecutorResult:
    import subprocess

    logger.info("GitExecutor._run_subprocess: %s cwd=%s", shlex.join(args), cwd or ".")

    with open(log_path, "a") as f:
        f.write(f"+ {shlex.join(args)}\n")

    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=600,
        )
        logger.info("GitExecutor._run_subprocess: completed exit_code=%d", proc.returncode)
        with open(log_path, "a") as f:
            if proc.stdout:
                f.write(proc.stdout)
            if proc.stderr:
                f.write(proc.stderr)

        return ExecutorResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except subprocess.TimeoutExpired as e:
        msg = f"Git operation timed out: {e}"
        logger.warning("GitExecutor._run_subprocess: timeout after 600s")
        with open(log_path, "a") as f:
            f.write(msg)
        return ExecutorResult(exit_code=-1, stderr=msg)
    except FileNotFoundError:
        msg = t("git command not found. Please ensure git is installed.")
        logger.error("GitExecutor._run_subprocess: git not found")
        with open(log_path, "a") as f:
            f.write(msg)
        return ExecutorResult(exit_code=1, stderr=msg)
