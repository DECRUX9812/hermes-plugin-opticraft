"""Ray-trace and paraxial tests.

The critical one is ``test_real_trace_converges_to_paraxial``: a real meridional
trace and a matrix paraxial solve are two independent derivations of the same
lens, so if they agree at a small aperture the trace is right. The rest pin the
behaviour that makes the engine useful: spherical aberration is real and grows
with aperture, and axial rays do not vignette.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opticraft.glass import LINES  # noqa: E402
from opticraft.trace import (  # noqa: E402
    Surface,
    design_report,
    paraxial,
    surface_power,
    trace_ray,
)

# BK7 biconvex singlet, R = +/-51.5 mm, 4 mm thick
SINGLET = [
    Surface(radius=51.5, thickness=4.0, glass_after="N-BK7", semi_aperture=12.5),
    Surface(radius=-51.5, thickness=0.0, glass_after="", semi_aperture=12.5),
]


def test_surface_power_sign():
    # entering glass: positive radius gives positive power
    assert surface_power(51.5, 1.0, 1.5168) > 0
    assert surface_power(0.0, 1.0, 1.5) == 0.0


def test_paraxial_matches_the_thick_lens_formula():
    px = paraxial(SINGLET, LINES["d"])
    # hand calculation: phi = (n-1)(1/R1 - 1/R2) - (t/n)(n-1)^2*(1/R1)*(1/R2)
    n = 1.5168
    r1, r2, t = 51.5, -51.5, 4.0
    phi1 = (n - 1.0) / r1
    phi2 = (1.0 - n) / r2
    phi = phi1 + phi2 - (t / n) * phi1 * phi2
    assert abs(px["efl"] - 1.0 / phi) < 0.02, f"{px['efl']:.4f} vs {1.0 / phi:.4f}"
    assert abs(px["bfd"] - (1.0 / phi - (t / n) * phi1 * (1.0 / phi))) < 0.02


def test_real_trace_converges_to_paraxial():
    """Two independent derivations must agree at a small aperture."""
    px = paraxial(SINGLET, LINES["d"])
    for height in (0.001, 0.01, 0.05):
        r = trace_ray(height, 0.0, SINGLET, LINES["d"])
        assert r is not None, "the axial ray vignetted"
        bfd = -r["height_out"] / r["slope_out"]
        assert abs(bfd - px["bfd"]) < 0.05, f"y={height}: traced {bfd:.4f} vs paraxial {px['bfd']:.4f}"


def test_axial_ray_is_not_vignetted():
    r = trace_ray(0.0, 0.0, SINGLET, LINES["d"])
    assert r is not None
    assert r["height_out"] == 0.0


def test_spherical_aberration_grows_with_aperture():
    """The whole point of real rays: the edge focuses closer than the centre."""
    small = trace_ray(1.0, 0.0, SINGLET, LINES["d"])
    big = trace_ray(12.0, 0.0, SINGLET, LINES["d"])
    assert big is not None
    bfd_small = -small["height_out"] / small["slope_out"]
    bfd_big = -big["height_out"] / big["slope_out"]
    assert bfd_big < bfd_small - 0.5, "the marginal focus should be measurably shorter"


def test_vignetting_is_reported_not_silently_clipped():
    assert trace_ray(14.0, 0.0, SINGLET, LINES["d"]) is None


def test_report_contains_the_honest_numbers():
    r = design_report(SINGLET)
    assert r["paraxial"]["efl"] > 0
    assert r["spherical_aberration_mm"] > 0
    assert r["blur_diameter_mm"] > 0
    assert r["vignetted_rays"] == 0


def test_plane_surface_power_is_zero():
    surf = [Surface(radius=0.0, thickness=5.0, glass_after="N-BK7", semi_aperture=10),
            Surface(radius=0.0, thickness=0.0, glass_after="", semi_aperture=10)]
    px = paraxial(surf, LINES["d"])
    assert px["power"] == 0.0
