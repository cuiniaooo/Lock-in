"""
test_phase_coherence.py

Tests the signal extractor's phase coherence at f1 != f2 using sources
that don't need to be phase-locked.

Logic: the multiplier + IQ extractor are deterministic. If the extracted
f_diff matches |f1_actual - f2_actual| computed independently from the
ADC FFTs, the extractor is coherent.  Drift in the sources is fine -
they just drift together, and we measure both inputs and the output in
the same time window.

Hardware setup:
    generator ---- ADC1
    lock-in   ---- ADC2

Run signal_multiplier.py FIRST (or let this script reconfigure the IQ
blocks - it does an idempotent setup that mirrors signal_multiplier.py).

Does NOT modify signal_multiplier.py or any other existing script.
"""
import numpy as np
from pyrpl import Pyrpl

# -------- configuration ------------------------------------------------
HOSTNAME = "rp-f0eb1d.local"
F1_NOMINAL = 1542        # Hz - your generator setting
F2_NOMINAL = 2000        # Hz - your lock-in setting (free-running)
UNCERTAINTY = 0.05
CAPTURE_S = 1          # capture window length
# -----------------------------------------------------------------------


def snap_down_bandwidth(iq, target):
    valid = np.array(iq.bandwidths)
    candidates = valid[(valid > 0) & (valid <= target)]
    if candidates.size == 0:
        return 1.1857967662444893
    return float(candidates.max())


def fft_peak(trace, sampling_time):
    """Frequency (Hz) of the largest spectral peak (excluding DC)."""
    n = len(trace)
    spectrum = np.abs(np.fft.rfft(trace - np.mean(trace)))
    freqs = np.fft.rfftfreq(n, sampling_time)
    spectrum[0] = 0  # ignore DC bin
    return float(freqs[np.argmax(spectrum)])


def configure_extractor(r, f1, f2, uncertainty):
    """Idempotent IQ setup that mirrors signal_multiplier.py."""
    f_sum = f1 + f2
    f_diff = abs(f1 - f2)

    sum_target = min(2 * f1, 2 * f2) / 99 ** 0.5
    diff_target = min(2 * f1, 2 * f2,
                      max(f_diff, 2 * f_diff - uncertainty * f_sum)) / 99 ** 0.5

    fc_sum = snap_down_bandwidth(r.iq0, sum_target)
    fc_diff = snap_down_bandwidth(r.iq1, diff_target)

    for m in [r.pid0, r.pid1, r.pid2, r.iq0, r.iq1, r.iq2, r.asg0, r.asg1]:
        m.output_direct = 'off'

    r.iq0.setup(
        input='product', frequency=f_sum,
        bandwidth=[fc_sum, fc_sum],
        acbandwidth=0, amplitude=0, gain=1, phase=0, quadrature_factor=1,
        output_signal='output_direct', output_direct='out1',
    )
    r.iq1.setup(
        input='product', frequency=f_diff,
        bandwidth=[fc_diff, fc_diff],
        acbandwidth=0, amplitude=0, gain=1, phase=0, quadrature_factor=1,
        output_signal='output_direct', output_direct='out2',
    )
    return fc_sum, fc_diff


def capture(r, signal_a, signal_b):
    """Capture two scope channels simultaneously. Returns (ch_a, ch_b)."""
    r.scope.input1 = signal_a
    r.scope.input2 = signal_b
    r.scope.trigger_source = 'immediately'
    ch1, ch2 = r.scope.single(timeout=5.0)
    return np.asarray(ch1), np.asarray(ch2)


# -------- run ---------------------------------------------------------
p = Pyrpl("signal_extractor", hostname=HOSTNAME, gui=False)
r = p.rp

fc_sum, fc_diff = configure_extractor(r, F1_NOMINAL, F2_NOMINAL, UNCERTAINTY)
print(f"Configured: fc_sum = {r.iq0.bandwidth} Hz, fc_diff = {r.iq1.bandwidth} Hz")

r.scope.duration = CAPTURE_S
dt = r.scope.sampling_time
fft_bin = 1.0 / r.scope.duration
print(f"Capture duration: {r.scope.duration:.3f} s, "
      f"sampling time: {dt*1e6:.2f} us, FFT bin: {fft_bin:.3f} Hz\n")

# Capture both inputs in one shot
in1_trace, in2_trace = capture(r, 'in1', 'in2')
# Then the IQ outputs
iq0_trace, iq1_trace = capture(r, 'iq0', 'iq1')

f1_actual = fft_peak(in1_trace, dt)
f2_actual = fft_peak(in2_trace, dt)
f_sum_actual = fft_peak(iq0_trace, dt)
f_diff_actual = fft_peak(iq1_trace, dt)

expected_sum = f1_actual + f2_actual
expected_diff = abs(f1_actual - f2_actual)

print(f"{'':24s}{'measured':>12s}  {'expected':>12s}  {'discrepancy':>12s}")
print(f"{'ADC1 (f1)':24s}{f1_actual:>12.3f}")
print(f"{'ADC2 (f2)':24s}{f2_actual:>12.3f}")
print(f"{'iq0 output (f_sum)':24s}{f_sum_actual:>12.3f}  "
      f"{expected_sum:>12.3f}  {abs(f_sum_actual-expected_sum):>12.3f}")
print(f"{'iq1 output (f_diff)':24s}{f_diff_actual:>12.3f}  "
      f"{expected_diff:>12.3f}  {abs(f_diff_actual-expected_diff):>12.3f}")
print()

tol = 2 * fft_bin
sum_ok = abs(f_sum_actual - expected_sum) < tol
diff_ok = abs(f_diff_actual - expected_diff) < tol

print(f"Tolerance: {tol:.3f} Hz (2 x FFT bin width)")
print(f"Sum arm:  {'PASS' if sum_ok else 'FAIL'}")
print(f"Diff arm: {'PASS' if diff_ok else 'FAIL'}")
