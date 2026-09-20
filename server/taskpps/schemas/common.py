"""schema 层共享校验规则。

设计决策：agent 与 credential 的 id 都会成为 YAML 文件名，必须使用同一套
路径安全正则；集中定义避免两处规则漂移导致其中一处再次引入路径穿越风险。
"""

from __future__ import annotations

# 首字符字母数字，后续允许 _ . -，最长 64（覆盖文件名安全性）
RESOURCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
