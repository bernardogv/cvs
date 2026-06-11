'''
Synthetic RcclTestsAggregated rows for compare-engine unit tests.

Canonical scenarios are built by composing make_rows():
  healthy fleet        -> {node: make_rows() for node in nodes}
  one slow node        -> healthy, but node N uses make_rows(scale=0.9)
  regressed run        -> make_rows(scale=0.85) vs a baseline of make_rows()
  sagging scaling      -> per-node-count runs where the largest uses scale=0.7
'''

GRID_COLLECTIVES = ['AllReduce', 'AllGather']
GRID_SIZES = [1048576, 1073741824, 8589934592]  # 1M, 1G, 8G
BASE_BUS_BW = {
    ('AllReduce', 1048576): 35.0,
    ('AllReduce', 1073741824): 280.0,
    ('AllReduce', 8589934592): 330.0,
    ('AllGather', 1048576): 30.0,
    ('AllGather', 1073741824): 260.0,
    ('AllGather', 8589934592): 320.0,
}


def make_rows(scale=1.0, only_collective=None, dtype='float', in_place=0, nodes=None):
    """Build a list of RcclTestsAggregated-shaped dicts.

    scale: multiply busBw_mean by this factor. algBw_mean is derived as
        busBw_mean * 0.95 (typical algBw/busBw relationship), so it scales
        with `scale` too.
    only_collective: if set, scale applies only to that collective.
    dtype: must be a valid RcclTests dtype literal, e.g. 'float', 'bfloat16'.
    in_place: 0 or 1 (RcclTests InPlace literal).
    nodes: if set, include multinode metadata (nodes/ranks/ranksPerNode/gpusPerRank).
    """
    rows = []
    for name in GRID_COLLECTIVES:
        for size in GRID_SIZES:
            factor = scale if (only_collective is None or name == only_collective) else 1.0
            bus_bw = BASE_BUS_BW[(name, size)] * factor
            row = {
                'name': name,
                'size': size,
                'type': dtype,
                'inPlace': in_place,
                'num_runs': 3,
                'busBw_mean': bus_bw,
                'busBw_std': 0.5,
                'algBw_mean': bus_bw * 0.95,
                'algBw_std': 0.5,
                'time_mean': 1000.0,
                'time_std': 10.0,
            }
            if nodes is not None:
                row.update({'nodes': nodes, 'ranks': nodes * 8, 'ranksPerNode': 8, 'gpusPerRank': 1})
            rows.append(row)
    return rows
