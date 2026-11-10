"""Spot diagrams, the diffraction limit, and the tolerance question.

A design is not done when the paraxial numbers look right: you have to know how
big the blur is against the Airy disc, and how much of it a real mount can
afford to lose. Both are computed here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .glass import LINES
from .trace import Surface, design_report, paraxial, trace_ray

# Diffraction: Airy radius = 1.22 * lambda * f/#
AIRY_FACTOR = 1.22


@dataclass
class Spot:
    """A computed spot diagram: rays across the aperture and pupil, at one field."""

    field_deg: float
    wavelength_nm: float
    points: list[tuple[float, float]]
    rms_mm: float
    geometric_blur_mm: float
    airy_diameter_mm: float
    ratio_to_airy: float
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_deg": self.field_deg,
            "wavelength_nm": self.wavelength_nm,
            "points": [[round(x, 5), round(y, 5)] for x, y in self.points],
            "rms_mm": round(self.rms_mm, 5),
            "geometric_blur_mm": round(self.geometric_blur_mm, 5),
            "airy_diameter_mm": round(self.airy_diameter_mm, 5),
            "ratio_to_airy": round(self.ratio_to_airy, 2),
            "verdict": self.verdict,
        }


def spot_diagram(
    surfaces: Sequence[Surface],
    *,
    field_deg: float = 0.0,
    wavelength_nm: float = LINES["d"],
    rings: int = 3,
    arms: int = 6,
    samples_per_arm: int = 7,
    focus_mm: float | None = None,
) -> Spot:
    """Fan of rays over the aperture, intersected with the image plane.

    ``focus_mm`` is measured from the last vertex; ``None`` puts the image
    plane at the paraxial focus, which is what a datasheet's spot diagram uses.
    """
    px = paraxial(surfaces, wavelength_nm)
    fnum = px["f_number"]
    semi = max(s.semi_aperture for s in surfaces)
    # trace_ray returns coordinates relative to the LAST vertex, and a paraxial
    # BFD is a positive distance past it — so the image plane is at +bfd, not -bfd.
    image_z_local = abs(px["bfd"]) if focus_mm is None else focus_mm

    slope0 = math.tan(math.radians(field_deg))
    pts: list[tuple[float, float]] = []
    for ring in range(1, rings + 1):
        frac = ring / rings
        for arm in range(arms):
            for k in range(samples_per_arm):
                # sample the pupil on a ring/arm grid
                theta = 2.0 * math.pi * arm / arms
                off = (k / max(samples_per_arm - 1, 1) - 0.5) * (2.0 * math.pi / arms) * 0.6
                ang = theta + off
                h_y = frac * semi * math.sin(ang)
                # meridional only, so the pupil point is a height; the field adds a slope
                r = trace_ray(h_y, slope0, surfaces, wavelength_nm)
                if r is None:
                    continue
                # y at the image plane distance from the last vertex
                y_img = r["height_out"] + r["slope_out"] * image_z_local
                pts.append((0.0, y_img))

    if not pts:
        return Spot(field_deg, wavelength_nm, [], math.inf, math.inf, math.inf, math.inf,
                    "no ray reached the image plane: every ray vignetted")

    ys = [p[1] for p in pts]
    mean = sum(ys) / len(ys)
    rms = math.sqrt(sum((y - mean) ** 2 for y in ys) / len(ys))
    blur = max(ys) - min(ys)
    airy = 2.0 * AIRY_FACTOR * (wavelength_nm * 1e-6) * abs(fnum)
    ratio = (rms * 2.0) / airy if airy else math.inf
    verdict = _spot_verdict(ratio)
    return Spot(
        field_deg=field_deg, wavelength_nm=wavelength_nm,
        points=[(0.0, y - mean) for y in ys],
        rms_mm=rms, geometric_blur_mm=blur, airy_diameter_mm=airy,
        ratio_to_airy=ratio, verdict=verdict,
    )


def _spot_verdict(ratio: float) -> str:
    if not math.isfinite(ratio):
        return "unusable"
    if ratio <= 1.0:
        return "diffraction-limited: the blur is inside the Airy disc, so a smaller aperture gains nothing"
    if ratio <= 2.0:
        return "near diffraction-limited: a good design at this f-number"
    if ratio <= 4.0:
        return "aberration-dominated: stopping down will sharpen it"
    if ratio <= 10.0:
        return "soft: visibly blurry at full aperture; this is a singlet-class design"
    return "unusable without stopping down hard"


def tolerance(
    surfaces: Sequence[Surface],
    *,
    wavelength_nm: float = LINES["d"],
    decentre_mm: float = 0.05,
    tilt_deg: float = 0.05,
    spacer_mm: float = 0.05,
) -> dict[str, Any]:
    """How much focus shift a plausible mount error causes.

    A real lens is held in a cell: the element can be decentred, tilted, or sit
    a fraction of a millimetre too far from its neighbour. Each of those moves
    the focus, and the useful question is whether the shift is smaller than the
    depth of focus, which is ±2·lambda·(f/#)² per the Rayleigh criterion.
    """
    base = paraxial(surfaces, wavelength_nm)
    fnum = base["f_number"]
    depth = 2.0 * (wavelength_nm * 1e-6) * fnum * fnum  # mm, one-sided

    # spacer error: move every internal thickness by the same amount
    moved = [Surface(s.radius, s.thickness + (spacer_mm if i < len(surfaces) - 1 else 0.0),
                     s.glass_after, s.semi_aperture) for i, s in enumerate(surfaces)]
    spacer_shift = abs(paraxial(moved, wavelength_nm)["bfd"] - base["bfd"])

    # decentre: shift the aperture by decentre_mm and refind the focus
    shifted = [Surface(s.radius, s.thickness, s.glass_after, s.semi_aperture + 0.0) for s in surfaces]
    # A decentred aperture samples the lens off-axis: the two marginal rays at
    # +/- semi now enter at heights (semi+d) and (semi-d), so their crossing
    # points differ. The difference is the coma-like blur a decentre introduces.
    semi = max(s.semi_aperture for s in shifted)
    crossings = []
    for h in (semi + decentre_mm, semi - decentre_mm, -semi + decentre_mm, -semi - decentre_mm):
        ray = trace_ray(h, 0.0, shifted, wavelength_nm)
        if ray and ray["slope_out"]:
            crossings.append(-ray["height_out"] / ray["slope_out"])
    coma_like = (max(crossings) - min(crossings)) if len(crossings) >= 2 else 0.0

    tilt_shift = abs(depth * math.tan(math.radians(tilt_deg)) / max(fnum, 1e-9))

    worst = max(spacer_shift, coma_like, tilt_shift)
    return {
        "focus_depth_mm": round(depth, 6),
        "spacer_error_mm": round(spacer_shift, 6),
        "decentre_blur_mm": round(coma_like, 6),
        "tilt_shift_mm": round(tilt_shift, 6),
        "worst_case_mm": round(worst, 6),
        "verdict": (
            "mountable on a hobby lathe: every error is a fraction of the depth of focus"
            if worst <= depth
            else "needs a machined cell: the worst error exceeds the depth of focus"
        ),
        "inputs": {"decentre_mm": decentre_mm, "tilt_deg": tilt_deg, "spacer_mm": spacer_mm},
    }


def system_report(
    surfaces: Sequence[Surface],
    *,
    wavelength_nm: float = LINES["d"],
    field_deg: float = 0.0,
) -> dict[str, Any]:
    """One call: paraxial, real rays, spot, tolerance, and the honest verdict."""
    trace = design_report(surfaces, wavelength_nm=wavelength_nm)
    spot = spot_diagram(surfaces, field_deg=field_deg, wavelength_nm=wavelength_nm)
    tol = tolerance(surfaces, wavelength_nm=wavelength_nm)
    return {
        "trace": trace,
        "spot": spot.as_dict(),
        "tolerance": tol,
        "summary": {
            "efl_mm": round(trace["paraxial"]["efl"], 3),
            "f_number": round(trace["paraxial"]["f_number"], 2),
            "spherical_aberration_mm": trace["spherical_aberration_mm"],
            "blur_diameter_mm": trace["blur_diameter_mm"],
            "spot_rms_mm": round(spot.rms_mm, 5),
            "airy_diameter_mm": round(spot.airy_diameter_mm, 5),
            "verdict": spot.verdict,
        },
    }
