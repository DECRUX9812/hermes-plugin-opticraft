"""Cemented achromat design: solve the glass, then *optimize* the one free bend.

The achromatic condition fixes the two element powers:

    phi_c + phi_f = phi            and      phi_c/V_c + phi_f/V_f = 0
    => phi_c = V_c/(V_c - V_f) * phi,  phi_f = -V_f/(V_c - V_f) * phi

A cemented doublet has one internal radius shared by both elements and two outer
radii, so once the powers are fixed there is exactly **one free parameter**: the
internal radius R2. That makes the design a one-dimensional optimization, and the
engine does it for real — it sweeps R2 and keeps the shape with the smallest
computed RMS spot at the requested focal ratio. A classic catalog doublet is
recovered from first principles rather than copied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .glass import LINES, glass as get_glass
from .trace import Surface, paraxial, trace_ray


@dataclass
class DoubletSolution:
    """A cemented achromat: crown element first, flint element second."""

    crown: str
    flint: str
    efl_mm: float
    aperture_mm: float
    f_number: float
    r1: float
    r2: float
    r3: float
    element_thickness_mm: float
    crown_power: float
    flint_power: float
    crown_efl: float
    flint_efl: float
    rms_spot_mm: float
    surfaces: list[Surface]
    trials: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "design": "cemented achromat (crown + flint, two elements)",
            "crown": self.crown,
            "flint": self.flint,
            "efl_mm": round(self.efl_mm, 3),
            "aperture_mm": round(self.aperture_mm, 3),
            "f_number": round(self.f_number, 2),
            "radii_mm": {"r1": round(self.r1, 3), "r2": round(self.r2, 3), "r3": round(self.r3, 3)},
            "element_thickness_mm": round(self.element_thickness_mm, 3),
            "powers": {"crown": round(self.crown_power, 5), "flint": round(self.flint_power, 5)},
            "element_focal_lengths_mm": {
                "crown": round(self.crown_efl, 3),
                "flint": round(self.flint_efl, 3),
            },
            "rms_spot_mm": round(self.rms_spot_mm, 5),
            "shapes_tried": self.trials,
            "surfaces": [
                {
                    "radius_mm": round(s.radius, 3),
                    "thickness_mm": round(s.thickness, 3),
                    "glass_after": s.glass_after or "air",
                    "semi_aperture_mm": round(s.semi_aperture, 3),
                }
                for s in self.surfaces
            ],
        }


def _rms_spot(surfaces: list[Surface], semi: float, wavelength_nm: float, samples: int = 15) -> float:
    """RMS spot at the paraxial focus — the objective the bend search minimizes."""
    px = paraxial(surfaces, wavelength_nm)
    if not math.isfinite(px["efl"]) or px["efl"] <= 0:
        return math.inf
    z = abs(px["bfd"])
    ys: list[float] = []
    for i in range(samples):
        h = (i / max(samples - 1, 1) * 2.0 - 1.0) * semi * 0.98
        r = trace_ray(h, 0.0, surfaces, wavelength_nm)
        if r is None:
            return math.inf
        ys.append(r["height_out"] + r["slope_out"] * z)
    mean = sum(ys) / len(ys)
    return math.sqrt(sum((y - mean) ** 2 for y in ys) / len(ys))


def design_achromat(
    efl_mm: float,
    aperture_mm: float,
    *,
    crown: str = "N-BK7",
    flint: str = "N-SF5",
    wavelengths: tuple[float, ...] = (LINES["d"],),
    bend_trials: int = 400,
) -> DoubletSolution:
    """Solve and optimize a cemented achromat for a target EFL and aperture."""
    if efl_mm <= 0 or aperture_mm <= 0:
        raise ValueError("efl_mm and aperture_mm must be positive")

    g_c, g_f = get_glass(crown), get_glass(flint)
    nd_c = g_c.index(LINES["d"])
    nd_f = g_f.index(LINES["d"])
    v_c, v_f = g_c.vd(), g_f.vd()

    phi = 1.0 / efl_mm
    if abs(v_c - v_f) < 1e-6:
        raise ValueError(f"{crown} and {flint} have nearly equal Abbe numbers; no achromat exists")
    phi_c = phi * v_c / (v_c - v_f)
    phi_f = phi - phi_c
    if phi_f == 0.0:
        raise ValueError("the flint element has zero power: pick glasses with different Abbe numbers")

    semi = aperture_mm / 2.0
    t = max(2.0, aperture_mm * 0.15)

    # curvature constants from each element's power at the d line
    k_c = phi_c / (nd_c - 1.0)   # 1/R1 - 1/R2
    k_f = phi_f / (nd_f - 1.0)   # 1/R2 - 1/R3

    def radii(r2: float) -> tuple[float, float, float] | None:
        inv2 = 1.0 / r2
        inv1 = k_c + inv2
        inv3 = inv2 - k_f
        if inv1 == 0.0 or inv3 == 0.0:
            return None
        return 1.0 / inv1, r2, 1.0 / inv3

    def build(r1: float, r2: float, r3: float) -> list[Surface]:
        return [
            Surface(radius=r1, thickness=t, glass_after=g_c.name, semi_aperture=semi),
            Surface(radius=r2, thickness=t, glass_after=g_f.name, semi_aperture=semi),
            Surface(radius=r3, thickness=0.0, glass_after="", semi_aperture=semi),
        ]

    # The one free parameter: sweep the internal radius. Skip shapes whose
    # surfaces are tighter than the clear aperture (unbuildable), and shapes
    # whose power or EFL diverges.
    best: tuple[float, float, float, float] | None = None   # rms, r1, r2, r3
    tried = 0
    for i in range(bend_trials):
        r2 = -semi * 1.10 * (1.0 + 6.0 * (i / max(bend_trials - 1, 1)))
        got = radii(r2)
        if got is None:
            continue
        r1, _, r3 = got
        if not all(math.isfinite(x) and abs(x) >= semi * 1.05 for x in (r1, r3)):
            continue
        surf = build(r1, r2, r3)
        px = paraxial(surf, LINES["d"])
        if not math.isfinite(px["efl"]) or abs(px["efl"] - efl_mm) > efl_mm * 0.15:
            continue
        tried += 1
        worst = max(_rms_spot(surf, semi, w) for w in wavelengths)
        if best is None or worst < best[0]:
            best = (worst, r1, r2, r3)

    if best is None:
        raise ValueError(
            "no buildable bend found: the aperture is too large for this focal length in these glasses "
            "(try a slower f-number or a smaller aperture)"
        )

    rms, r1, r2, r3 = best
    surfaces = build(r1, r2, r3)
    return DoubletSolution(
        crown=g_c.name, flint=g_f.name, efl_mm=efl_mm, aperture_mm=aperture_mm,
        f_number=abs(efl_mm) / aperture_mm, r1=r1, r2=r2, r3=r3,
        element_thickness_mm=t,
        crown_power=phi_c, flint_power=phi_f,
        crown_efl=1.0 / phi_c if phi_c else math.inf,
        flint_efl=1.0 / phi_f if phi_f else math.inf,
        rms_spot_mm=rms, surfaces=surfaces, trials=tried,
    )


# --- colour error ---------------------------------------------------------

def colour_focus_shift(surfaces: list[Surface], *, line_a: str = "C", line_b: str = "F") -> dict[str, Any]:
    """Axial focus difference between two Fraunhofer lines — the real colour error."""
    la, lb = LINES[line_a], LINES[line_b]
    fa = abs(paraxial(surfaces, la)["bfd"])
    fb = abs(paraxial(surfaces, lb)["bfd"])
    shift = abs(fa - fb)
    return {
        "line_a_nm": la,
        "line_b_nm": lb,
        "focus_a_mm": round(fa, 5),
        "focus_b_mm": round(fb, 5),
        "axial_shift_mm": round(shift, 5),
        "verdict": _colour_verdict(shift),
    }


def _colour_verdict(shift_mm: float) -> str:
    if shift_mm <= 0.02:
        return "colour-free at this size: the shift is below the usable depth of focus"
    if shift_mm <= 0.1:
        return "very good: a faint fringe only at the widest aperture"
    if shift_mm <= 0.5:
        return "usable: visible colour at the edge until you stop down"
    if shift_mm <= 2.0:
        return "heavy colour fringing: this is a single lens, not an achromat"
    return "unusable colour: no chromatic correction at all"


def singlet_for_comparison(efl_mm: float, aperture_mm: float, glass_name: str = "N-BK7") -> list[Surface]:
    """The same focal length in one element, so the contrast is measured, not claimed."""
    g = get_glass(glass_name)
    nd = g.index(LINES["d"])
    semi = aperture_mm / 2.0
    t = max(2.0, aperture_mm * 0.15)
    # thick equal-biconvex: phi = 2(n-1)/r - (t/n)(n-1)^2/r^2, solve for r
    phi_target = 1.0 / efl_mm
    k1 = 2.0 * (nd - 1.0)
    k2 = (t / nd) * (nd - 1.0) ** 2
    disc = k1 * k1 - 4.0 * k2 * phi_target
    if k2 > 0 and disc > 0:
        inv_r = (k1 - math.sqrt(disc)) / (2.0 * k2)
    else:
        inv_r = phi_target / k1
    r = 1.0 / inv_r if inv_r else math.inf
    return [
        Surface(radius=r, thickness=t, glass_after=g.name, semi_aperture=semi),
        Surface(radius=-r, thickness=0.0, glass_after="", semi_aperture=semi),
    ]
