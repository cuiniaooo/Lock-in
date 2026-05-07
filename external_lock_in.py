from pyrpl import Pyrpl

p = Pyrpl("external_lockin", hostname="rp-f0eb1d.local", gui=False)
r = p.rp

# IQ used as a pure LPF (no demodulation — we already multiplied!)
iq = r.iq0
iq.setup(
    input='product',  # ← reads bus slot 14 = ADC1 × ADC2
    frequency=0,  # NCO at DC = mixer is a no-op (cos(0)=1)
    bandwidth=[1e3],  # lock-in time constant (1 kHz here)
    gain=0.0,
    phase=0,
    acbandwidth=0,  # no input HPF needed; the multiplication alreadyfrom DC
    amplitude=0,  # no LO output — both DACs free for results
    output_direct = 'out1',
    output_signal = 'quadrature',
    quadrature_factor = 1,
)