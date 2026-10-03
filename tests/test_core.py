from sunflow.core import TimeGrid, load_config


def test_timegrid_blocks():
    g = TimeGrid()
    assert g.N == 96
    assert g.block_of("07:30") == 30
    assert g.block_of("17:30") == 70
    assert g.label(30) == "07:30"
    assert len(g.blocks_between("09:00", "17:00")) == 32


def test_config_topology(cfg):
    names = [f.name for f in cfg.feeders]
    assert names == ["Kharosa", "Jawali", "Lamjana II", "Chalburga"]
    assert [f.name for f in cfg.feeders_on_pt("PT-2")] == ["Jawali", "Lamjana II", "Chalburga"]
    assert [f.name for f in cfg.feeders_on_pt("PT-1")] == ["Kharosa"]
    assert cfg.pt("PT-2").rating_kva == 5000


def test_published_slots_are_eight_hours(cfg):
    g = TimeGrid()
    for f in cfg.feeders:
        s, e = f.published_slot
        assert len(g.blocks_between(s, e)) == cfg.rules.min_blocks_per_feeder


def test_dt_expansion(cfg):
    for f in cfg.feeders:
        assert len(f.dts) == f.n_dts
        assert all(d.n_pumps > 0 and d.rating_kva in (63, 100) for d in f.dts)
    # PT-2 installed kVA at full participation exceeds its rating (the problem the planner manages)
    pt2 = sum(cfg.feeder_installed_kva(f) for f in cfg.feeders_on_pt("PT-2"))
    assert pt2 > cfg.pt("PT-2").rating_kva
    # but at the P90 participation used for planning/verification it fits
    assert pt2 * cfg.verification.participation < cfg.pt("PT-2").rating_kva
