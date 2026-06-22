"""Issue #106: PipelineConfig max_parallel → max_concurrent_runs 向后兼容测试"""

from taskpps.schemas.pipeline import PipelineConfig


class TestPipelineConfigBackwardCompat:
    """测试 max_parallel 旧字段自动映射到 max_concurrent_runs"""

    def test_new_field_works(self):
        """使用新字段 max_concurrent_runs 正常工作"""
        cfg = PipelineConfig(max_concurrent_runs=3)
        assert cfg.max_concurrent_runs == 3

    def test_old_field_maps_to_new(self):
        """YAML 中写 max_parallel 自动映射到 max_concurrent_runs"""
        cfg = PipelineConfig(**{"max_parallel": 5})
        assert cfg.max_concurrent_runs == 5

    def test_both_fields_new_wins(self):
        """同时写 max_parallel 和 max_concurrent_runs 时，新字段优先"""
        cfg = PipelineConfig(**{"max_parallel": 2, "max_concurrent_runs": 3})
        assert cfg.max_concurrent_runs == 3

    def test_neither_field_defaults_none(self):
        """两个字段都不写时，max_concurrent_runs 为 None"""
        cfg = PipelineConfig()
        assert cfg.max_concurrent_runs is None

    def test_old_field_zero_maps(self):
        """max_parallel=0 也应映射到 max_concurrent_runs"""
        cfg = PipelineConfig(**{"max_parallel": 0})
        assert cfg.max_concurrent_runs == 0

    def test_model_dump_uses_new_name(self):
        """model_dump 输出使用新字段名"""
        cfg = PipelineConfig(**{"max_parallel": 4})
        data = cfg.model_dump()
        assert "max_concurrent_runs" in data
        assert data["max_concurrent_runs"] == 4


class TestPipelineConfigMaxConcurrentTasks:
    """测试新增的 max_concurrent_tasks 字段"""

    def test_default_none(self):
        cfg = PipelineConfig()
        assert cfg.max_concurrent_tasks is None

    def test_set_value(self):
        cfg = PipelineConfig(max_concurrent_tasks=5)
        assert cfg.max_concurrent_tasks == 5

    def test_in_model_dump(self):
        cfg = PipelineConfig(max_concurrent_tasks=3)
        data = cfg.model_dump()
        assert data["max_concurrent_tasks"] == 3
