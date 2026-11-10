"""Achromat, spot and tolerance tests — the claims the demo makes."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opticraft.achromat import (  # noqa: E402
    colour_focus_shift,
    design_achromat,
    singlet_for_comparison,
)
from opticraft.glass import LINES  # noqa: E402
from opticraft.spot import spot_diagram, system_report, tolerance  # noqa: E402
from opticraft.trace import paraxial  # noqa: E402


def test_design_hits_its_focal_length():
    for efl, ap in ((50.0, 12.5), (100.0, 25.0), (200.0, 50.0)):
        d = design_achromat(efl, ap)
        got = paraxial(d.surfaces, LINES["d"])["efl"]
        assert abs(got - efl) < efl * 0.02, f"target {efl}: got {got:.2f}"


def test_doublet_beats_singlet_on_colour():
    """The second element exists to fix colour; measure it, do not assert it."""
    d = design_achromat(100.0, 25.0)
    s = singlet_for_comparison(100.0, 25.0)
    c_doublet = colour_focus_shift(d.surfaces)["axial_shift_mm"]
    c_singlet = colour_focus_shift(s)["axial_shift_mm"]
    assert c_doublet * 5 < c_singlet, f"doublet {c_doublet:.4f} vs singlet {c_singlet:.4f}"


def test_doublet_beats_singlet_on_spot():
    d = design_achromat(100.0, 25.0)
    s = singlet_for_comparison(100.0, 25.0)
    rms_d = system_report(d.surfaces)["summary"]["spot_rms_mm"]
    rms_s = system_report(s)["summary"]["spot_rms_mm"]
    assert rms_d * 5 < rms_s, f"doublet rms {rms_d:.5f} vs singlet {rms_s:.5f}"


def test_design_is_diffraction_limited_at_f4():
    d = design_achromat(100.0, 25.0)
    spot = spot_diagram(d.surfaces)
    assert spot.ratio_to_airy <= 2.0, f"ratio {spot.ratio_to_airy:.2f}"
    assert "diffraction" in spot.verdict


def test_airy_diameter_tracks_f_number():
    d = design_achromat(100.0, 25.0)   # f/4
    d2 = design_achromat(100.0, 12.5)  # f/8
    a4 = spot_diagram(d.surfaces).airy_diameter_mm
    a8 = spot_diagram(d2.surfaces).airy_diameter_mm
    assert abs(a8 / a4 - 2.0) < 0.2, f"f/8 airy {a8:.4f} should be ~2x f/4 {a4:.4f}"


def test_unbuildable_request_is_refused_with_a_reason():
    try:
        design_achromat(20.0, 60.0)  # f/0.33: no glass can do this
    except ValueError as exc:
        assert "aperture" in str(exc).lower() or "f-number" in str(exc).lower()
    else:
        raise AssertionError("an impossible f-number was accepted")


def test_tolerance_compares_against_depth_of_focus():
    d = design_achromat(100.0, 25.0)
    tol = tolerance(d.surfaces)
    assert tol["focus_depth_mm"] > 0
    assert tol["worst_case_mm"] >= 0
    assert tol["verdict"]


def test_slower_system_tolerates_more():
    """Depth of focus scales with (f/#)^2 — the engine must show that."""
    fast = design_achromat(100.0, 50.0)   # f/2
    slow = design_achromat(100.0, 12.5)   # f/8
    assert tolerance(slow.surfaces)["focus_depth_mm"] > tolerance(fast.surfaces)["focus_depth_mm"] * 10


def test_spot_at_field_still_returns_a_verdict():
    d = design_achromat(100.0, 25.0)
    spot = spot_diagram(d.surfaces, field_deg=2.0)
    assert spot.verdict
    assert math.isfinite(spot.rms_mm) or "vignetted" in spot.verdict
