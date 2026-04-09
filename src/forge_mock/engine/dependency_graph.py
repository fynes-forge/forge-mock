"""Dependency graph for ordering table generation to respect foreign keys.

Uses stdlib collections only — no networkx dependency required.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from forge_mock.parser.schema_models import TableSchema


class DependencyGraph:
    """Builds a DAG of tables from FK relationships and returns a topological order.

    Implements Kahn's algorithm (BFS-based topological sort) so the result is
    deterministic and cycle detection is O(V + E).
    """

    def __init__(self) -> None:
        # adjacency list: node → set of nodes that depend ON it (its successors)
        self._successors: dict[str, set[str]] = defaultdict(set)
        # in-degree per node (number of unresolved dependencies)
        self._in_degree: dict[str, int] = defaultdict(int)
        self._nodes: set[str] = set()

    def build(self, tables: Iterable[TableSchema]) -> None:
        """Populate the graph from a collection of TableSchema objects."""
        self._successors.clear()
        self._in_degree.clear()
        self._nodes.clear()

        table_list = list(tables)
        for table in table_list:
            self._nodes.add(table.name)

        for table in table_list:
            for dep in table.dependencies:
                self._nodes.add(dep)  # may be external/unknown table
                self._successors[dep].add(table.name)
                self._in_degree[table.name] += 1

        # Ensure every node has an in_degree entry (even if zero)
        for node in self._nodes:
            if node not in self._in_degree:
                self._in_degree[node] = 0

    def generation_order(self) -> list[str]:
        """Return table names in topological order (dependencies first).

        Raises ValueError if the dependency graph contains cycles.
        """
        in_degree = dict(self._in_degree)  # mutable copy
        queue: deque[str] = deque(
            sorted(node for node, deg in in_degree.items() if deg == 0)
        )
        order: list[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for successor in sorted(self._successors.get(node, set())):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(order) != len(self._nodes):
            remaining = self._nodes - set(order)
            raise ValueError(
                f"Circular FK dependency detected among tables: "
                f"{', '.join(sorted(remaining))}. "
                "Check your FOREIGN KEY constraints for cycles."
            )

        return order

    def has_cycles(self) -> bool:
        """Return True if the graph contains at least one cycle."""
        try:
            self.generation_order()
            return False
        except ValueError:
            return True
