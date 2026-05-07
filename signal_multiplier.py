from pyrpl import Pyrpl

p = Pyrpl("signal_extractor", hostname="rp-f0eb1d.local", gui=False)
r = p.rp

# === You must know these (approximately) ===
f1 = 5e6  # frequency on ADC1 (Hz, ±1% uncertainty)
f2 = 8e6  # frequency on ADC2
f_sum = f1 + f2  # 13 MHz — what the multiplier produces
f_diff = abs(f1 - f2)  # 3 MHz — what the multiplier produces

# === Sum-band extractor → DAC OUT1 ===
iq_sum = r.iq0
iq_sum.setup(
    input='product',  # ← the new bus signal: ADC1 × ADC2
    frequency=f_sum,  # heterodyne against predicted f_sum
    bandwidth=[1e6, 1e6],  # 2-stage 1-MHz LPF on baseband I/Q
    acbandwidth=0,  # no input HPF (multiplier alread removed DC concerns)
    amplitude = 0,  # no LO out: both DACs needed for results
    gain = 1,  # no LO gain
    phase = 0,  # arbitrary; fine for amplitude detection
    quadrature_factor = 1,  # no extra digital gain on baseband
    output_signal = 'output_direct',  # ← key: the demod-LPF-RE-modulated path
    output_direct = 'out1',  # send to DAC OUT1
)

# === Difference-band extractor → DAC OUT2 ===
iq_diff = r.iq1
iq_diff.setup(
input = 'product',
frequency = f_diff,
bandwidth = [1e6, 1e6],
acbandwidth = 0,
amplitude = 0,
gain = 1,
phase = 0,
quadrature_factor = 1,
output_signal = 'output_direct',
output_direct = 'out2',
)

# After this runs, hardware does:
#   ADC1 × ADC2 = ½cos((f1+f2)t) + ½cos((f1-f2)t)
#   iq0 picks out the f_sum component → OUT1
#   iq1 picks out the f_diff component → OUT2