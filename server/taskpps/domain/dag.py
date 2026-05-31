from __future__ import annotations

from collections import deque

from taskpps.domain.pipeline import ResolvedTask
from taskpps.i18n import t


class DAGCycleError(Exception):
    pass


class DAG:
    def __init__(self, tasks: list[ResolvedTask], implicit_sequential: bool = True):
        self.tasks = {t.name: t for t in tasks}
        self.task_order = [t.name for t in tasks]
        self.adjacency: dict[str, list[str]] = {}
        self.reverse_adjacency: dict[str, list[str]] = {}
        self._build(implicit_sequential)

    def _build(self, implicit_sequential: bool = True) -> None:
        for name in self.tasks:
            self.adjacency[name] = []
            self.reverse_adjacency[name] = []

        if implicit_sequential:
            for i in range(1, len(self.task_order)):
                name = self.task_order[i]
                task = self.tasks[name]
                if not task.depends_on:
                    prev = self.task_order[i - 1]
                    task.depends_on = [prev]

        for name, task in self.tasks.items():
            for dep in task.depends_on:
                if dep not in self.tasks:
                    raise ValueError(t("Task '{task}' depends on unknown task '{dep}'", task=name, dep=dep))
                self.adjacency[dep].append(name)
                self.reverse_adjacency[name].append(dep)

    def topological_sort(self) -> list[str]:
        in_degree: dict[str, int] = {name: 0 for name in self.tasks}
        for name in self.tasks:
            for neighbor in self.adjacency[name]:
                in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in self.adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.tasks):
            remaining = set(self.tasks.keys()) - set(result)
            raise DAGCycleError(t("Cycle detected among tasks: {tasks}", tasks=remaining))

        return result

    def get_execution_levels(self) -> list[list[str]]:
        in_degree: dict[str, int] = {name: len(self.reverse_adjacency[name]) for name in self.tasks}
        levels = []
        remaining = set(self.tasks.keys())

        while remaining:
            level = [name for name in remaining if in_degree[name] == 0]
            if not level:
                raise DAGCycleError(t("Cycle detected among tasks: {tasks}", tasks=remaining))
            levels.append(level)
            for name in level:
                remaining.remove(name)
                for neighbor in self.adjacency[name]:
                    in_degree[neighbor] -= 1

        return levels

    def get_dependents(self, task_name: str) -> set[str]:
        visited = set()
        queue = deque([task_name])
        while queue:
            node = queue.popleft()
            for neighbor in self.adjacency.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def get_dependencies(self, task_name: str) -> set[str]:
        visited = set()
        queue = deque([task_name])
        while queue:
            node = queue.popleft()
            for dep in self.reverse_adjacency.get(node, []):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        return visited
