from __future__ import annotations

import alphascanner_ui.data as ui_data


def test_get_sector_mapping_loads_local_cache():
    ui_data.get_sector_mapping.clear()

    nifty_mapping = ui_data.get_sector_mapping("Nifty 500")
    total_mapping = ui_data.get_sector_mapping("Total Market (Cap Focused)")

    assert len(nifty_mapping) == 500
    assert len(total_mapping) == 751
    assert "RELIANCE.NS" in nifty_mapping
    assert "RELIANCE.NS" in total_mapping


def test_fetch_fii_dii_data_uses_cached_flow(monkeypatch):
    ui_data.fetch_fii_dii_data.clear()

    monkeypatch.setattr(
        ui_data,
        "load_institutional_flow",
        lambda: {
            "date": "2026-07-25",
            "fii_net": 123.0,
            "dii_net": -45.0,
            "fii_buy": 200.0,
            "fii_sell": 77.0,
            "dii_buy": 88.0,
            "dii_sell": 133.0,
        },
    )

    flow = ui_data.fetch_fii_dii_data()

    assert flow["date"] == "2026-07-25"
    assert flow["fii_net"] == 123.0
    assert flow["dii_net"] == -45.0
