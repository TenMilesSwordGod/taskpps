"""测试 naming 模块的 display_name 生成。"""

from taskpps.naming import _ADJECTIVES, _NOUNS, generate_display_name


@pytest.mark.zentao("TC-S0026", domain="server/root", priority="P2")
def test_generate_display_name_format():
    """生成的名称应为 形容词_名词 格式。"""
    name = generate_display_name()
    assert "_" in name
    parts = name.split("_")
    assert len(parts) == 2
    assert parts[0] in _ADJECTIVES
    assert parts[1] in _NOUNS


@pytest.mark.zentao("TC-S0027", domain="server/root", priority="P2")
def test_generate_display_name_not_empty():
    """生成的名称不应为空。"""
    name = generate_display_name()
    assert name
    assert isinstance(name, str)


@pytest.mark.zentao("TC-S0028", domain="server/root", priority="P2")
def test_generate_display_name_randomness():
    """多次调用应产生不同的名称（概率性测试）。"""
    names = {generate_display_name() for _ in range(20)}
    # 40*40=1600 种组合，20 次调用至少应有 2 种不同名称
    assert len(names) >= 2


def test_word_lists_size():
    """形容词和名词列表各约 40 个。"""
    assert len(_ADJECTIVES) >= 30
    assert len(_NOUNS) >= 30

