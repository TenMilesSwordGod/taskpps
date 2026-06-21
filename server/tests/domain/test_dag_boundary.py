from __future__ import annotations

import pytest

from taskpps.domain.dag import DAG, DAGCycleError
from taskpps.domain.pipeline import ResolvedTask


def _make_task(name: str, depends_on: list[str] | None = None) -> ResolvedTask:
    return ResolvedTask(
        name=name,
        task_type="command",
        command="echo",
        depends_on=depends_on or [],
    )


class TestDAGBoundary:
    def test_empty_dag(self):
        dag = DAG([])
        assert len(dag.tasks) == 0
        assert dag.topological_sort() == []
        assert dag.get_execution_levels() == []

    def test_single_node(self):
        dag = DAG([_make_task("a")])
        assert len(dag.tasks) == 1
        assert dag.topological_sort() == ["a"]

    def test_two_nodes_with_dependency(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b", depends_on=["a"]),
            ]
        )
        order = dag.topological_sort()
        assert order.index("a") < order.index("b")

    def test_two_nodes_no_dependency_implicit_sequential(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b"),
            ]
        )
        order = dag.topological_sort()
        assert order.index("a") < order.index("b")

    def test_two_nodes_no_dependency_explicit(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b"),
            ],
            implicit_sequential=False,
        )
        order = dag.topological_sort()
        assert len(order) == 2
        assert "a" in order
        assert "b" in order

    def test_cycle_detection_two_nodes(self):
        with pytest.raises(DAGCycleError):
            dag = DAG(
                [
                    _make_task("a", depends_on=["b"]),
                    _make_task("b", depends_on=["a"]),
                ]
            )
            dag.topological_sort()

    def test_cycle_detection_three_nodes(self):
        with pytest.raises(DAGCycleError):
            dag = DAG(
                [
                    _make_task("a", depends_on=["b"]),
                    _make_task("b", depends_on=["c"]),
                    _make_task("c", depends_on=["a"]),
                ]
            )
            dag.topological_sort()

    def test_unknown_dependency(self):
        with pytest.raises(ValueError):
            DAG(
                [
                    _make_task("a", depends_on=["nonexistent"]),
                ]
            )

    def test_get_dependents(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b", depends_on=["a"]),
                _make_task("c", depends_on=["a"]),
            ]
        )
        assert dag.get_dependents("a") == {"b", "c"}
        assert dag.get_dependents("b") == set()

    def test_get_dependencies(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b", depends_on=["a"]),
                _make_task("c", depends_on=["b"]),
            ]
        )
        assert dag.get_dependencies("c") == {"a", "b"}
        assert dag.get_dependencies("a") == set()

    def test_execution_levels(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b"),
                _make_task("c", depends_on=["a", "b"]),
                _make_task("d", depends_on=["c"]),
            ],
            implicit_sequential=False,
        )
        levels = dag.get_execution_levels()
        assert len(levels) == 3
        assert set(levels[0]) == {"a", "b"}
        assert set(levels[1]) == {"c"}
        assert set(levels[2]) == {"d"}

    def test_diamond_structure(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b", depends_on=["a"]),
                _make_task("c", depends_on=["a"]),
                _make_task("d", depends_on=["b", "c"]),
            ]
        )
        order = dag.topological_sort()
        assert len(order) == 4
        assert order.index("a") < order.index("d")

    def test_linear_chain(self):
        tasks = [_make_task("step0")]
        for i in range(1, 10):
            tasks.append(_make_task(f"step{i}", depends_on=[f"step{i - 1}"]))
        dag = DAG(tasks)
        order = dag.topological_sort()
        for i in range(9):
            assert order.index(f"step{i}") < order.index(f"step{i + 1}")

    def test_disconnected_graph(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b", depends_on=["a"]),
                _make_task("c"),
                _make_task("d", depends_on=["c"]),
            ],
            implicit_sequential=False,
        )
        order = dag.topological_sort()
        assert len(order) == 4
        assert order.index("a") < order.index("b")
        assert order.index("c") < order.index("d")

    def test_large_dag(self):
        tasks = [_make_task("step0")]
        for i in range(1, 100):
            tasks.append(_make_task(f"step{i}", depends_on=[f"step{i - 1}"]))
        dag = DAG(tasks)
        order = dag.topological_sort()
        assert len(order) == 100
        assert order[0] == "step0"
        assert order[-1] == "step99"

    def test_single_level(self):
        dag = DAG(
            [
                _make_task("a"),
                _make_task("b"),
                _make_task("c"),
            ],
            implicit_sequential=False,
        )
        levels = dag.get_execution_levels()
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_get_dependencies_nonexistent(self):
        dag = DAG([_make_task("a")])
        assert dag.get_dependencies("nonexistent") == set()

    def test_get_dependents_nonexistent(self):
        dag = DAG([_make_task("a")])
        assert dag.get_dependents("nonexistent") == set()

    def test_execution_levels_preserve_yaml_order(self):
        """Issue #85: 同层级任务应按 YAML 声明顺序排列"""
        dag = DAG(
            [
                _make_task("setup"),
                _make_task("smoke-test", depends_on=["setup"]),
                _make_task("perf-test", depends_on=["setup"]),
                _make_task("final", depends_on=["smoke-test"]),
            ],
            implicit_sequential=False,
        )
        levels = dag.get_execution_levels()
        # Level 0: [setup]
        # Level 1: [smoke-test, perf-test] — 应按 YAML 声明顺序
        # Level 2: [final]
        assert len(levels) == 3
        assert levels[0] == ["setup"]
        # smoke-test 在 perf-test 之前声明, 应排在前面
        assert levels[1] == ["smoke-test", "perf-test"]
        assert levels[2] == ["final"]
