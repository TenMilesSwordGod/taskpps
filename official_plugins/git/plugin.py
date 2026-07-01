class GitPlugin:
    """Git 执行器 — 智能 clone/pull 操作。

    在 pipeline YAML 中使用:
      plugin: git_plugin
      params:
        remote: "https://github.com/user/repo.git"
        branch: "main"
        # action: "clone"  # 可选，不传则自动判断

    默认行为：检查仓库目录是否存在，不存在则 clone，存在则 pull。
    显式指定 action 时直接执行对应操作。
    """
    type = "executor"
    version = "2.0.0"
    params_schema = {
        "remote": {"type": "string", "required": True, "label": "远程仓库地址"},
        "branch": {"type": "string", "required": True, "label": "分支名"},
        "action": {"type": "string", "required": False, "label": "操作（可选）", "enum": ["clone", "checkout", "pull"]},
        "credential": {"type": "string", "required": False, "label": "凭据名"},
    }

    def __init__(self, remote, branch, action=None, credential=None):
        self.remote = remote
        self.branch = branch
        self.action = action
        self.credential = credential

    def _repo_dir(self) -> str:
        """从 remote URL 提取仓库目录名"""
        import re
        name = self.remote.rstrip("/").split("/")[-1]
        name = re.sub(r'\.git$', '', name)
        return name

    def build_command(self) -> str:
        import shlex

        if self.action:
            return self._build_explicit_command()

        # 默认行为：智能检查 + clone/pull
        repo_dir = self._repo_dir()
        remote_q = shlex.quote(self.remote)
        branch_q = shlex.quote(self.branch)
        dir_q = shlex.quote(repo_dir)

        clone_cmd = f"git clone --branch {branch_q} {remote_q} {dir_q}"
        pull_cmd = f"cd {dir_q} && git pull origin {branch_q}"

        if self.credential:
            cred_q = shlex.quote(self.credential)
            clone_cmd = f"GIT_CREDENTIAL_HELPER='store --file={cred_q}' {clone_cmd}"
            pull_cmd = f"GIT_CREDENTIAL_HELPER='store --file={cred_q}' {pull_cmd}"

        return f"if [ -d {dir_q}/.git ]; then {pull_cmd}; else {clone_cmd}; fi"

    def _build_explicit_command(self) -> str:
        """显式 action 模式（向后兼容）"""
        import shlex
        parts = ["git", self.action]
        if self.action == "clone":
            parts.append(f"--branch {shlex.quote(self.branch)}")
        elif self.action == "pull":
            parts.extend(["origin", shlex.quote(self.branch)])
        parts.append(shlex.quote(self.remote))
        return " ".join(parts)
