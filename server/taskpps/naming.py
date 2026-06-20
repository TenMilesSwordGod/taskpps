"""生成 Docker 风格的 display_name（形容词_名词 格式）。"""

import random

_ADJECTIVES = [
    "happy", "brave", "clever", "calm", "eager",
    "gentle", "keen", "noble", "proud", "swift",
    "warm", "bright", "charming", "daring", "elegant",
    "fierce", "graceful", "humble", "jolly", "lively",
    "merry", "optimistic", "patient", "quiet", "resilient",
    "sincere", "thoughtful", "vivid", "witty", "zealous",
    "bold", "curious", "diligent", "faithful", "generous",
    "honest", "kind", "loyal", "modest", "persistent",
]

_NOUNS = [
    "einstein", "curie", "newton", "tesla", "darwin",
    "galileo", "pasteur", "faraday", "planck", "bohr",
    "turing", "lovelace", "hopper", "hamilton", "noether",
    "fox", "eagle", "tiger", "panda", "dolphin",
    "falcon", "wolf", "bear", "owl", "hawk",
    "otter", "raven", "lynx", "crane", "heron",
    "panther", "jaguar", "mantis", "phoenix", "dragon",
    "sphinx", "griffin", "pegasus", "kraken", "leviathan",
]


def generate_display_name() -> str:
    """生成一个 Docker 风格的随机名称（形容词_名词）。"""
    return f"{random.choice(_ADJECTIVES)}_{random.choice(_NOUNS)}"
