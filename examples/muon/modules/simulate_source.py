import mimocorb2 as mi2
import numpy as np
import time


def simulate_source(buffer_io):
    """mimoCoRB2 Function: Simulate a source of muon pulses

    Type
    ----
    Importer

    Buffers
    -------
    sinks
        Waveform data

    Configs
    -------
    analogue_offset : float
        Offset applied to the simulated pulses in Volts.
    trigger_level : float, optional (default=analogue_offset)
        Trigger level for the first pulse in Volts.
    sample_time_ns : int
        Sample time in nanoseconds.
    pre_trigger_samples : int
        Number of samples before the trigger.
    eventcount : int, optional (default=1000)
        Number of events to simulate. Use -1 for infinite.
    sleeptime : float, optional (default=0.10)
        Sleep time between events in seconds. If random is True, this is a random Poisson
        distributed time.
    random : bool, optional (default=False)
        If True, the sleep time is randomly distributed.
    pulseWindow : int, optional (default=100)
        Length of the pulse in samples.
    pulseHeight : float or list of floats, optional (default=250.0)
        Height of the pulse in mV. If a list, multiple heights are used.
    pulseSpread : float, optional (default=pulseHeight * 0.3)
        Spread of the pulse height in mV.
    prbIteraction : float, optional (default=0.95)
        Probability of interaction with the detector.
    prb2ndPulse : float, optional (default=0.10)
        Probability of a second pulse after the first.
    """
    importer = mi2.Importer(buffer_io)
    config = importer.config

    # get parameters
    # self.number_of_samples = config_dict["number_of_samples"]  # not needed here, taken from buffer configuration
    analogue_offset_mv = config.get("analogue_offset") * 1000.0
    trigger_level = config.get("trigger_level", analogue_offset_mv) - analogue_offset_mv
    sample_time_ns = config.get("sample_time_ns")
    pre_trigger_samples = config.get("pre_trigger_samples")
    events_required = config.get("eventcount", 1000)
    sleeptime = config.get("sleeptime", 0.10)
    random = config.get("random", False)
    plen = config.get("pulseWindow", 100)

    pulse_height = config.get("pulseHeight", 250.0)
    if not isinstance(pulse_height, list):
        pulse_height = [pulse_height]
    pulse_height = np.array(pulse_height)

    pulse_spread = config.get("pulseSpread", pulse_height * 0.3)
    detector_efficiency = config.get("prbIteraction", 0.95)
    stopping_probability = config.get("prb2ndPulse", 0.10)

    data_example = importer.data_example
    number_of_channels = len(data_example.dtype)
    number_of_values = data_example.size
    channel_names = data_example.dtype.names

    # parameters for pulse simulation and detector porperties
    tau = plen / 4.0  # decay time of exponential pulse
    mn_position = pre_trigger_samples
    mx_position = number_of_values - plen
    pulse_template = np.exp(-np.float32(np.linspace(0.0, plen, plen, endpoint=False)) / tau)
    noise = pulse_height.mean() / 30.0
    tau_mu = 2197  # muon life time in ns
    T_spin = 0.85 * tau_mu  # spin precession time
    A_spin = 0.05  # (relative) amplitude of precession signal

    def ufunc():
        event_count = 0
        while True:
            if events_required != -1 and event_count > events_required:
                break
            else:
                event_count += 1
            nchan = number_of_channels
            pulse = np.float32(noise * (0.5 - np.random.rand(nchan, number_of_values)))

            if np.random.rand() < stopping_probability:  # stopped muon ?
                stopped_mu = True
                n1 = min(2, nchan)  # only 2 layers for 1st pulse
            else:
                stopped_mu = False  # 4 layers for passing muon
                n1 = nchan

            # one pulse at trigger position in layers one and two
            for i_layer in range(n1):
                # random pulse height for trigger pulse
                pheight = np.random.choice(pulse_height) + pulse_spread * np.random.normal()
                if i_layer == 0:
                    #  respect trigger condition in layer 1
                    while pheight < trigger_level:
                        pheight = np.random.choice(pulse_height) + pulse_spread * np.random.normal()
                if np.random.rand() < detector_efficiency:
                    pulse[i_layer, mn_position : mn_position + plen] += pheight * pulse_template

            # return if muon was not stopped
            if stopped_mu:
                # add delayed pulse(s)
                t_mu = -tau_mu * np.log(np.random.rand())  # muon life time
                pos2 = int(t_mu / sample_time_ns) + pre_trigger_samples
                if np.random.rand() > 0.5 + 0.5 * A_spin * np.cos(2 * np.pi * t_mu / T_spin):  # upward decay electron
                    for i_layer in range(0, min(nchan, 2)):
                        # random pulse height and position for 2nd pulse
                        ## pheight2 = np.random.rand()*maxheight
                        pheight2 = np.random.choice(pulse_height) + pulse_spread * np.random.normal()
                        if np.random.rand() < detector_efficiency and pos2 < mx_position:
                            pulse[i_layer, pos2 : pos2 + plen] += pheight2 * pulse_template
                else:
                    for i_layer in range(min(nchan, 2), min(nchan, 4)):
                        # random pulse height and position for 2nd pulse
                        ## pheight2 = np.random.rand()*maxheight
                        pheight2 = np.random.choice(pulse_height) + pulse_spread * np.random.normal()
                        if np.random.rand() < detector_efficiency and pos2 < mx_position:
                            pulse[i_layer, pos2 : pos2 + plen] += pheight2 * pulse_template
            pulse += analogue_offset_mv  # apply analogue offset

            # simulate timing via sleep: respect wait time
            if random:  # random ...
                time.sleep(-sleeptime * np.log(np.random.rand()))  # random Poisson sleept time
            else:  # ... or fixed time
                time.sleep(sleeptime)  # fixed sleep time

            out = data_example.copy()
            for i, ch in enumerate(channel_names):
                out[ch] = pulse[i]

            yield out
        yield None

    importer(ufunc)
