import pytest
from taskpps.i18n import Translator, get_translator, set_locale, t


def test_translator_init_zh():
    tr = Translator(locale="zh")
    assert tr._locale == "zh"
    assert tr._translations is not None


def test_translator_init_en():
    tr = Translator(locale="en")
    assert tr._locale == "en"


def test_translator_t_existing():
    tr = Translator(locale="zh")
    result = tr.t("Run not found")
    assert result == "运行记录未找到"


def test_translator_t_missing():
    tr = Translator(locale="zh")
    result = tr.t("Non-existent key")
    assert result == "Non-existent key"


def test_translator_t_with_params():
    tr = Translator(locale="zh")
    result = tr.t("Task exceeded timeout of {timeout}s", timeout=30)
    assert result == "任务超时（30秒）"


def test_translator_t_extra_kwargs():
    """Test that extra kwargs that don't appear in the format string are ignored."""
    tr = Translator(locale="zh")
    result = tr.t("Run not found", extra_param="ignored")
    assert result == "运行记录未找到"


def test_translator_t_kwargs_not_in_string():
    """Test when format string has placeholder missing in kwargs (KeyError path)."""
    tr = Translator(locale="zh")
    result = tr.t("Task exceeded timeout of {timeout}s", wrong_key="value")
    assert "{timeout}" in result
    assert "超时" in result


def test_translator_t_missing_key_in_kwargs():
    """Test when format string has placeholder not provided."""
    tr = Translator(locale="zh")
    result = tr.t("Step {n}/{total}: {cmd}")
    assert "{n}" in result and "{total}" in result and "{cmd}" in result


def test_translator_en_returns_key():
    tr = Translator(locale="en")
    result = tr.t("Run not found")
    assert result == "Run not found"


def test_get_translator_singleton():
    set_locale("en")
    tr1 = get_translator()
    tr2 = get_translator()
    assert tr1 is tr2


def test_set_locale():
    set_locale("en")
    tr = get_translator()
    assert tr._locale == "en"
    assert tr.t("Run not found") == "Run not found"


def test_t_shortcut():
    set_locale("zh")
    result = t("Run not found")
    assert result == "运行记录未找到"


def test_t_shortcut_with_params():
    set_locale("zh")
    result = t("Task exceeded timeout of {timeout}s", timeout=60)
    assert result == "任务超时（60秒）"
