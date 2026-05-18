"""
test_zero_phase_shift.py

Stronger test than test_phase_coherence.py: this one checks whether the
absolute phase of iq1's output matches the diff-tone phase in the raw
product bus, with NO offset.  Static offset = phase shift; zero offset
= no shift.

Logic:
    product line   = (1/2)cos(2pi f_d t + phi_d) + (1/2)cos(2pi f_s t + phi_s)
    iq1 output     = (1/2)|H(df)| cos(2pi f_d t + phi_d + arg H(df))

At the f_d FFT bin, phase(iq1) - phase(product) = arg H(df), the LPF's
static phase shift.  After auto-calibrating iq1 to the measured actual
f_d, Δf -> 0, and arg H(0) = 0, so the phase difference should be ~0.

Hardware setup:
    generator ---- ADC1
    lock-in   ---- ADC2

Does NOT modify signal_multiplier.py.
"""
import numpy as np
from pyrpl import Pyrpl

HOSTNAME = "rp-f0eb1d.local"
F1_NOMINAL = 1569
F2_NOMINAL = 2000
UNCERTAINTY = 0.05
CAPTURE_S = 1.0            # longer = finer FFT bin = tighter phase accuracy
TOL_DEG = 2.0              # tolerance for "zero" phase shift
AUTO_CALIBRATE = False      # True: retune iq1 to measured actual f_d (Δf -> 0)
                           # False: leave iq1 at nominal f_d -> shows predicted shift


def snap_down_bandwidth(iq, target):
    valid = np.array(iq.bandwidths)
    candidates = valid[(valid > 0) & (valid <= target)]
    if candidates.size == 0:
        return 1.1857967662444893
    return float(candidates.max())


def configure_extractor(r, f1, f2, uncertainty):
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


def capture(r, sig_a, sig_b, duration):
    r.scope.duration = duration
    r.scope.input1 = sig_a
    r.scope.input2 = sig_b
    r.scope.trigger_source = 'immediately'
    ch1, ch2 = r.scope.single(timeout=duration * 2 + 2)
    return np.asarray(ch1), np.asarray(ch2)


def windowed_fft(trace):
    """Hann-windowed FFT. Reduces spectral leakage between f_d and f_s peaks."""
    x = trace - np.mean(trace)
    w = np.hanning(len(x))
    return np.fft.rfft(x * w)


def peak_freq(spectrum, sampling_time, n):
    freqs = np.fft.rfftfreq(n, sampling_time)
    magn = np.abs(spectrum.copy())
    magn[0] = 0
    return float(freqs[np.argmax(magn)]), int(np.argmax(magn))


# -------- run ---------------------------------------------------------
p = Pyrpl("signal_extractor", hostname=HOSTNAME, gui=False)
r = p.rp

# Step 1: capture inputs at nominal IQ setup, measure actual frequencies
print("Step 1: measuring actual input frequencies")
configure_extractor(r, F1_NOMINAL, F2_NOMINAL, UNCERTAINTY)
in1, in2 = capture(r, 'in1', 'in2', CAPTURE_S)
dt = r.scope.sampling_time
n = len(in1)

f1_actual, _ = peak_freq(windowed_fft(in1), dt, n)
f2_actual, _ = peak_freq(windowed_fft(in2), dt, n)
print(f"  f1_actual = {f1_actual:.4f} Hz")
print(f"  f2_actual = {f2_actual:.4f} Hz")

# Step 2: either retune to actual (calibration) or leave at nominal (demonstration)
if AUTO_CALIBRATE:
    print("\nStep 2: retuning iq NCOs to actual frequencies (Δf -> 0)")
    configure_extractor(r, f1_actual, f2_actual, UNCERTAINTY)
else:
    print("\nStep 2: keeping iq NCOs at nominal (Δf is whatever detuning gives)")
    # already configured at nominal in Step 1, just print
print(f"  iq0.frequency = {r.iq0.frequency:.4f} Hz")
print(f"  iq1.frequency = {r.iq1.frequency:.4f} Hz")
print(f"  iq1.bandwidth = {r.iq1.bandwidth} Hz")

# Step 3: capture product + iq1, compare phase at the diff bin
print("\nStep 3: capturing product + iq1, comparing phases at f_d bin")
product, iq1 = capture(r, 'product', 'iq1', CAPTURE_S)
dt = r.scope.sampling_time
n = len(iq1)

spec_iq1 = windowed_fft(iq1)
spec_prd = windowed_fft(product)
f_d_obs, peak_idx = peak_freq(spec_iq1, dt, n)

phi_iq1 = np.angle(spec_iq1[peak_idx])
phi_prd = np.angle(spec_prd[peak_idx])
delta_phi = phi_iq1 - phi_prd
delta_phi = ((delta_phi + np.pi) % (2 * np.pi)) - np.pi      # wrap to [-pi, pi]
delta_phi_deg = np.degrees(delta_phi)

amp_ratio = np.abs(spec_iq1[peak_idx]) / np.abs(spec_prd[peak_idx])

print(f"  observed f_d = {f_d_obs:.4f} Hz (FFT bin = {1/CAPTURE_S:.4f} Hz)")
print(f"  phase(iq1)     = {np.degrees(phi_iq1):+.3f} deg")
print(f"  phase(product) = {np.degrees(phi_prd):+.3f} deg")
print(f"  delta phase    = {delta_phi_deg:+.3f} deg")
print(f"  amp ratio      = {amp_ratio:.4f}")

# Predict LPF phase shift from filter model.  Δf must be SIGNED: the sign
# tells the LPF which side of the carrier the signal sits, and arctan is odd.
fc = r.iq1.bandwidth[0] if hasattr(r.iq1.bandwidth, '__getitem__') else r.iq1.bandwidth
delta_f = f_d_obs - r.iq1.frequency      # signed: + if actual above NCO, - if below
predicted_deg = -2 * np.degrees(np.arctan(delta_f / fc))
print(f"\n  Δf (signed) = f_d_obs - iq1_freq = {delta_f:+.4f} Hz")
print(f"  predicted LPF phase = {predicted_deg:+.3f} deg")

print()
residual = delta_phi_deg - predicted_deg    # how far measured is from LPF model
if abs(delta_phi_deg) < TOL_DEG:
    print(f"  PASS: phase shift within +/- {TOL_DEG} deg (effectively zero)")
elif abs(residual) < TOL_DEG:
    print(f"  Phase shift {delta_phi_deg:+.3f} deg is non-zero but matches the LPF")
    print(f"  prediction ({predicted_deg:+.3f} deg, residual {residual:+.3f} deg).")
    print(f"  System is well-modeled; calibration would drive this to zero.")
else:
    print(f"  FAIL: measured {delta_phi_deg:+.3f} deg vs predicted {predicted_deg:+.3f} deg")
    print(f"        residual {residual:+.3f} deg - does not match LPF model")
