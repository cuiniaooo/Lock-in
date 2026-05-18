# Lock-in / Signal Extractor scripts

PyRPL configuration scripts for signal-recovery tasks on a Red Pitaya STEMlab 125-14, including a custom external-reference variant that the upstream PyRPL doesn't support.

## What this does

A **lock-in amplifier** recovers a small signal at a known frequency that's buried in noise. It does this by multiplying the noisy input by a clean sine wave at that same frequency (the "reference"), then low-pass filtering the result. After the filter, only the part of the input signal that matched the reference's frequency and phase survives — everything else (broadband noise, signals at other frequencies) averages out.

There are two ways the reference sine can be supplied:

### 1. Internal reference (the standard approach — `internal_lock_in.py`)

The Red Pitaya's FPGA generates the reference sine itself, digitally. A numerically controlled oscillator (NCO — basically a digital sine generator running off the 125 MHz clock) produces a clean sine at a frequency you set in software. The hardware then multiplies the ADC input by this internal sine and runs the result through a low-pass filter.

In PyRPL, all of this lives inside one hardware unit called the **IQ block** — it bundles the NCO, the multiplier, and the filter together. You configure it with one Python call. The output is the demodulated, filtered signal.

`internal_lock_in.py` configures one IQ block for a 10 MHz reference, takes the input on the first ADC (`in1`), and routes the filtered output to the first DAC (`out1`). It uses a second hardware unit — a **PID block** (proportional-integral-derivative controller, normally used for feedback control loops, but here just acting as a wire that copies the IQ's output to the DAC) — as a buffer.

This works with stock PyRPL — no custom firmware needed.

### 2. External reference (the new variant — `external_lock_in.py`)

Instead of an internal NCO, the reference comes from a **physical signal on the second ADC input**. The hardware multiplies the two real-world ADC inputs (`in1 × in2`) directly, then low-pass filters that product.

This requires a custom Verilog block in the PyRPL fork (`../pyrpl/`) that performs `in1 × in2` inside the FPGA and exposes the result as a new selectable signal called **`product`**. An IQ block is then pointed at `product` instead of an ADC, with its NCO frequency set to zero (so its internal multiplier becomes a no-op — multiplying by `cos(0) = 1`). All the IQ does in this mode is run the low-pass filter.

`external_lock_in.py` does exactly this: IQ takes `product` as input, NCO at DC, low-pass filter at 1 kHz, output on `out1`.

### 3. Two-output extractor — sum and difference simultaneously (`signal_multiplier.py`)

Same hardware multiplier as the external lock-in, but instead of just low-pass filtering the product, **two** IQ blocks run in parallel — each tuned to a different *predicted* center frequency. One targets the predicted sum f₁+f₂, the other targets the predicted difference |f₁−f₂|. Each IQ heterodynes the product down to baseband, low-pass filters, then re-modulates back up to its center frequency. The result: `out1` carries a clean sine at the true f₁+f₂, `out2` carries a clean sine at the true |f₁−f₂|, both phase-coherent with the input signals — even if your predicted frequencies are slightly off.

`signal_multiplier.py` configures both IQ blocks (`iq0` for sum, `iq1` for difference) on the `product` signal. It supports two modes via the `AUTO_TUNE` toggle at the top of the file: a **manual mode** where you supply nominal `f1`, `f2`, and a fractional uncertainty; and an **auto-tune mode** where the script measures the actual input frequencies through the internal scope and retunes the IQ NCOs to match, which drives the LPF's static phase shift to zero. See the "Configuring the extractor" section below for details.

## Files

| file | needs custom pyrpl? | what it does |
|---|---|---|
| `internal_lock_in.py` | no | Standard internal-reference lock-in. One IQ block at 10 MHz demodulates `in1`; a PID block buffers the filtered output to `out1`. |
| `external_lock_in.py` | **yes** | External-reference lock-in. Hardware multiplier computes `in1 × in2`; one IQ block low-pass filters the result and emits it on `out1`. |
| `signal_multiplier.py` | **yes** | Two-output extractor with optional auto-tuning. `iq0` → sum-frequency on `out1`, `iq1` → difference-frequency on `out2`. |
| `test_phase_coherence.py` | **yes** | Verifies the extractor preserves frequency relationships: captures inputs and outputs via internal scope, FFTs each, checks `f_sum_out ≈ f1+f2` and `f_diff_out ≈ |f1−f2|`. Inputs don't need to be phase-locked. |
| `test_zero_phase_shift.py` | **yes** | Stronger test — compares the phase of `iq1` to the diff tone in `product`, with optional auto-calibration of the IQ NCO to drive the LPF's static phase shift to zero. |
| `design_math.ipynb` | n/a | Jupyter notebook walking through the math behind `signal_multiplier.py` — four baseband frequencies, lowest-unwanted-frequency selection, LPF response, recombination, and the f_c/Δ phase-coherence story. Regenerate via `python build_notebook.py`. |

## Install

`internal_lock_in.py` works with stock PyRPL. The two scripts that use the hardware multiplier (`external_lock_in.py`, `signal_multiplier.py`) need the custom PyRPL fork that adds the `product` DSP-bus signal.

Recommended setup — clone both repos side by side and install the custom PyRPL into a venv:

```bash
# 1. Clone this repo (these scripts)
git clone https://github.com/cuiniaooo/Lock-in.git
cd Lock-in

# 2. Clone the custom PyRPL fork next to it
cd ..
git clone https://github.com/cuiniaooo/pyrpl.git

# 3. Create a venv and install the fork in editable mode
cd pyrpl
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -e ".[qt-pyqt6]"
```

The fork ships a prebuilt FPGA bitstream — see [`pyrpl/README_SIGNALEXTRACTOR.md`](https://github.com/cuiniaooo/pyrpl/blob/main/README_SIGNALEXTRACTOR.md) for how to deploy it to your Red Pitaya. If you only need `internal_lock_in.py`, `pip install pyrpl` from upstream is enough.

## Running

Edit the `hostname=` argument in any script to match your board, then from this repo:

```bash
# with the venv from above activated
python signal_multiplier.py
```

PyRPL connects, deploys its monitor server over SSH, configures the IQ blocks, and leaves the configuration running on the FPGA. The script then exits — the FPGA keeps doing the work until reconfigured or the board is power-cycled.

## Configuring the extractor

`signal_multiplier.py` has two modes selected by a toggle near the top of the file:

```python
AUTO_TUNE = True          # measure actual f1, f2 and derive uncertainty
                          # False: use manual values
CAPTURE_S = 1.0           # measurement window (AUTO_TUNE only)

F1_MANUAL = 246e3         # used when AUTO_TUNE=False; also used as
F2_MANUAL = 500e3         #   frequency-range hint when AUTO_TUNE=True
UNCERTAINTY_MANUAL = 0.05
```

**Manual mode** (`AUTO_TUNE = False`). The script uses `F1_MANUAL`, `F2_MANUAL`, and `UNCERTAINTY_MANUAL` directly. The IQ NCOs are set to nominal `f1 + f2` and `|f1 − f2|`, and the LPF cutoff is sized to allow `uncertainty × f_sum` of headroom in the passband. Pick `uncertainty` based on how confident you are in your nominal values (5% is a common default).

**Auto-tune mode** (`AUTO_TUNE = True`). The script first captures the ADC inputs via the internal scope, FFTs each, and finds the actual frequencies. It then retunes the IQ NCOs to those measured values and derives the `uncertainty` from the FFT bin width (`uncertainty = bin_width / f_sum`). This eliminates the LPF's static phase shift — the IQ NCO matches the actual signal exactly, so the LPF acts at DC where its phase response is identically zero.

`F1_MANUAL` and `F2_MANUAL` still matter in auto-tune mode. They're used as a **frequency-range hint** for the scope: the sample rate must satisfy Nyquist for the highest input frequency, or the FFT sees an aliased peak and the auto-tune tunes the IQ to garbage. Set the manual values within ~1.2× of where your real inputs are. The Red Pitaya's scope buffer is 16384 samples, so the achievable FFT bin width depends on frequency range — finer at low frequencies, coarser at MHz. The script reports the actual capture duration and bin width on each run.

The two-output extractor is structurally tolerant of small prediction errors — the output frequency and phase track the actual inputs, not the predictions, as long as the LPF passes the residual offset and rejects everything else. Auto-tune mode handles this calibration automatically; manual mode requires the user-supplied uncertainty to cover the worst case.

## Testing phase coherence

Two diagnostic scripts verify the extractor is behaving correctly. Run them after `signal_multiplier.py` has configured the IQ blocks (or let them reconfigure themselves — both do an idempotent setup that mirrors `signal_multiplier.py`).

**`test_phase_coherence.py`** checks that the output *frequencies* match what the math predicts. It captures `in1`, `in2`, and the two IQ outputs via the internal scope, FFTs each one, and confirms `f_sum_out ≈ f1 + f2` and `f_diff_out ≈ |f1 − f2|` to within an FFT bin. Useful as a sanity check that the FPGA multiplier, IQ blocks, and bus routing are all wired correctly. The inputs don't need to be phase-locked sources — drift is fine because inputs and outputs are measured in the same time window.

**`test_zero_phase_shift.py`** is a stronger test. It captures the raw `product` bus and the iq1 output simultaneously, then compares their *phase* at the diff-frequency FFT bin. The phase difference is the LPF's static phase shift `−N·arctan(Δf/f_c)`. With `AUTO_CALIBRATE = True`, the script first measures the actual `f1, f2`, retunes the IQ NCO so Δf → 0, and verifies the resulting phase shift is zero. With `AUTO_CALIBRATE = False`, it leaves the IQ at nominal and lets the script demonstrate that the measured shift matches the predicted LPF behavior to within ~1°. Together the two modes establish both that (a) calibration eliminates phase distortion, and (b) when distortion is present, it's the predictable LPF response with no unmodeled extras.

## Design math notes

The math behind `signal_multiplier.py` — the four baseband frequencies produced by the IQ mixer, why we pick `min(2f₁, 2f₂, max(f_d, 2f_d − Δ))` as the lowest unwanted frequency, the LPF transfer function, cascading stages, the `f_c/Δ` ratio that governs phase coherence, and the recombination math — is written up as a Jupyter notebook at `design_math.ipynb`.

The notebook is generated by `build_notebook.py`. To edit, change the cell content in that Python file (it uses raw strings so LaTeX backslashes work naturally), then run `python build_notebook.py` to regenerate the `.ipynb`. Open the notebook in any tool that renders Jupyter math: PyCharm Professional, JupyterLab, classic Jupyter Notebook, or VS Code with the Jupyter extension all work. Each cell's LaTeX renders via MathJax/KaTeX.