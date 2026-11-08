# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Builds a tiny synthetic .sim with the same layout STAR-CCM+ 2502 writes, so tests need no real files."""
import struct

import pytest

STATE = [
    # record -2 and 0: version records
    "{'ClassName': 'StarVersion', 'PresentationVersion': '2502.0001', 'ReleaseNumber': '20.02.008'}",
    "",
    "{'ClassName': 'StarVersion', 'PresentationVersion': '2502.0001', 'ReleaseNumber': '20.02.008'}",
    "{'ClassName': 'star.common.Simulation', 'name': 'demo', 'parallel': true, 'TaskManager': 0L}",  # 1
    "{'ClassName': 'star.common.SimulationIterator', 'CurrentIteration': 3L}",  # 2
    "{'ClassName': 'star.common.Region', 'PresentationName': 'fluid'}",  # 3
    "{'ClassName': 'star.common.Boundary', 'PresentationName': 'inlet', 'Region': 3L, "
    "'StageableConditionType': 5L, 'Objects': 7L}",  # 4
    "{'ClassName': 'star.common.StageableConditionType', 'BoundaryType': 6L}",  # 5
    "{'ClassName': 'star.flow.FreeStreamBoundary'}",  # 6
    "{'ClassName': 'star.common.ConditionManager', 'Keys': [8L]}",  # 7
    "{'ClassName': 'star.common.ValueManager', 'Keys': [9L, 10L]}",  # 8
    "{'ClassName': 'star.flow.FlowDirectionOption', 'Selected': 1, 'AvailableOptionsVector': [0, 1, 2]}",  # 9
    "{'ClassName': 'star.flow.MachNumberProfile', 'Method': 11L}",  # 10
    "{'ClassName': 'star.common.ConstantScalarProfileMethod', 'Quantity': 12L}",  # 11
    "{'ClassName': 'star.common.ScalarPhysicalQuantity', 'Definition': '${M}', 'Value': 0.7, 'Units': 0L}",  # 12
    "{'ClassName': 'star.common.ScalarGlobalParameter', 'PresentationName': 'M', 'Quantity': 14L}",  # 13
    "{'ClassName': 'star.common.ScalarPhysicalQuantity', 'Value': 0.7, 'Units': 0L}",  # 14
    "{'ClassName': 'star.common.Units', 'PresentationName': 'm/s'}",  # 15
    "{'ClassName': 'star.base.report.MonitorManager', 'Keys': [17L]}",  # 16
    "{'ClassName': 'star.base.report.ReportMonitor', 'PresentationName': 'CD Monitor', 'XAxisData': 18L, "
    "'MultiYAxisData': 19L, 'Report': 21L}",  # 17
    "{'ClassName': 'MasterArray<Float8>', 'dataKey': XKEYL, 'size': 3L}",  # 18
    "{'ClassName': 'YAxisValues', 'keys': ['YAxisData'], 'values': [20L]}",  # 19
    "{'ClassName': 'MasterArray<Float8>', 'dataKey': YKEYL, 'size': 3L}",  # 20
    "{'ClassName': 'star.flow.ForceCoefficientReport', 'PresentationName': 'CD', 'ReferenceVelocity': 22L, "
    "'Parent': 16L}",  # 21
    "{'ClassName': 'star.common.ScalarPhysicalQuantity', 'Definition': '${V}', 'Value': 10.0, 'Units': 15L}",  # 22
    "{'ClassName': 'star.common.StarLog', 'Log': '\\n----------------------------------------\\nSun Nov  8 2026"
    "\\n\\nSaved Simulation as demo.sim\\n'}",  # 23
    "{'ClassName': 'star.common.StepStoppingCriterion', 'PresentationName': 'Maximum Steps', 'IsUsed': true, "
    "'IsSatisfied': false, 'MaximumNumberSteps': 25L}",  # 24
    "{'ClassName': 'star.common.IntegerValue', 'Quantity': 26L}",  # 25
    "{'ClassName': 'star.common.ScalarPhysicalQuantity', 'Value': 1000.0, 'Units': 0L}",  # 26
    "{'ClassName': 'star.common.FvRepresentation', 'PresentationName': 'Volume Mesh', 'CellCount': 1234L, "
    "'InteriorFaceCount': 5L, 'VertexCount': 6L}",  # 27
]


def build_sim(path):
    head_len = len(b"{'Binary': '', 'ClassName': 'STAR', 'StatePosition': 0000000000L, 'Version': 3}\n")
    arr = lambda vals: (b"{'ClassName': 'Array', 'Type': 'Float8', 'nElements': %dL, 'sizeof<T>': 8}\n" % len(vals)
                        + struct.pack(f"<{len(vals)}d", *vals))
    ax, ay = arr([1.0, 2.0, 3.0]), arr([0.5, 0.25, 0.125])
    xkey, ykey = head_len, head_len + len(ax)
    state = "\n".join(STATE).replace("XKEY", str(xkey)).replace("YKEY", str(ykey)).encode()
    pos = head_len + len(ax) + len(ay)
    head = b"{'Binary': '', 'ClassName': 'STAR', 'StatePosition': %010dL, 'Version': 3}\n" % pos
    assert len(head) == head_len
    path.write_bytes(head + ax + ay + state + b"\n")
    return path


@pytest.fixture
def sim_path(tmp_path):
    return build_sim(tmp_path / "demo.sim")
