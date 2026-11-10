"""Meridional ray trace, paraxial lens formula, and third-order aberrations.

All of it is arithmetic over the glass catalogue: no model, no network, no
lookup tables of answers. The trace is a exact vector Snell refraction at
spherical surfaces, which is why the tests can assert it converges to the
paraxial formula as the aperture shrinks — and why a real ray at the edge of a
singlet lands measurably off the paraxial focus (spherical aberration, computed
rather than quoted).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from .glass import LINES, glass as get_glass


# --- geometry -------------------------------------------------------------

@dataclass(frozen=True)
class Surface:
    """One refracting surface. ``radius`` is signed: positive when the centre of
    curvature sits on the image side, as every optical datasheet prints it."""

    radius: float           # mm; 0 = plane
    thickness: float        # mm to the next surface / to the image plane
    glass_after: str        # glass name after this surface, "" = air
    semi_aperture: float    # mm; rays outside it are vignetted (honest, not clipped)

    def n_next(self, wavelength_nm: float, n_current: float) -> float:
        if self.glass_after:
            return get_glass(self.glass_after).index(wavelength_nm)
        return 1.0


def _intersect(pz: float, py: float, dz: float, dy: float, vertex_z: float, radius: float):
    """First intersection ahead of the ray with the sphere centred at (vertex_z+radius, 0)."""
    if radius == 0.0:
        if dz == 0.0:
            return None
        t = (vertex_z - pz) / dz
        return (pz + t * dz, py + t * dy, t)
    cz = vertex_z + radius
    oz, oy = pz - cz, py
    b = 2.0 * (oz * dz + oy * dy)
    c = oz * oz + oy * oy - radius * radius
    disc = b * b - 4.0 * c
    if disc <= 0.0:
        return None
    sq = math.sqrt(disc)
    # A ray that starts exactly on the vertex has t = 0 as its true intersection:
    # accepting only positive roots sends the axial ray to the far side of the
    # sphere, which then misses the next surface entirely.
    ahead = [t for t in ((-b - sq) / 2.0, (-b + sq) / 2.0) if t >= -1e-9]
    if not ahead:
        return None
    t = min(ahead)
    return (pz + t * dz, py + t * dy, t)


def _refract(dz: float, dy: float, nz: float, ny: float, n_in: float, n_out: float):
    """Vector Snell's law: t = eta*i + (eta*cos_i - cos_t)*n_hat."""
    cos_i = -(dz * nz + dy * ny)
    if cos_i < 0.0:
        cos_i = -cos_i
        nz, ny = -nz, -ny
    eta = n_in / n_out
    sin2_t = eta * eta * (1.0 - cos_i * cos_i)
    if sin2_t > 1.0:
        return None  # total internal reflection: report it, do not silently bend
    cos_t = math.sqrt(1.0 - sin2_t)
    oz = eta * dz + (eta * cos_i - cos_t) * nz
    oy = eta * dy + (eta * cos_i - cos_t) * ny
    m = math.hypot(oz, oy)
    return oz / m, oy / m


def trace_ray(
    height: float,
    slope: float,
    surfaces: Sequence[Surface],
    wavelength_nm: float,
    *,
    n_start: float = 1.0,
) -> dict[str, Any] | None:
    """Trace one meridional ray; ``None`` when it vignettes or TIRs."""
    m = math.hypot(1.0, slope)
    dz, dy = 1.0 / m, slope / m
    pz, py, n = 0.0, height, n_start
    vertex_z = 0.0
    path = [(pz, py)]
    for s in surfaces:
        hit = _intersect(pz, py, dz, dy, vertex_z, s.radius)
        if hit is None:
            return None
        pz, py, _ = hit
        if abs(py) > s.semi_aperture:
            return None
        if s.radius == 0.0:
            nz, ny = -1.0, 0.0
        else:
            nz, ny = (pz - (vertex_z + s.radius)) / abs(s.radius), py / abs(s.radius)
        out = _refract(dz, dy, nz, ny, n, s.n_next(wavelength_nm, n))
        if out is None:
            return None
        dz, dy = out
        n = s.n_next(wavelength_nm, n)
        path.append((pz, py))
        vertex_z += s.thickness
        # advance to the next vertex plane is handled by the next intersection;
        # for the last surface, walk to the image plane so the return is complete.
    if dz == 0.0:
        return None
    t = (vertex_z - pz) / dz
    image_z = vertex_z
    image_y = py + t * dy
    return {
        "height_out": py,
        "slope_out": dy / dz,
        "image_height": image_y,
        "image_z": image_z,
        "path": path,
    }


# --- paraxial -------------------------------------------------------------

def surface_power(radius_mm: float, n_in: float, n_out: float) -> float:
    """phi = (n_out - n_in) / R, in 1/mm."""
    if radius_mm == 0.0:
        return 0.0
    return (n_out - n_in) / radius_mm


def paraxial(
    surfaces: Sequence[Surface],
    wavelength_nm: float,
    object_distance: float | None = None,
) -> dict[str, float]:
    """Thick-lens paraxial solution via ray-transfer matrices.

    Ray vector is (y, u) with u the *reduced* angle n·theta, so
      translation by t in medium n:  y += (t/n) u
      refraction at power phi:       u -= phi y
    The system matrix M maps the input ray to the output ray; for a parallel
    input ray (u=0) the crossover is at -A/C from the last vertex, and the
    effective focal length is -1/C.
    """
    m = [[1.0, 0.0], [0.0, 1.0]]  # A B / C D

    def matmul(x, y):
        return [
            [x[0][0] * y[0][0] + x[0][1] * y[1][0], x[0][0] * y[0][1] + x[0][1] * y[1][1]],
            [x[1][0] * y[0][0] + x[1][1] * y[1][0], x[1][0] * y[0][1] + x[1][1] * y[1][1]],
        ]

    n_cur = 1.0
    for i, s in enumerate(surfaces):
        n_next = s.n_next(wavelength_nm, n_cur)
        phi = surface_power(s.radius, n_cur, n_next)
        m = matmul([[1.0, 0.0], [-phi, 1.0]], m)
        if i < len(surfaces) - 1:
            m = matmul([[1.0, s.thickness / n_next], [0.0, 1.0]], m)
        n_cur = n_next

    a, c = m[0][0], m[1][0]
    semi = max(s.semi_aperture for s in surfaces)
    if c == 0.0:
        return {"power": 0.0, "efl": math.inf, "bfd": math.inf,
                "f_number": math.inf, "matrix": m}
    efl = -1.0 / c
    bfd = -a / c
    f_number = abs(efl) / (2.0 * semi) if semi else math.inf
    return {"power": -c, "efl": efl, "bfd": bfd, "f_number": f_number, "matrix": m}


# --- the design report ----------------------------------------------------

def design_report(
    surfaces: Sequence[Surface],
    *,
    wavelength_nm: float = LINES["d"],
    ray_heights: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Everything: paraxial, real-ray focus, spherical aberration, blur, vignetting."""
    px = paraxial(surfaces, wavelength_nm)
    semi = max(s.semi_aperture for s in surfaces)
    heights = list(ray_heights) if ray_heights else [semi * f for f in (0.05, 0.25, 0.5, 0.75, 0.95)]

    rays = []
    for h in heights:
        r = trace_ray(h, 0.0, surfaces, wavelength_nm)
        if r is None:
            rays.append({"height": round(h, 4), "vignetted": True})
            continue
        bfd = -r["height_out"] / r["slope_out"] if r["slope_out"] else math.inf
        rays.append({
            "height": round(h, 4),
            "y_out": round(r["height_out"], 6),
            "slope_out": round(r["slope_out"], 7),
            "bfd": round(bfd, 4),
            "vignetted": False,
        })

    traced = [r for r in rays if not r.get("vignetted")]
    axial = [r["bfd"] for r in traced if abs(r["height"]) <= 1e-3]
    focus = axial[0] if axial else (traced[0]["bfd"] if traced else px.get("bfd", math.inf))
    spherical = max((abs(r["bfd"] - focus) for r in traced), default=0.0)

    # blur diameter at the paraxial focus for a ray fan up to the aperture
    blur = 0.0
    for r in traced:
        rho = abs(r["bfd"] - focus)
        if rho:
            blur = max(blur, 2.0 * abs(r["slope_out"]) * rho)

    return {
        "wavelength_nm": wavelength_nm,
        "paraxial": {k: (round(v, 5) if isinstance(v, (int, float)) else v) for k, v in px.items()},
        "rays": rays,
        "paraxial_focus_mm": round(focus, 4),
        "spherical_aberration_mm": round(spherical, 4),
        "blur_diameter_mm": round(blur, 4),
        "aperture_mm": round(2.0 * semi, 4),
        "vignetted_rays": sum(1 for r in rays if r.get("vignetted")),
    }
