# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
import pytest

from starccm_mcp import simfile


def test_overview(sim_path):
    o = simfile.overview(simfile.open_sim(str(sim_path)))
    assert o["simulation"] == "demo"
    assert o["saved_with"] == "2502.0001 (20.02.008)"
    assert o["parallel"] is True
    assert o["current_iteration"] == 3
    assert o["volume_mesh"]["cells"] == 1234
    assert o["regions"] == ["fluid"]
    assert o["monitors"] == ["CD Monitor"]
    crit = o["stopping_criteria"][0]
    assert crit["used"] is True and crit["satisfied"] is False
    assert crit["settings"]["MaximumNumberSteps"]["value"] == 1000.0
    assert o["save_history"] == ["Sun Nov  8 2026\n\nSaved Simulation as demo.sim"]


def test_parameters(sim_path):
    assert simfile.parameters(simfile.open_sim(str(sim_path))) == [
        {"name": "M", "type": "ScalarGlobalParameter", "value": 0.7, "units": ""}]


def test_boundaries(sim_path):
    (b,) = simfile.boundaries(simfile.open_sim(str(sim_path)))
    assert (b["region"], b["name"], b["type"]) == ("fluid", "inlet", "FreeStreamBoundary")
    assert b["options_selected_index"] == {"FlowDirectionOption": 1}
    assert b["values"]["MachNumberProfile"] == {"method": "ConstantScalarProfileMethod", "value": 0.7, "units": "",
                                                "definition": "${M}"}
    assert simfile.boundaries(simfile.open_sim(str(sim_path)), region="other") == []


def test_monitor_series(sim_path):
    sim = simfile.open_sim(str(sim_path))
    assert simfile.monitors(sim)[0]["report"] == "CD"
    s = simfile.monitor_series(sim, "cd monitor", last=2)
    assert s["x"] == [2.0, 3.0]
    assert s["y"]["YAxisData"] == [0.25, 0.125]
    with pytest.raises(KeyError):
        simfile.monitor_series(sim, "nope")


def test_find_and_settings(sim_path):
    sim = simfile.open_sim(str(sim_path))
    hits = simfile.find(sim, "^CD$")
    assert [h["record"] for h in hits["items"]] == [21]
    assert hits["items"][0]["parent"] == "MonitorManager"
    settings = sim.settings(21, 1)
    assert settings["ReferenceVelocity"] == {"value": 10.0, "units": "m/s", "definition": "${V}"}


def test_counts_are_not_references(sim_path):
    sim = simfile.open_sim(str(sim_path))
    assert sim.settings(27, 1)["CellCount"] == 1234


def test_not_a_sim(tmp_path):
    p = tmp_path / "x.sim"
    p.write_text("hello")
    with pytest.raises(ValueError):
        simfile.open_sim(str(p))
