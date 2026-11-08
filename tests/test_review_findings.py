# starccm-mcp
# © 2026 RHerAle
# SPDX-License-Identifier: GPL-3.0-only
# Additional terms under section 7 of the GPL apply: see NOTICE.
"""Regression tests for the findings of the first adversarial review."""
import time

import pytest

from starccm_mcp import logs, session
from starccm_mcp.masking import mask

KEY = "Qw3rTy7UiOp9AsDfGh2JkL"


# ---- masking ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["20241217_1200_AAPL3_wing_M141", "Practica_02_Solucion_del_caso_inicial",
                                  "Aerodinamica_proyecto_V4", "ConstantScalarProfileMethod"])
def test_mask_keeps_simulation_names(name):
    assert mask(name) == name


@pytest.mark.parametrize("text", [f"-Dpodkey={KEY}", f"-podkey:{KEY}", f"podkey: {KEY}", f"POD_KEY={KEY}",
                                  f'{{"podkey": "{KEY}"}}', f"-podkey {KEY}", f"key {KEY} here"])
def test_mask_key_forms(text):
    assert KEY not in mask(text)


def test_mask_licence_server_forms():
    assert "lic.example.org" not in mask("License server: lic.example.org")
    assert "lic.example.org" not in mask("-licpath 1999@lic.example.org")


def test_mask_is_fast_on_pathological_input():
    t = time.perf_counter()
    mask("-" * 100_000 + "a" * 100_000)
    assert time.perf_counter() - t < 2


# ---- logs ------------------------------------------------------------------------------------------
def _fragments(s, n=8):
    return {s[i:i + n] for i in range(len(s) - n + 1)}


@pytest.mark.parametrize("pad", range(180, 200))
def test_truncation_never_leaves_a_key_fragment(pad):
    text = "x" * pad + f" -podkey {KEY} tail\n"
    out = str(logs.summarize(text)) + logs.tail(text)
    assert not any(f in out for f in _fragments(KEY))


def test_grep_cannot_probe_hidden_values():
    text = f"server -podkey {KEY}\n"
    assert logs.tail(text, grep="podkey Qw3r") == ""
    assert logs.tail(text, grep=KEY[:6]) == ""


def test_header_columns_are_masked():
    s = logs.summarize(f"     Iteration   1999@lic.example.org   -podkey   {KEY}\n")
    assert "lic.example.org" not in str(s["columns"]) and KEY not in str(s["columns"])


def test_rows_keep_their_own_header():
    text = ("     Iteration     Continuity     X-momentum             CD\n"
            "             1   1.000000e+00   2.000000e+00   3.000000e+00\n"
            "     Iteration     Continuity      CD Monitor      CL Monitor\n"
            "             2   4.000000e+00   5.000000e+00   6.000000e+00\n")
    s = logs.summarize(text)
    assert s["first_row"] == {"Iteration": 1, "Continuity": 1.0, "X-momentum": 2.0, "CD": 3.0}
    assert s["last_rows"][-1]["CL Monitor"] == 6.0


def test_nan_rows_are_kept():
    text = ("     Iteration     Continuity     X-momentum\n"
            "             1   1.000000e+00   1.000000e+00\n"
            "             2      -nan(ind)        1.#QNAN\n")
    s = logs.summarize(text)
    assert s["rows"] == 2 and s["last_rows"][-1]["Continuity"] == "-nan(ind)"


# ---- macro checks ----------------------------------------------------------------------------------
def macro(body, imports=""):
    return f"import star.common.*;\n{imports}\npublic class M extends StarMacro {{\n  public void execute() {{\n{body}\n  }}\n}}\n"


@pytest.mark.parametrize("body", [
    '// hidden \\u000a System.exit(0);',
    'Class\\u002eforName("java.lang.String");',
    'Class/**/.forName("java.lang.String");',
    'System . exit (0);',
    'Runtime r = Runtime.getRuntime(); r.exec("calc");',
    'System.getenv("CDLMD_LICENSE_FILE");',
    'new java.net.URL("http://example.org").openStream();',
    'java.lang.invoke.MethodHandles.lookup();',
    'getClass().getClassLoader().loadClass("x");',
    'getActiveSimulation().getClass().getMethods();',
])
def test_blocked_even_with_allow_risky(body):
    assert any(p.startswith("blocked") for p in session.check_macro(macro(body), allow_risky=True))


@pytest.mark.parametrize("body", [
    '// x\r Class.forName("java.lang.String");',
    '// x \\u000d Class.forName("java.lang.String");',
    'Class.for\\u200bName("java.lang.String");',
    'Cl\\u0000ass.forName("java.lang.String");',
    'System.load("C:/x/evil.dll");',
    'System.loadLibrary("evil");',
    'Object v = new java.beans.Expression("abc", "length", new Object[0]).getValue();',
    'java.util.function.Function<Class<?>, ?> f = Class::getMethods;',
    'java.awt.Desktop.getDesktop();',
    'java.rmi.Naming.lookup("x");',
    'java.util.ServiceLoader.load(Runnable.class);',
])
def test_second_review_bypasses_are_blocked(body):
    assert any(p.startswith("blocked") for p in session.check_macro(macro(body), allow_risky=True))


def test_unicode_escape_follows_the_even_backslash_rule():
    assert session._decode_unicode(r"\u0041") == "A"
    assert session._decode_unicode(r"\\u0041") == r"\\u0041"
    assert session._decode_unicode(r"\\\u0041") == "\\\\A"


def test_check_is_linear_on_long_whitespace():
    src = macro(" " * 100_000 + "\n" * 50_000 + "/**/" * 20_000 + "int x = 1;")
    t = time.perf_counter()
    session.check_macro(src)
    assert time.perf_counter() - t < 2


@pytest.mark.parametrize("body", [
    'java.util.List<String> l = java.nio.file.Files.readAllLines(java.nio.file.Paths.get("a.txt"));',
    'String s = "a\\u00f1b";',
])
def test_reading_files_and_accents_in_strings_are_allowed(body):
    assert session.check_macro(macro(body)) == []


def test_bom_is_ignored():
    assert session.check_macro("\ufeff" + macro("int x = 1;")) == []


@pytest.mark.parametrize("body", ['new java.io.RandomAccessFile("a", "rw");',
                                  'plot.export(new java.io.File("a.csv"));',
                                  'scene.printAndWait(new java.io.File("a.png"), 1, 800, 600);'])
def test_more_file_writes_are_risky(body):
    assert any(p.startswith("needs allow_risky") for p in session.check_macro(macro(body)))


def test_static_import_of_system_is_blocked():
    src = macro("exit(0);", imports="import static java.lang.System.*;")
    assert any(p.startswith("blocked") for p in session.check_macro(src, allow_risky=True))


@pytest.mark.parametrize("body", [
    'String t = """\n a " b\n """; getActiveSimulation().saveState("x.sim");',
    'java.util.function.Consumer<String> f = getActiveSimulation()::saveState;',
    'Simulation simulation_0 = getActiveSimulation(); simulation_0.close(true);',
    'getActiveSimulation().getRegionManager().removeRegions(null);',
    'getActiveSimulation().getSolution().initializeSolution();',
    'SimulationIterator it = getActiveSimulation().getSimulationIterator(); it.run();',
    'getActiveSimulation().get(MeshPipelineController.class).generateVolumeMesh();',
    'java.nio.file.Files.write(java.nio.file.Paths.get("a.sim"), new byte[0]);',
])
def test_risky_needs_permission(body):
    src = macro(body)
    assert any(p.startswith("needs allow_risky") for p in session.check_macro(src))
    assert session.check_macro(src, allow_risky=True) == []


def test_star_profile_get_method_is_allowed():
    body = ('Boundary b = getActiveSimulation().getRegionManager().getRegion("r").getBoundaryManager().getBoundary("in");\n'
            'MachNumberProfile p = b.getValues().get(MachNumberProfile.class);\n'
            'p.getMethod(ConstantScalarProfileMethod.class).getQuantity().getDefinition();')
    assert session.check_macro(macro(body)) == []


def test_built_in_info_macro_passes_its_own_check():
    assert session.check_macro(session.INFO_MACRO) == []


def test_class_name_ignores_comments():
    src = "// public class Fake\n/* public class Fake2 */\n" + macro("int x = 1;").replace("class M", "class Real")
    assert session.class_name(src) == "Real"
