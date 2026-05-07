from pyrpl import Pyrpl

p = Pyrpl("lockin_config", hostname="rp-f0eb1d.local", gui=False)
r = p.rp

#shortcut
iq = r.iq0

# modulation/demodulation frequency 25 MHz
# two lowpass filters with 10 and 20 kHz bandwidth
# input signal is analog input 1
# input AC-coupled with cutoff frequency near 50 kHz
# modulation amplitude 0.1 V
# modulation goes to out1
# output_signal is the demodulated quadrature 1
# quadrature_1 is amplified by 10
iq.setup(frequency=2e3, bandwidth=[10,20], gain=0.0,
         phase=0, acbandwidth=100, amplitude=0.5,
         input='in1', output_direct='out1',
         output_signal='quadrature', quadrature_factor=10)