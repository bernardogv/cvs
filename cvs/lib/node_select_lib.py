'''
Select a subset of cluster nodes from a --nodes spec, so an agent can target a
rack or a suspect node instead of the whole fleet. Pure function.
'''


def select_nodes(all_nodes, spec):
    '''Filter *all_nodes* to the comma-separated *spec*.

    Args:
        all_nodes: ordered list of node names (cluster file's node_dict keys).
        spec: comma-separated subset, or ``None``/empty for the whole cluster.

    Returns a new list in cluster order (not request order). Raises ValueError
    if *spec* names a node the cluster does not have.
    '''
    if not spec:
        return list(all_nodes)
    requested = {s.strip() for s in spec.split(',') if s.strip()}
    known = set(all_nodes)
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f'--nodes: unknown node(s) {unknown}; cluster has {sorted(known)}')
    return [n for n in all_nodes if n in requested]
