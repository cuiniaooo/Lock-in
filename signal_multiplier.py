from pyrpl import Pyrpl
import numpy as np

# ============ configuration ============
AUTO_TUNE = True          # True: measure actual f1, f2 and derive uncertainty
                          # False: use manual values below
CAPTURE_S = 1.0           # measurement window in seconds (only used when AUTO_TUNE=True)

# Manual settings (only used when AUTO_TUNE=False)
F1_MANUAL = 246e3          # frequency on ADC1
F2_MANUAL = 500e3          # frequency on ADC2
UNCERTAINTY_MANUAL = 0.05
# =======================================


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


def measure_input_frequencies(r, capture_s, f_max_hint):
    """Capture ADC1 and ADC2 simultaneously and return (f1, f2, actual_duration).

    Picks a scope sampling rate that satisfies Nyquist for f_max_hint
    (>= 3x margin), then uses the longest window that fits, capped at
    capture_s.  The actual duration may be shorter than capture_s when
    Nyquist requires a higher sample rate.
    """
    data_length = 16384
    nyquist_safe_st = 1.0 / (3 * f_max_hint)    # sampling_time required for Nyquist
    user_target_st = capture_s / data_length
    chosen_st = min(nyquist_safe_st, user_target_st)
    r.scope.sampling_time = chosen_st            # PyRPL snaps to nearest valid

    r.scope.input1 = 'in1'
    r.scope.input2 = 'in2'
    r.scope.trigger_source = 'immediately'
    actual_dur = r.scope.duration
    ch1, ch2 = r.scope.single(timeout=actual_dur * 2 + 2)
    dt = r.scope.sampling_time
    n = len(ch1)
    freqs = np.fft.rfftfreq(n, dt)
    w = np.hanning(n)

    def fft_peak(trace):
        x = np.asarray(trace) - np.mean(trace)
        spec = np.fft.rfft(x * w)
        spec[0] = 0
        return float(freqs[np.argmax(np.abs(spec))])

    return fft_peak(ch1), fft_peak(ch2), actual_dur


p = Pyrpl("signal_extractor", hostname="rp-f0eb1d.local", gui=False)
r = p.rp

for m in [r.pid0, r.pid1, r.pid2, r.iq0, r.iq1, r.iq2, r.asg0, r.asg1]:
    m.output_direct = 'off'

# === Pick operating frequencies and uncertainty ===
if AUTO_TUNE:
    # Use the manual values as a rough hint for the expected frequency range.
    # The scope's sampling rate needs to satisfy Nyquist for the highest signal
    # frequency; otherwise the FFT sees an aliased peak and tunes to garbage.
    f_max_hint = max(F1_MANUAL, F2_MANUAL) * 1.2     # 20% safety margin
    print(f"Auto-tune: measuring input frequencies "
          f"(Nyquist-safe up to {f_max_hint:.0f} Hz, max window {CAPTURE_S} s)...")
    f1, f2, actual_dur = measure_input_frequencies(r, CAPTURE_S, f_max_hint)
    f_sum_est = f1 + f2
    bin_width = 1.0 / actual_dur
    # delta = uncertainty * f_sum = bin_width (worst-case shift on sum or diff)
    uncertainty = bin_width / f_sum_est
    print(f"  actual capture duration = {actual_dur*1e3:.4f} ms")
    print(f"  FFT bin width = {bin_width:.4f} Hz")
    print(f"  f1 = {f1:.4f} Hz")
    print(f"  f2 = {f2:.4f} Hz")
    print(f"  derived uncertainty = {uncertainty:.6e}  (= bin_width / f_sum)")
else:
    f1 = F1_MANUAL
    f2 = F2_MANUAL
    uncertainty = UNCERTAINTY_MANUAL
    print(f"Manual: f1 = {f1} Hz, f2 = {f2} Hz, uncertainty = {uncertainty}")

f_sum = f1 + f2
f_diff = abs(f1 - f2)


# === Calculate the filter--we first calculate the closest frequency and then the two stage filter to supress it by 100x===
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

print(f"\nFinal setup:")
print(f"  iq0 (sum):  freq = {f_sum:.4f} Hz, bandwidth = [{sum_filter}, {sum_filter}] Hz")
print(f"  iq1 (diff): freq = {f_diff:.4f} Hz, bandwidth = [{diff_filter}, {diff_filter}] Hz")
