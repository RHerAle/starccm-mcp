from starccm_mcp import logs, session
from starccm_mcp.masking import mask

FAKE_KEY = "AbCdEf0123456789XyZ0Qq"
LOG = f"""Starting server
WARNING [x]: something odd
     Iteration     Continuity     X-momentum     CD Monitor
             1   1.000000e+00   1.000000e+00   5.000000e-01
Reversed flow on  12 faces on Fluid: outlet
             2   5.000000e-01   4.000000e-01   4.000000e-01

Error: AMG solver diverged.
     Iteration     Continuity     X-momentum     CD Monitor
             3   2.500000e-01   2.000000e-01   3.500000e-01
server cmd: starccm+ -power -podkey {FAKE_KEY} -licpath 1999@flex.example.com -np 6
"""


def test_iteration_table():
    s = logs.summarize(LOG)
    assert s["columns"] == ["Iteration", "Continuity", "X-momentum", "CD Monitor"]
    assert s["rows"] == 3 and s["tables_printed"] == 2
    assert s["last_rows"][-1] == {"Iteration": 3, "Continuity": 0.25, "X-momentum": 0.2, "CD Monitor": 0.35}
    kinds = {e["kind"]: e for e in s["events"]}
    assert kinds["reversed_flow"]["first_iteration"] == 1
    assert kinds["amg"]["first_iteration"] == 2
    assert "warning" in kinds


def test_no_licence_data_leaks():
    out = logs.tail(LOG) + str(logs.summarize(LOG))
    assert FAKE_KEY not in out and "flex.example.com" not in out and "1999@" not in out


def test_mask_rules():
    assert mask("-podkey abc123") == "-podkey <masked>"
    assert mask('-licpath "1999@host.example.org"') == "-licpath <masked>"
    assert "10.0.0.12" not in mask("server at 10.0.0.12 ready")
    assert mask("CDLMD_LICENSE_FILE=1999@x") == "CDLMD_LICENSE_FILE=<masked>"
    # ordinary text survives
    assert mask("STAR-CCM+ 20.02.008 ConstantScalarProfileMethod") == "STAR-CCM+ 20.02.008 ConstantScalarProfileMethod"


MACRO = """import star.common.*;
public class M extends StarMacro {
  public void execute() { %s }
}
"""


def test_reflection_is_always_blocked():
    src = MACRO % "for (java.lang.reflect.Method m : getClass().getMethods()) {}"
    assert any(p.startswith("blocked") for p in session.check_macro(src, allow_risky=True))


def test_risky_needs_permission():
    src = MACRO % 'getActiveSimulation().saveState("x.sim");'
    assert session.check_macro(src) and session.check_macro(src, allow_risky=True) == []


def test_comments_and_strings_do_not_trigger():
    src = MACRO % '// saveState( and getMethods() in a comment\n getActiveSimulation().println("saveState(");'
    assert session.check_macro(src) == []


def test_needs_starmacro():
    assert session.check_macro("public class X { }")


def test_parse_info():
    info = session.parse_info(["simulation|demo", "boundary|fluid|inlet|Free Stream",
                               "parameter|M|0.7|0.7|", "continuum|Air|Steady;Gas;", "done|ok"])
    assert info["simulation"] == "demo" and info["done"] == "ok"
    assert info["boundaries"] == [{"region": "fluid", "name": "inlet", "type": "Free Stream"}]
    assert info["parameters"][0] == {"name": "M", "definition": "0.7", "value": "0.7", "units": ""}
    assert info["continua"] == [{"name": "Air", "models": ["Steady", "Gas"]}]
