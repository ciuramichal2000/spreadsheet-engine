import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sheetcalc.graph import strongly_connected_components


def components(roots, edges):
    return list(strongly_connected_components(roots, lambda node: edges.get(node, [])))


def test_a_cycle_is_one_component_emitted_before_the_nodes_that_use_it():
    edges = {"d": ["a"], "a": ["b"], "b": ["c"], "c": ["b"]}
    result = [sorted(component) for component in components(["d"], edges)]
    assert result == [["b", "c"], ["a"], ["d"]]


def test_shared_dependency_comes_out_before_both_users():
    edges = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
    order = [component[0] for component in components(["a"], edges)]
    assert sorted(order) == ["a", "b", "c", "d"]
    assert order[0] == "d"
    assert order[-1] == "a"


def test_every_node_is_reported_once_even_with_several_roots():
    edges = {"a": ["c"], "b": ["c"]}
    order = [component[0] for component in components(["a", "b", "c", "a"], edges)]
    assert sorted(order) == ["a", "b", "c"]


def test_a_node_pointing_at_itself_is_a_single_node_component():
    assert components(["a"], {"a": ["a"]}) == [["a"]]


def test_chain_far_longer_than_the_recursion_limit_is_handled():
    length = 5000
    edges = {n: [n + 1] for n in range(length - 1)}
    result = components([0], edges)
    assert len(result) == length
    assert result[0] == [length - 1]  # the end of the chain has no dependencies: first
    assert result[-1] == [0]
