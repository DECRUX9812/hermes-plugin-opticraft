"""Glass catalogue and Sellmeier dispersion tests.

The point of these tests is that a mistyped coefficient fails the build: every
glass is checked against the manufacturer's published nd and Vd, so the model the
engine uses and the databook the user reads cannot disagree.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opticraft.glass import GLASSES, LINES, catalogue, glass  # noqa: E402


def test_every_glass_matches_its_published_nd():
    for name, g in GLASSES.items():
        nd = g.index(LINES["d"])
        assert abs(nd - g.nd_published) < 2e-4, f"{name}: model {nd:.5f} vs published {g.nd_published:.5f}"


def test_every_glass_matches_its_published_vd():
    for name, g in GLASSES.items():
        vd = g.vd()
        assert abs(vd - g.vd_published) < 1.0, f"{name}: model {vd:.2f} vs published {g.vd_published:.2f}"


def test_dispersion_decreases_with_wavelength():
    """Normal dispersion: index must fall from F (486) to C (656)."""
    for name, g in GLASSES.items():
        nf = g.index(LINES["F"])
        nc = g.index(LINES["C"])
        assert nf > nc, f"{name}: nF {nf} should exceed nC {nc}"


def test_crowns_have_higher_abbe_than_flints():
    crown = glass("N-BK7").vd()
    flint = glass("N-SF5").vd()
    assert crown > 50 > flint, f"{crown:.1f} / {flint:.1f}"


def test_unknown_glass_is_rejected_with_a_list():
    try:
        glass("Unobtanium")
    except KeyError as exc:
        assert "N-BK7" in str(exc), "the error should name the available glasses"
    else:
        raise AssertionError("unknown glass was accepted")


def test_catalogue_reports_computed_values():
    rows = catalogue()
    assert len(rows) == len(GLASSES)
    for row in rows:
        assert row["crown_or_flint"] in {"crown", "flint"}
