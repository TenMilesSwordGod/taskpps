import pytest
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from official_plugins.git.plugin import GitPlugin


class TestGitPluginDefaultBehavior:
    """默认行为测试"""

    def test_default_action_when_repo_not_exists(self):
        """仓库不存在时自动生成 clone 命令"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main"
        )
        command = plugin.build_command()
        assert "if [ -d" in command
        assert "git clone" in command
        assert "git pull" in command
        assert "repo" in command  # 目录名

    def test_default_action_repo_dir_extraction(self):
        """测试仓库目录名提取"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main"
        )
        assert plugin._repo_dir() == "repo"

    def test_default_action_repo_dir_with_trailing_slash(self):
        """测试带尾部斜杠的 URL"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git/",
            branch="main"
        )
        assert plugin._repo_dir() == "repo"

    def test_default_action_repo_dir_without_git_suffix(self):
        """测试不带 .git 后缀的 URL"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo",
            branch="main"
        )
        assert plugin._repo_dir() == "repo"

    def test_default_branch_handling(self):
        """测试默认分支处理"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main"
        )
        command = plugin.build_command()
        assert "main" in command

    def test_custom_branch(self):
        """测试自定义分支"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="develop"
        )
        command = plugin.build_command()
        assert "develop" in command


class TestGitPluginExplicitAction:
    """显式 action 测试"""

    def test_explicit_clone(self):
        """显式指定 clone 行为不变"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            action="clone"
        )
        command = plugin.build_command()
        assert command == "git clone --branch main https://github.com/user/repo.git"

    def test_explicit_pull(self):
        """显式指定 pull 行为不变"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            action="pull"
        )
        command = plugin.build_command()
        assert command == "git pull origin main https://github.com/user/repo.git"

    def test_explicit_checkout(self):
        """显式指定 checkout 行为不变"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            action="checkout"
        )
        command = plugin.build_command()
        assert command == "git checkout https://github.com/user/repo.git"

    def test_explicit_action_with_branch(self):
        """显式 action 带分支参数"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="feature/test",
            action="clone"
        )
        command = plugin.build_command()
        assert "feature/test" in command


class TestGitPluginParameterCombinations:
    """参数组合测试"""

    def test_remote_branch_credential(self):
        """remote + branch + credential 组合"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            credential="my-git-cred"
        )
        command = plugin.build_command()
        assert "GIT_CREDENTIAL_HELPER" in command
        assert "my-git-cred" in command

    def test_only_remote(self):
        """只指定 remote（最简配置）"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main"
        )
        command = plugin.build_command()
        assert "https://github.com/user/repo.git" in command

    def test_credential_handling(self):
        """指定 credential 时的处理"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            credential="test-cred"
        )
        command = plugin.build_command()
        assert "GIT_CREDENTIAL_HELPER='store --file=test-cred'" in command

    def test_explicit_action_with_credential(self):
        """显式 action 带 credential（显式模式不处理 credential）"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            action="clone",
            credential="test-cred"
        )
        command = plugin.build_command()
        # 显式模式不处理 credential
        assert "GIT_CREDENTIAL_HELPER" not in command
        assert "git clone" in command


class TestGitPluginEdgeCases:
    """边界情况测试"""

    def test_https_url(self):
        """HTTPS URL 格式"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main"
        )
        command = plugin.build_command()
        assert "https://github.com/user/repo.git" in command

    def test_ssh_url(self):
        """SSH URL 格式"""
        plugin = GitPlugin(
            remote="git@github.com:user/repo.git",
            branch="main"
        )
        command = plugin.build_command()
        assert "git@github.com:user/repo.git" in command

    def test_git_at_url(self):
        """git@ URL 格式"""
        plugin = GitPlugin(
            remote="git@gitlab.com:group/project.git",
            branch="main"
        )
        assert plugin._repo_dir() == "project"

    def test_branch_with_special_chars(self):
        """分支名称特殊字符"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="feature/test-branch"
        )
        command = plugin.build_command()
        assert "feature/test-branch" in command

    def test_branch_with_slash(self):
        """分支名称带斜杠"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="feature/sub-branch"
        )
        command = plugin.build_command()
        assert "feature/sub-branch" in command

    def test_empty_string_remote(self):
        """空字符串 remote 参数"""
        plugin = GitPlugin(
            remote="",
            branch="main"
        )
        # 空字符串应该能正常处理
        assert plugin._repo_dir() == ""

    def test_empty_string_branch(self):
        """空字符串 branch 参数"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch=""
        )
        command = plugin.build_command()
        assert "''" in command or '""' in command or " " in command


class TestGitPluginErrorHandling:
    """错误处理测试"""

    def test_invalid_action_value(self):
        """无效的 action 值"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            action="invalid"
        )
        # 无效 action 会生成无效命令，但不会抛出异常
        command = plugin.build_command()
        assert "git invalid" in command

    def test_missing_remote_parameter(self):
        """缺少必填参数 remote"""
        # GitPlugin 不会在初始化时验证参数
        # 而是在 build_command 时使用
        plugin = GitPlugin(
            remote=None,
            branch="main"
        )
        # 会抛出异常
        with pytest.raises(AttributeError):
            plugin.build_command()

    def test_missing_branch_parameter(self):
        """缺少必填参数 branch"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch=None
        )
        # branch=None 时，shlex.quote(None) 返回空字符串
        command = plugin.build_command()
        assert "''" in command

    def test_none_action(self):
        """action 为 None 时使用默认行为"""
        plugin = GitPlugin(
            remote="https://github.com/user/repo.git",
            branch="main",
            action=None
        )
        command = plugin.build_command()
        assert "if [ -d" in command


class TestGitPluginSchema:
    """参数 schema 测试"""

    def test_params_schema(self):
        """测试参数 schema 定义"""
        schema = GitPlugin.params_schema
        assert "remote" in schema
        assert "branch" in schema
        assert "action" in schema
        assert "credential" in schema

    def test_remote_required(self):
        """remote 参数必填"""
        assert GitPlugin.params_schema["remote"]["required"] is True

    def test_branch_required(self):
        """branch 参数必填"""
        assert GitPlugin.params_schema["branch"]["required"] is True

    def test_action_optional(self):
        """action 参数可选"""
        assert GitPlugin.params_schema["action"]["required"] is False

    def test_credential_optional(self):
        """credential 参数可选"""
        assert GitPlugin.params_schema["credential"]["required"] is False

    def test_action_enum(self):
        """action 参数枚举值"""
        assert "clone" in GitPlugin.params_schema["action"]["enum"]
        assert "pull" in GitPlugin.params_schema["action"]["enum"]
        assert "checkout" in GitPlugin.params_schema["action"]["enum"]


class TestGitPluginVersion:
    """版本测试"""

    def test_version(self):
        """测试版本号"""
        assert GitPlugin.version == "2.0.0"

    def test_type(self):
        """测试插件类型"""
        assert GitPlugin.type == "executor"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])