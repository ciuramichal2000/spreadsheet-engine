"""Strongly connected components, computed without recursion.

A spreadsheet can legally contain a chain of a couple of thousand dependent
cells; a recursive depth-first search would hit Python's recursion limit long
before that, so the search below keeps its own stack.
"""

from collections.abc import Callable, Iterable, Iterator


def strongly_connected_components[T](
    roots: Iterable[T],
    successors: Callable[[T], Iterable[T]],
) -> Iterator[list[T]]:
    """Yield the strongly connected components reachable from `roots` (Tarjan's algorithm).

    Components come out in dependency order: when node X has an edge to node Y
    in another component, Y's component is yielded before X's. That is exactly
    the order in which cells must be calculated. A component with more than one
    node (or one node with an edge to itself) is a cycle.
    """
    index: dict[T, int] = {}
    lowlink: dict[T, int] = {}
    on_stack: set[T] = set()
    stack: list[T] = []

    def visit(node: T) -> tuple[T, Iterator[T]]:
        index[node] = lowlink[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        return node, iter(successors(node))

    for root in roots:
        if root in index:
            continue
        work = [visit(root)]
        while work:
            node, pending = work[-1]
            descended = False
            for successor in pending:
                if successor not in index:
                    work.append(visit(successor))
                    descended = True
                    break
                if successor in on_stack:
                    lowlink[node] = min(lowlink[node], index[successor])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index[node]:
                component: list[T] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                yield component
