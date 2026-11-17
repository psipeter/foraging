"""The reachable-region tool (map_region.py): the sample is reproducible and the summary accounts for every map."""

import map_region


def test_the_sample_is_reproducible_and_the_summary_counts_every_map():
    a, b = map_region.sample(20, seed=5), map_region.sample(20, seed=5)
    assert [d["gini"] for _, d in a] == [d["gini"] for _, d in b]
    rows = map_region.summarise(a)
    assert sum(r[0] + r[3] for r in rows.values()) == 20
