import pytest

from taskpps.i18n import Translator, get_translator, set_locale, t


class TestTranslator:
    @pytest.mark.zentao("TC-S0845", domain="server/i18n", priority="P2")
    def test_init_zh(self):
        tr = Translator(locale="zh")
        assert tr._locale == "zh"
        assert tr._translations is not None

    @pytest.mark.zentao("TC-S0846", domain="server/i18n", priority="P2")
    def test_init_en(self):
        tr = Translator(locale="en")
        assert tr._locale == "en"

    @pytest.mark.zentao("TC-S0847", domain="server/i18n", priority="P2")
    def test_t_existing(self):
        tr = Translator(locale="zh")
        result = tr.t("Run not found")
        assert result == "运行记录未找到"

    @pytest.mark.zentao("TC-S0848", domain="server/i18n", priority="P2")
    def test_t_missing(self):
        tr = Translator(locale="zh")
        result = tr.t("Non-existent key")
        assert result == "Non-existent key"

    @pytest.mark.zentao("TC-S0849", domain="server/i18n", priority="P2")
    def test_t_with_params(self):
        tr = Translator(locale="zh")
        result = tr.t("Task exceeded timeout of {timeout}s", timeout=30)
        assert result == "任务超时(30秒)"

    @pytest.mark.zentao("TC-S0850", domain="server/i18n", priority="P2")
    def test_t_extra_kwargs(self):
        tr = Translator(locale="zh")
        result = tr.t("Run not found", extra_param="ignored")
        assert result == "运行记录未找到"

    @pytest.mark.zentao("TC-S0851", domain="server/i18n", priority="P2")
    def test_t_kwargs_not_in_string(self):
        tr = Translator(locale="zh")
        result = tr.t("Task exceeded timeout of {timeout}s", wrong_key="value")
        assert "{timeout}" in result
        assert "超时" in result

    @pytest.mark.zentao("TC-S0852", domain="server/i18n", priority="P2")
    def test_t_missing_key_in_kwargs(self):
        tr = Translator(locale="zh")
        result = tr.t("Step {n}/{total}: {cmd}")
        assert "{n}" in result and "{total}" in result and "{cmd}" in result

    @pytest.mark.zentao("TC-S0853", domain="server/i18n", priority="P2")
    def test_en_returns_key(self):
        tr = Translator(locale="en")
        result = tr.t("Run not found")
        assert result == "Run not found"


class TestTranslatorSingleton:
    @pytest.mark.zentao("TC-S0854", domain="server/i18n", priority="P2")
    def test_get_translator_singleton(self):
        set_locale("en")
        tr1 = get_translator()
        tr2 = get_translator()
        assert tr1 is tr2

    @pytest.mark.zentao("TC-S0855", domain="server/i18n", priority="P2")
    def test_set_locale(self):
        set_locale("en")
        tr = get_translator()
        assert tr._locale == "en"
        assert tr.t("Run not found") == "Run not found"


class TestTShortcut:
    @pytest.mark.zentao("TC-S0856", domain="server/i18n", priority="P2")
    def test_t_shortcut(self):
        set_locale("zh")
        result = t("Run not found")
        assert result == "运行记录未找到"

    @pytest.mark.zentao("TC-S0857", domain="server/i18n", priority="P2")
    def test_t_shortcut_with_params(self):
        set_locale("zh")
        result = t("Task exceeded timeout of {timeout}s", timeout=60)
        assert result == "任务超时(60秒)"


class TestAuthErrorLocale:
    """auth 错误文案 i18n 验收（issue #223）。

    设计考虑：get_translator 是进程级缓存，locale 切换必须走 set_locale 重置；
    测试用 try/finally 恢复 zh，避免全局翻译器污染后续同进程用例。
    """

    @pytest.mark.zentao("TC-S3604", domain="server/i18n", priority="P1")
    def test_auth_error_keys_keep_zh_output(self):
        """生产改动回归：新增英文 key 在 zh 下的输出与历史硬编码中文逐字一致。"""
        tr = Translator(locale="zh")
        assert tr.t("Not logged in") == "未登录"
        assert tr.t("Invalid username or password") == "用户名或密码错误"
        # en 字典为空 → 回退 key 原文，因此 key 本身就是英文文案
        assert Translator(locale="en").t("Not logged in") == "Not logged in"
        assert Translator(locale="en").t("Invalid username or password") == "Invalid username or password"

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S3605", domain="server/i18n", priority="P0")
    async def test_auth_error_messages_follow_locale(self, client):
        """API 级验收：zh 返回原中文；en 返回英文 key 文案。"""
        try:
            set_locale("zh")
            zh_login = await client.post("/api/v1/auth/login", json={"username": "ghost", "password": "bad"})
            assert zh_login.status_code == 401
            assert zh_login.json()["detail"] == "用户名或密码错误"

            zh_me = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token"})
            assert zh_me.status_code == 401
            assert zh_me.json()["detail"] == "未登录"

            set_locale("en")
            en_login = await client.post("/api/v1/auth/login", json={"username": "ghost", "password": "bad"})
            assert en_login.status_code == 401
            assert en_login.json()["detail"] == "Invalid username or password"

            en_me = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token"})
            assert en_me.status_code == 401
            assert en_me.json()["detail"] == "Not logged in"
        finally:
            set_locale("zh")

