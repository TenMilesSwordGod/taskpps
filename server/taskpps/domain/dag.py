from __future__ import annotations

from collections import deque
from typing import Dict, List, Set

from taskpps.domain.pipeline import ResolvedTask


class DAGCycleError(Exception):
    pass


class DAG:
    def __init__(self, tasks: List[ResolvedTask]):
        self.tasks = {t.name: t for t in tasks}
        self.adjacency: Dict[str, List[str]] = {}
        self.reverse_adjacency: Dict[str, List[str]] = {}
        self._build()

    def _build(self) -> None:
        for name in self.tasks:
            self.adjacency[name] = []
            self.reverse_adjacency[name] = []

        for name, task in self.tasks.items():
            for dep in task.depends_on:
                if dep not in self.tasks:
                    raise ValueError(f"Task '{name}' depends on unknown task '{dep}'")
                self.adjacency[dep].append(name)
                self.reverse_adjacency[name].append(dep)

    def topological_sort(self) -> List[str]:
        in_degree: Dict[str, int] = {name: 0 for name in self.tasks}
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
            raise DAGCycleError(f"Cycle detected among tasks: {remaining}")

        return result

    def get_execution_levels(self) -> List[List[str]]:
        in_degree: Dict[str, int] = {name: len(self.reverse_adjacency[name]) for name in self.tasks}
        levels = []
        remaining = set(self.tasks.keys())

        while remaining:
            level = [name for name in remaining if in_degree[name] == 0]
            if not level:
                raise DAGCycleError(f"Cycle detected among tasks: {remaining}")
            levels.append(level)
            for name in level:
                remaining.remove(name)
                for neighbor in self.adjacency[name]:
                    in_degree[neighbor] -= 1

        return levels

    def get_dependents(self, task_name: str) -> Set[str]:
        visited = set()
        queue = deque([task_name])
        while queue:
            node = queue.popleft()
            for neighbor in self.adjacency.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def get_dependencies(self, task_name: str) -> Set[str]:
        visited = set()
        queue = deque([task_name])
        while queue:
            node = queue.popleft()
            for dep in self.reverse_adjacency.get(node, []):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        return visited
