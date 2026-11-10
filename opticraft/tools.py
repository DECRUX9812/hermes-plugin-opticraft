"""Agent tools for Opticraft: design, trace, tolerance, and the honest verdict.

Every number comes from ``opticraft.trace`` / ``.achromat`` / ``.spot``, which are
deterministic physics over a bundled glass catalogue. Nothing here calls a model,
and nothing here asserts a result it did not compute.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .achromat import DoubletSolution, colour_focus_shift, design_achromat, singlet_for_comparison
from .glass import GLASSES, LINES, catalogue, glass as get_glass
from .spot import spot_diagram, system_report, tolerance
from .trace import Surface, design_report, paraxial, trace_ray

TOOLSET = "opticraft"


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _wavelength(value: Any) -> float:
    """Accept a Fraunhofer label, a number, or nothing."""
    if value is None or value == "":
        return LINES["d"]
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in LINES:
        return LINES[text]
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"wavelength {value!r} is neither a Fraunhofer line ({', '.join(LINES)}) nor a number in nm")


def _surfaces_from_spec(spec: list[dict[str, Any]]) -> list[Surface]:
    """Build a surface list from a plain description (what the model passes)."""
    if not spec:
        raise ValueError("surface_spec is empty")
    out: list[Surface] = []
    for i, item in enumerate(spec):
        radius = float(item.get("radius_mm", item.get("radius", 0.0)) or 0.0)
        thickness = float(item.get("thickness_mm", item.get("thickness", 0.0)) or 0.0)
        glass_after = str(item.get("glass", item.get("glass_after", "")) or "").strip()
        if glass_after:
            get_glass(glass_after)  # reject an unknown glass here, not mid-trace
        semi = float(item.get("semi_aperture_mm", item.get("semi_aperture", 0.0)) or 0.0)
        out.append(Surface(radius=radius, thickness=thickness, glass_after=glass_after, semi_aperture=semi))
    # a last surface with no thickness is normal; anything else is user error
    for j, s in enumerate(out):
        if s.semi_aperture <= 0:
            raise ValueError(f"surface {j + 1} needs a positive semi_aperture_mm")
    return out


# --- schemas --------------------------------------------------------------

DESIGN_SCHEMA = {
    "name": "opticraft_design",
    "description": (
        "Design a cemented achromatic doublet for a target focal length and aperture, and return the "
        "three radii, the two element powers and focal lengths, the computed RMS spot, and the colour "
        "error. Use this when the user asks for a lens, an objective, an eyepiece, a telescope or a "
        "collimator design. It solves the achromatic condition from the Sellmeier data of the two "
        "glasses, then optimizes the single free bend (the internal radius) against the computed RMS "
        "spot, so the radii are derived, not copied from a catalog. It also reports the same focal "
        "length as a single element for comparison, which is how it shows what the second element buys."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "efl_mm": {"type": "number", "description": "Target effective focal length in mm"},
            "aperture_mm": {"type": "number", "description": "Clear aperture (lens diameter) in mm"},
            "crown": {"type": "string", "description": "Crown glass, e.g. N-BK7 (default N-BK7)"},
            "flint": {"type": "string", "description": "Flint glass, e.g. N-SF5 (default N-SF5)"},
            "wavelength": {"type": "string", "description": "Design wavelength: d, F, C, or a number in nm (default d = 587.6 nm)"},
        },
        "required": ["efl_mm", "aperture_mm"],
    },
}

TRACE_SCHEMA = {
    "name": "opticraft_trace",
    "description": (
        "Trace a lens system you describe: paraxial EFL/BFD/F-number, the exact meridional ray path, "
        "the spherical aberration, the blur at focus, and a spot diagram against the Airy disc. Use "
        "this to check a prescription the user already has (from a datasheet, a Zemax file description "
        "or their own numbers) before building it. Surfaces are listed in order of light travel; the "
        "last surface's thickness is the distance to the image plane."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "surface_spec": {
                "type": "array",
                "description": "Ordered surfaces. Each: {radius_mm, thickness_mm, glass, semi_aperture_mm}. Positive radius = centre of curvature on the image side.",
                "items": {
                    "type": "object",
                    "properties": {
                        "radius_mm": {"type": "number"},
                        "thickness_mm": {"type": "number"},
                        "glass": {"type": "string", "description": "Glass after this surface; empty for air"},
                        "semi_aperture_mm": {"type": "number"},
                    },
                },
            },
            "wavelength": {"type": "string", "description": "d, F, C, or nm (default d)"},
            "field_deg": {"type": "number", "description": "Field angle in degrees for the spot diagram (default 0, on axis)"},
        },
        "required": ["surface_spec"],
    },
}

SPOT_SCHEMA = {
    "name": "opticraft_spot",
    "description": (
        "Compute a spot diagram for a described system: the ray fan over the aperture, the RMS spot, "
        "the Airy disc at its f-number, and the ratio between them. The ratio is the answer to 'is "
        "this lens good?': at or below 1.0 the design is diffraction-limited and stopping down cannot "
        "improve it. Use this after opticraft_design or opticraft_trace when the user asks how sharp "
        "it will be."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "surface_spec": {"type": "array", "items": {"type": "object"}, "description": "As in opticraft_trace"},
            "wavelength": {"type": "string"},
            "field_deg": {"type": "number", "description": "Field angle in degrees (default 0)"},
        },
        "required": ["surface_spec"],
    },
}

COLOUR_SCHEMA = {
    "name": "opticraft_colour",
    "description": (
        "Measure the chromatic error of a described system: the axial focus shift between the C (656 nm) "
        "and F (486 nm) lines, with a verdict. Use this when the user asks about colour fringing or "
        "whether an achromat is actually achromatic."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "surface_spec": {"type": "array", "items": {"type": "object"}, "description": "As in opticraft_trace"},
            "line_a": {"type": "string", "description": "First line label (default C)"},
            "line_b": {"type": "string", "description": "Second line label (default F)"},
        },
        "required": ["surface_spec"],
    },
}

TOLERANCE_SCHEMA = {
    "name": "opticraft_tolerance",
    "description": (
        "Ask whether a design can actually be built: how far the focus moves when the elements are "
        "spaced a fraction of a millimetre wrong, decentred or tilted, measured against the Rayleigh "
        "depth of focus. Use this before telling someone to order glass or machine a cell."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "surface_spec": {"type": "array", "items": {"type": "object"}, "description": "As in opticraft_trace"},
            "decentre_mm": {"type": "number", "description": "Assumed decentre (default 0.05)"},
            "tilt_deg": {"type": "number", "description": "Assumed tilt (default 0.05)"},
            "spacer_mm": {"type": "number", "description": "Assumed spacer error (default 0.05)"},
        },
        "required": ["surface_spec"],
    },
}

GLASS_SCHEMA = {
    "name": "opticraft_glass",
    "description": (
        "Look up the optical glasses the engine can design with, with their index at the d line and "
        "their Abbe number, both evaluated from the Sellmeier terms. Use this to pick a crown/flint "
        "pair. Also returns the index at any wavelength you ask for."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A specific glass (e.g. N-SF5). Omit to list the whole catalogue."},
            "wavelength": {"type": "string", "description": "Optional: index at this wavelength (d, F, C, or nm)"},
        },
        "required": [],
    },
}


# --- handlers -------------------------------------------------------------

def make_handlers() -> dict[str, Callable[..., Any]]:
    def design_handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            efl = float(args.get("efl_mm") or 0)
            ap = float(args.get("aperture_mm") or 0)
            d: DoubletSolution = design_achromat(
                efl, ap,
                crown=str(args.get("crown") or "N-BK7"),
                flint=str(args.get("flint") or "N-SF5"),
                wavelengths=(_wavelength(args.get("wavelength")),),
            )
            report = system_report(d.surfaces, wavelength_nm=_wavelength(args.get("wavelength")))
            colour = colour_focus_shift(d.surfaces)
            single = singlet_for_comparison(efl, ap, glass_name=d.crown)
            single_report = system_report(single)
            single_colour = colour_focus_shift(single)
        except Exception as exc:  # noqa: BLE001 — tool handlers must not raise
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        return _json({
            "ok": True,
            "design": d.as_dict(),
            "report": report,
            "colour": colour,
            "comparison": {
                "what": "the same focal length in a single element",
                "singlet": {
                    "radii_mm": [round(s.radius, 3) for s in single],
                    "summary": single_report["summary"],
                    "colour": single_colour,
                },
                "improvement": {
                    "colour_factor": round(single_colour["axial_shift_mm"] / colour["axial_shift_mm"], 1)
                    if colour["axial_shift_mm"] else None,
                    "spot_factor": round(
                        single_report["summary"]["spot_rms_mm"] / report["summary"]["spot_rms_mm"], 1
                    ) if report["summary"]["spot_rms_mm"] else None,
                },
            },
        })

    def trace_handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            surfaces = _surfaces_from_spec(args.get("surface_spec") or [])
            w = _wavelength(args.get("wavelength"))
            field = float(args.get("field_deg") or 0.0)
            report = design_report(surfaces, wavelength_nm=w)
            spot = spot_diagram(surfaces, field_deg=field, wavelength_nm=w)
            px = paraxial(surfaces, w)
        except Exception as exc:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return _json({
            "ok": True,
            "paraxial": {k: (round(v, 5) if isinstance(v, (int, float)) else v) for k, v in px.items()},
            "report": report,
            "spot": spot.as_dict(),
            "verdict": spot.verdict,
        })

    def spot_handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            surfaces = _surfaces_from_spec(args.get("surface_spec") or [])
            spot = spot_diagram(
                surfaces,
                field_deg=float(args.get("field_deg") or 0.0),
                wavelength_nm=_wavelength(args.get("wavelength")),
            )
        except Exception as exc:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return _json({"ok": True, "spot": spot.as_dict(), "verdict": spot.verdict})

    def colour_handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            surfaces = _surfaces_from_spec(args.get("surface_spec") or [])
            out = colour_focus_shift(
                surfaces,
                line_a=str(args.get("line_a") or "C"),
                line_b=str(args.get("line_b") or "F"),
            )
        except Exception as exc:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return _json({"ok": True, **out})

    def tolerance_handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            surfaces = _surfaces_from_spec(args.get("surface_spec") or [])
            out = tolerance(
                surfaces,
                decentre_mm=float(args.get("decentre_mm") or 0.05),
                tilt_deg=float(args.get("tilt_deg") or 0.05),
                spacer_mm=float(args.get("spacer_mm") or 0.05),
            )
        except Exception as exc:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return _json({"ok": True, **out})

    def glass_handler(args: dict[str, Any], **kwargs: Any) -> str:
        try:
            name = str(args.get("name") or "").strip()
            if name:
                g = get_glass(name)
                payload: dict[str, Any] = {
                    "glass": g.name,
                    "nd": round(g.index(LINES["d"]), 5),
                    "vd": round(g.vd(), 2),
                    "nd_published": g.nd_published,
                    "vd_published": g.vd_published,
                }
                w = args.get("wavelength")
                if w not in (None, ""):
                    payload["index_at"] = {"wavelength_nm": _wavelength(w), "n": round(g.index(_wavelength(w)), 6)}
                return _json({"ok": True, "glass": payload})
            return _json({"ok": True, "glasses": catalogue(), "count": len(GLASSES)})
        except Exception as exc:  # noqa: BLE001
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "opticraft_design": design_handler,
        "opticraft_trace": trace_handler,
        "opticraft_spot": spot_handler,
        "opticraft_colour": colour_handler,
        "opticraft_tolerance": tolerance_handler,
        "opticraft_glass": glass_handler,
    }


SCHEMAS: dict[str, dict[str, Any]] = {
    "opticraft_design": DESIGN_SCHEMA,
    "opticraft_trace": TRACE_SCHEMA,
    "opticraft_spot": SPOT_SCHEMA,
    "opticraft_colour": COLOUR_SCHEMA,
    "opticraft_tolerance": TOLERANCE_SCHEMA,
    "opticraft_glass": GLASS_SCHEMA,
}
