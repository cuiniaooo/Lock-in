from pyrpl import Pyrpl

p = Pyrpl("lockin_config", hostname="rp-f0eb1d.local", gui=False)
r = p.rp

# IQ demodulator
iq = r.iq0

iq.setup(
    frequency=10e6,
    bandwidth=[10e3, 20e3],
    gain=0.0,
    phase=0,
    acbandwidth=50000,
    amplitude=0.5,          # turn off internal sine on out1
    input='in1',
    output_direct='out2',    # do NOT send LO to out1
    output_signal='quadrature',
    quadrature_factor=10
)

# PID as router/buffer
pid = r.pid0
pid.setup(
    input='iq0',
    output_direct='out1',
    setpoint=0,
    p=1.0,
    i=0.0,
    inputfilter=[],
    max_voltage=8.0,
    min_voltage=-8.0
)