class GitPlugin:
    """Git 执行器 — clone/checkout/pull 操作。

    在 pipeline YAML 中使用:
      plugin: git_plugin
      params:
        remote: "https://github.com/user/repo.git"
        branch: "main"
        action: "clone"
        credential: "my-git-cred"  # 可选
    """
    type = "executor"
    version = "1.0.0"
    params_schema = {
        "remote": {"type": "string", "required": True, "label": "远程仓库地址"},
        "branch": {"type": "string", "required": True, "label": "分支名"},
        "action": {"type": "string", "required": True, "label": "操作", "enum": ["clone", "checkout", "pull"]},
        "credential": {"type": "string", "required": False, "label": "凭据名"},
    }

    def __init__(self, remote, branch, action="clone", credential=None):
        self.remote = remote
        self.branch = branch
        self.action = action
        self.credential = credential

    def build_command(self) -> str:
        import shlex
        parts = ["git", self.action]
        if self.action == "clone":
            parts.append(f"--branch {shlex.quote(self.branch)}")
        elif self.action == "pull":
            parts.extend(["origin", shlex.quote(self.branch)])
        parts.append(shlex.quote(self.remote))
        return " ".join(parts)
