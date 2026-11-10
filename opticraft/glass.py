"""Optical glass catalogue and Sellmeier dispersion.

The index at any wavelength is evaluated from published Sellmeier coefficients,
never read from a pre-baked table. Every coefficient set below is checked against
the manufacturer's published nd and Vd in ``tests/test_glass.py``, so a typo in
a coefficient fails the build instead of silently mis-designing a lens.

Sources: Schott optical-glass data sheets (Sellmeier 1 form), cross-checked
against the coefficient table shipped in `ofiber` (MIT).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Fraunhofer lines every optical datasheet is quoted at.
LINES = {
    "C": 656.2725,   # red hydrogen,  nC
    "d": 587.5618,   # helium, the design wavelength, nd
    "F": 486.1327,   # blue hydrogen, nF
}


@dataclass(frozen=True)
class Glass:
    """One optical glass: Sellmeier 1 terms plus the published reference values."""

    name: str
    b1: float
    b2: float
    b3: float
    c1: float      # um^2
    c2: float      # um^2
    c3: float      # um^2
    nd_published: float = 0.0
    vd_published: float = 0.0

    def index(self, wavelength_nm: float) -> float:
        """Refractive index at a wavelength in nanometres (Sellmeier 1)."""
        if wavelength_nm <= 0:
            raise ValueError("wavelength must be positive")
        lam2 = (wavelength_nm / 1000.0) ** 2
        n2 = 1.0 + (
            self.b1 * lam2 / (lam2 - self.c1)
            + self.b2 * lam2 / (lam2 - self.c2)
            + self.b3 * lam2 / (lam2 - self.c3)
        )
        if n2 <= 0:
            raise ValueError(f"{self.name} is not transmissive at {wavelength_nm} nm")
        return math.sqrt(n2)

    def vd(self) -> float:
        """Abbe number from the model itself, so design and databook agree."""
        nd = self.index(LINES["d"])
        return (nd - 1.0) / (self.index(LINES["F"]) - self.index(LINES["C"]))


GLASSES: dict[str, Glass] = {
    g.name: g
    for g in (
        # crown glasses
        Glass("N-BK7", 1.03961212, 0.231792344, 1.01046945,
              6.00069867e-03, 2.00179144e-02, 103.560653, 1.51680, 64.17),
        Glass("N-K5", 1.08511833, 0.19956200, 0.93051166,
              6.61099503e-03, 2.41108660e-02, 111.982777, 1.52249, 59.48),
        Glass("N-SK16", 1.34317774, 0.24114440, 0.99431797,
              7.04687339e-03, 2.29005000e-02, 92.750853, 1.62041, 60.32),
        Glass("N-LAK9", 1.46231905, 0.34439959, 1.15508372,
              7.24270156e-03, 2.43353131e-02, 85.468687, 1.69100, 54.71),
        # flint glasses, the partner in an achromat
        Glass("N-F2", 1.39757037, 0.15920140, 1.26865430,
              9.95906143e-03, 5.46931752e-02, 119.248346, 1.62004, 36.43),
        Glass("N-SF2", 1.47343127, 0.16368185, 1.36920899,
              1.09019098e-02, 5.85683687e-02, 127.404933, 1.64769, 33.82),
        Glass("N-SF5", 1.52481889, 0.18708553, 1.42729015,
              1.12547560e-02, 5.88995392e-02, 129.141675, 1.67270, 32.25),
    )
}


def glass(name: str) -> Glass:
    key = (name or "").strip().upper().replace("_", "-")
    for candidate, entry in GLASSES.items():
        if candidate.upper() == key:
            return entry
    raise KeyError(f"unknown glass {name!r}; available: {', '.join(sorted(GLASSES))}")


def catalogue() -> list[dict[str, object]]:
    """Every glass with its model-evaluated nd and Vd, for a picker or a listing."""
    out = []
    for name, g in sorted(GLASSES.items()):
        out.append({
            "glass": name,
            "nd": round(g.index(LINES["d"]), 5),
            "vd": round(g.vd(), 2),
            "nd_published": g.nd_published,
            "vd_published": g.vd_published,
            "crown_or_flint": "crown" if g.vd() > 50 else "flint",
        })
    return out
