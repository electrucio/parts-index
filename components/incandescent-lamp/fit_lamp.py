#!/usr/bin/env python3
"""Offline companion of lamp.sub: the same equations in Python, used to

1. fit the one free parameter `fc` (fraction of the rated power lost by conduction
   at the rated point) to S. Holmes' measurement on a #327-type lamp: 0.5 V RMS
   at 4.5 mA (sound-au.com/articles/sinewave.htm, section 4.2);
2. derive the cold resistance of the lamps with no published cold value: same
   filament temperature at rating as the #327 (README "Provenance");
3. print what the bench then checks independently: R at 7.4 mA, the filament
   temperature at 10 and 13 mA against the Draper point, the current exponent,
   the thermal time constant.

No LTspice needed: python3 fit_lamp.py
"""
from __future__ import annotations

import math

SIGMA = 5.670374419e-8          # W m^-2 K^-4 (CODATA)
M_W, RHO_M = 0.18384, 19250.0   # kg/mol, kg/m^3 (Tolias 2017, eq. for rho_m at T0)


def rho(T):
    """Tungsten resistivity, micro-ohm cm: White & Minges 1997 fit, 100-3600 K,
    as quoted by Tolias, arXiv:1703.06302 (Nucl. Mater. Energy 13, 2017), p.4."""
    return -0.9680 + 1.9274e-2 * T + 7.8260e-6 * T**2 - 1.8517e-9 * T**3 + 2.0790e-13 * T**4


def cp(T):
    """Tungsten isobaric heat capacity, J/(mol K): White & Minges fit, 300-3400 K
    (Tolias 2017 p.5, misprints corrected there)."""
    return 21.868372 + 8.068661e-3 * T - 3.756196e-6 * T**2 + 1.075862e-9 * T**3 + 1.406637e4 / T**2


def eps(T):
    """Total hemispherical emissivity: 0.0992 at 1000 K (Verret & Ramanathan, JOSA 68,
    1167 (1978), abstract), taken proportional to T (free-electron trend for rho ~ T):
    a stated assumption, see README."""
    return 0.0992 * T / 1000.0


class Lamp:
    def __init__(self, Vr, Ir, Rc, fc, TaC=25.0):
        self.Vr, self.Ir, self.Rc, self.fc = Vr, Ir, Rc, fc
        self.Ta = TaC + 273.15
        self.Rh = Vr / Ir
        k = self.Rh / Rc
        # filament temperature at rating: rho(Th)/rho(Ta) = Rh/Rc (Newton)
        T = self.Ta * k ** (1 / 1.2)
        for _ in range(30):
            f = rho(T) / rho(self.Ta) - k
            df = (rho(T + 0.5) - rho(T - 0.5)) / rho(self.Ta)
            T -= f / df
        self.Th = T
        P = Vr * Ir
        self.Gc = fc * P / (T - self.Ta)
        self.A = (1 - fc) * P / (SIGMA * (eps(T) * T**4 - eps(self.Ta) * self.Ta**4))
        # straight round wire of diameter d: R = 4 rho L/(pi d^2), A = pi d L
        d3 = 4 * rho(T) * 1e-8 * self.A / (math.pi**2 * self.Rh)
        self.d = d3 ** (1 / 3)
        self.L = self.A / (math.pi * self.d)
        self.vol = self.A * self.d / 4

    def R(self, T):
        return self.Rc * rho(T) / rho(self.Ta)

    def loss(self, T):
        return self.Gc * (T - self.Ta) + self.A * SIGMA * (eps(T) * T**4 - eps(self.Ta) * self.Ta**4)

    def Cth(self, T):
        return self.vol * RHO_M * cp(T) / M_W

    def T_at_I(self, I):
        lo, hi = self.Ta, 3600.0
        for _ in range(100):
            m = 0.5 * (lo + hi)
            if I * I * self.R(m) > self.loss(m):
                lo = m
            else:
                hi = m
        return 0.5 * (lo + hi)

    def T_at_V(self, V):
        lo, hi = self.Ta, 3600.0
        for _ in range(100):
            m = 0.5 * (lo + hi)
            if V * V / self.R(m) > self.loss(m):
                lo = m
            else:
                hi = m
        return 0.5 * (lo + hi)

    def tau(self, T):
        """small-signal electro-thermal time constant at constant current is
        Cth / (dLoss/dT - I^2 dR/dT); at constant voltage Cth / (dLoss/dT + V^2/R^2 dR/dT).
        Reported: the plain thermal one, Cth / dLoss/dT."""
        dl = (self.loss(T + 0.5) - self.loss(T - 0.5))
        return self.Cth(T) / dl


def fit_fc(Vr, Ir, Rc, I0, R0):
    lo, hi = 0.0, 0.5
    for _ in range(80):
        m = 0.5 * (lo + hi)
        L = Lamp(Vr, Ir, Rc, m)
        if L.R(L.T_at_I(I0)) > R0:     # too hot: more conduction needed
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


if __name__ == "__main__":
    fc = fit_fc(28, 0.040, 65.0, 4.5e-3, 0.5 / 4.5e-3)
    L = Lamp(28, 0.040, 65.0, fc)
    print(f"#327: fc = {fc:.4f}  Th = {L.Th:.1f} K  Gc = {L.Gc*1e6:.2f} uW/K  A = {L.A*1e6:.4f} mm2"
          f"  d = {L.d*1e6:.2f} um  L = {L.L*1e3:.1f} mm  Cth(Th) = {L.Cth(L.Th)*1e6:.2f} uJ/K")
    for I in (4.5e-3, 7.4e-3, 10e-3, 13e-3, 40e-3):
        T = L.T_at_I(I)
        print(f"   I = {I*1e3:5.1f} mA: T = {T:7.1f} K  R = {L.R(T):7.2f} ohm  V = {I*L.R(T):6.3f} V"
              f"  tau = {L.tau(T)*1e3:7.2f} ms")
    I14 = 14 / L.R(L.T_at_V(14))
    print(f"   I at 14 V = {I14*1e3:.2f} mA; exponent ln(I/Ir)/ln(0.5) = {math.log(I14/0.04)/math.log(0.5):.3f}")
    ratio = rho(L.Ta) / rho(L.Th)
    for name, V, I in (("#47", 6.3, 0.150), ("GOW12", 12.0, 0.040), ("6V60", 6.0, 0.060)):
        Rc = V / I * ratio
        print(f"{name}: Rc (same Th as #327) = {Rc:.4g} ohm")
    # the 6 V / 60 mA lamp of sound-au project 179 has its own cold value (10 ohm)
    L6 = Lamp(6.0, 0.060, 10.0, fc)
    T = L6.T_at_V(0.5)
    print(f"6V60 (Rc = 10, fc as #327): Th = {L6.Th:.0f} K; at 0.5 V: R = {L6.R(T):.2f} ohm,"
          f" I = {0.5/L6.R(T)*1e3:.2f} mA (published: 30 ohm, 17 mA)")
