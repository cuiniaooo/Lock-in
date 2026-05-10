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

`signal_multiplier.py` configures both IQ blocks (`iq0` for sum, `iq1` for difference) on the `product` signal.

## Files

| file | needs custom pyrpl? | what it does |
|---|---|---|
| `internal_lock_in.py` | no | Standard internal-reference lock-in. One IQ block at 10 MHz demodulates `in1`; a PID block buffers the filtered output to `out1`. |
| `external_lock_in.py` | **yes** | External-reference lock-in. Hardware multiplier computes `in1 × in2`; one IQ block low-pass filters the result and emits it on `out1`. |
| `signal_multiplier.py` | **yes** | Two-output extractor. `iq0` → sum-frequency on `out1`, `iq1` → difference-frequency on `out2`. |

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

`signal_multiplier.py` exposes the two input frequencies at the top of the file:

```python
f1 = 1265   # frequency on ADC1 (Hz)
f2 = 1069   # frequency on ADC2 (Hz)
```

Set these to your *predicted* input frequencies. The two-output extractor is structurally tolerant of small prediction errors — the output frequency and phase track the actual inputs, not the predictions, as long as the post-mixer low-pass filter is sized correctly (the filter must pass the prediction error and reject everything outside).