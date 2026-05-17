from pyrpl import Pyrpl
import numpy as np

def snap_down_bandwidth(iq, target):
    """Return the largest valid filter bandwidth <= target (Hz).

    PyRPL's setter snaps to the *nearest* valid frequency, which can silently
    widen the filter. This forces a snap-down so the actual cutoff is never
    above what you asked for.
    """
    valid = np.array(iq.bandwidths)
    candidates = valid[(valid > 0) & (valid <= target)]
    if candidates.size == 0:
        return 1.1857967662444893
    return float(candidates.max())

p = Pyrpl("signal_extractor", hostname="rp-f0eb1d.local", gui=False)
r = p.rp

for m in [r.pid0, r.pid1, r.pid2, r.iq0, r.iq1, r.iq2, r.asg0, r.asg1]:
    m.output_direct = 'off'

# === You must know these (approximately) ===
f1 = 3000  # frequency on ADC1 (Hz, ±1% uncertainty)
f2 = 3000  # frequency on ADC2
f_sum = f1 + f2  # 13 MHz — what the multiplier produces
f_diff = abs(f1 - f2)  # 3 MHz — what the multiplier produces
uncertainty = 0.05


# === Calculate the filter--we are first calculated the closest frequency and then the two stage filter to supress it by 100x===
sum_filter = min(2*f1, 2*f2)
diff_filter = min(2*f1, 2*f2, max(f_diff, 2*f_diff - uncertainty * f_sum)) # account for case where f_diff is zero, then uncertinaty * f_sum is the total uncertainty on both the sum and the difference
sum_filter = sum_filter / 99**0.5
diff_filter = diff_filter / 99**0.5

# === Sum-band extractor → DAC OUT1 ===
iq_sum = r.iq0
# === Handles Snapping ===
sum_filter = snap_down_bandwidth(iq_sum, sum_filter)
iq_sum.setup(
    input='product',  # ← the new bus signal: ADC1 × ADC2
    frequency=f_sum,  # heterodyne against predicted f_sum
    bandwidth= [sum_filter, sum_filter],  # 2-stage 1-MHz LPF on baseband I/Q
    acbandwidth= 0,  # no input HPF (multiplier alread removed DC concerns)
    amplitude = 0,  # no LO out: both DACs needed for results
    gain = 1,  # no LO gain
    phase = 0,  # arbitrary; fine for amplitude detection
    quadrature_factor = 1,  # no extra digital gain on baseband
    output_signal = 'output_direct',  # ← key: the demod-LPF-RE-modulated path
    output_direct = 'out1',  # send to DAC OUT1
)

# === Difference-band extractor → DAC OUT2 ===
iq_diff = r.iq1
# === Handles Snapping ===
diff_filter = snap_down_bandwidth(iq_diff, diff_filter)
iq_diff.setup(
input = 'product',
frequency = f_diff,
bandwidth = [diff_filter, diff_filter],
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