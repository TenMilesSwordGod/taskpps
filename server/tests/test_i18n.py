from taskpps.i18n import Translator, get_translator, set_locale, t


class TestTranslator:
    def test_init_zh(self):
        tr = Translator(locale="zh")
        assert tr._locale == "zh"
        assert tr._translations is not None

    def test_init_en(self):
        tr = Translator(locale="en")
        assert tr._locale == "en"

    def test_t_existing(self):
        tr = Translator(locale="zh")
        result = tr.t("Run not found")
        assert result == "运行记录未找到"

    def test_t_missing(self):
        tr = Translator(locale="zh")
        result = tr.t("Non-existent key")
        assert result == "Non-existent key"

    def test_t_with_params(self):
        tr = Translator(locale="zh")
        result = tr.t("Task exceeded timeout of {timeout}s", timeout=30)
        assert result == "任务超时(30秒)"

    def test_t_extra_kwargs(self):
        tr = Translator(locale="zh")
        result = tr.t("Run not found", extra_param="ignored")
        assert result == "运行记录未找到"

    def test_t_kwargs_not_in_string(self):
        tr = Translator(locale="zh")
        result = tr.t("Task exceeded timeout of {timeout}s", wrong_key="value")
        assert "{timeout}" in result
        assert "超时" in result

    def test_t_missing_key_in_kwargs(self):
        tr = Translator(locale="zh")
        result = tr.t("Step {n}/{total}: {cmd}")
        assert "{n}" in result and "{total}" in result and "{cmd}" in result

    def test_en_returns_key(self):
        tr = Translator(locale="en")
        result = tr.t("Run not found")
        assert result == "Run not found"


class TestTranslatorSingleton:
    def test_get_translator_singleton(self):
        set_locale("en")
        tr1 = get_translator()
        tr2 = get_translator()
        assert tr1 is tr2

    def test_set_locale(self):
        set_locale("en")
        tr = get_translator()
        assert tr._locale == "en"
        assert tr.t("Run not found") == "Run not found"


class TestTShortcut:
    def test_t_shortcut(self):
        set_locale("zh")
        result = t("Run not found")
        assert result == "运行记录未找到"

    def test_t_shortcut_with_params(self):
        set_locale("zh")
        result = t("Task exceeded timeout of {timeout}s", timeout=60)
        assert result == "任务超时(60秒)"