import socket
import struct
import numpy as np

from mimocorb2.worker_templates import Importer

SOCKET_TIMEOUT = 5


COMMANDS = {
    0: "reset histogram",
    1: "reset timer",
    2: "reset oscilloscope",
    3: "reset generator",
    4: "set sample rate",
    5: "set negator mode (0 for disabled, 1 for enabled)",
    6: "set pha delay",
    7: "set pha threshold min",
    8: "set pha threshold max",
    9: "set timer",
    10: "set timer mode (0 for stop, 1 for running)",
    11: "read status",
    12: "read histogram",
    13: "set trigger source (0 for channel 1, 1 for channel 2)",
    14: "set trigger slope (0 for rising, 1 for falling)",
    15: "set trigger mode (0 for normal, 1 for auto)",
    16: "set trigger level",
    17: "set number of samples before trigger",
    18: "set total number of samples",
    19: "start oscilloscope",
    20: "read oscilloscope data",
    21: "set fall time",
    22: "set rise time",
    23: "set lower limit",
    24: "set upper limit",
    25: "set rate",
    26: "set probability distribution",
    27: "reset spectrum",
    28: "set spectrum bin",
    29: "start generator",
    30: "stop generator",
    31: "start daq",
}

SAMPLE_RATES = [1, 4, 8, 16, 32, 54, 128, 256]
INPUTS = {"IN1": 0, "IN2": 1}
TRIGGER_SLOPES = {"rising": 0, "falling": 1}
TRIGGER_MODES = {"normal": 0, "auto": 1}
MAXIMUM_SAMPLES = 8388607  # TODO not sure about this value
MIN_ADC_VALUE = -4096
MAX_ADC_VALUE = 4095
NUMBER_OF_GENERATOR_BINS = 4096
DISTRIBUTIONS = {"uniform": 0, "poisson": 1}
ACQUISITION_MODES = ['save', 'process']

PORT = 1001

PLOT_SPECTRUM = True

CUT_OFF = 100
"""
For some reason the last few samples are not read correctly.
Requesting 100 samples more and discarding them works.
This is a temporary fix.
"""


class rpControll:
    def __init__(self):
        self.sample_rate = None
        self.negators = {"IN1": None, "IN2": None}
        self.trigger_source = None
        self.trigger_slope = None
        self.trigger_mode = None
        self.trigger_level = None
        self.number_of_samples_before_trigger = None
        self.total_number_of_samples = None

        self.fall_time = None
        self.rise_time = None
        self.generator_rate = None
        self.distribution = None
        self.spectrum = None

        self.set_size = None

        self.requested_count = 0

    def connect(self, ip):
        self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.socket.connect((ip, PORT))
        self.socket.settimeout(SOCKET_TIMEOUT)
        return True

    def command(self, code, number, value):
        # print("Sending command: ", COMMANDS[code], " with number ", number, " and value ", value)
        # print(COMMANDS[code])
        self.socket.sendall(struct.pack("<Q", code << 56 | number << 52 | (int(value) & 0xFFFFFFFFFFFFF)))

    # Set Configuration
    def set_sample_rate(self, rate):
        if rate not in SAMPLE_RATES:
            raise ValueError("Invalid sample rate")
        self.sample_rate = rate
        self.command(4, 0, rate)

    def set_negator(self, negated, channel):
        if negated:
            value = 1
        else:
            value = 0
        if channel not in INPUTS:
            raise ValueError("Invalid channel")
        self.negators[channel] = value
        self.command(5, INPUTS[channel], value)

    def set_trigger_source(self, channel):
        if channel not in INPUTS:
            raise ValueError("Invalid channel")
        self.trigger_source = channel
        self.command(13, INPUTS[channel], 0)

    def set_trigger_slope(self, slope):
        if slope not in TRIGGER_SLOPES:
            raise ValueError("Invalid slope")
        self.trigger_slope = slope
        self.command(14, 0, TRIGGER_SLOPES[slope])

    def set_trigger_mode(self, mode):
        if mode not in TRIGGER_MODES:
            raise ValueError("Invalid mode")
        self.trigger_mode = mode
        self.command(15, 0, TRIGGER_MODES[mode])

    def set_trigger_level(self, level):
        if not isinstance(level, int):
            raise ValueError("Invalid level (must be integer)")
        if level < MIN_ADC_VALUE or level > MAX_ADC_VALUE:  # TODO does a negative level make sense?
            raise ValueError("Invalid level (out of range)")
        self.trigger_level = level
        self.command(16, 0, level)

    def set_number_of_samples_before_trigger(self, number):
        if not isinstance(number, int):
            raise ValueError("Invalid number (must be integer)")
        if number < 0 or number > MAXIMUM_SAMPLES:
            raise ValueError("Invalid number (out of range)")
        if self.total_number_of_samples is not None and number > self.total_number_of_samples:
            raise ValueError("Invalid number (must be less than total number of samples)")
        self.number_of_samples_before_trigger = number
        self.command(17, 0, number)

    def set_total_number_of_samples(self, number):
        if not isinstance(number, int):
            raise ValueError("Invalid number (must be integer)")
        if number < 0 or number > MAXIMUM_SAMPLES:
            raise ValueError("Invalid number (out of range)")
        if self.number_of_samples_before_trigger is not None and number < self.number_of_samples_before_trigger:
            raise ValueError("Invalid number (must be greater than number of samples before trigger)")

        self.osc_bytes = np.zeros(2 * number, dtype=np.int16).nbytes
        self.cut_bytes = np.zeros(2 * CUT_OFF, dtype=np.int16).nbytes

        self.cut_view = np.zeros(2 * CUT_OFF, dtype=np.int16).view(np.uint8)

        self.total_number_of_samples = number
        self.command(18, 0, number + CUT_OFF)

    def set_generator_fall_time(self, fall_time):
        # TODO check if time is valid
        # TODO unit of time
        self.fall_time = fall_time
        self.command(21, 0, fall_time)

    def set_generator_rise_time(self, rise_time):
        # TODO check if time is valid
        # TODO unit of time
        self.rise_time = rise_time
        self.command(22, 0, rise_time)

    def set_generator_rate(self, rate):
        # TODO check if rate is valid
        # TODO unit of rate
        self.generator_rate = rate
        self.command(25, 0, rate)

    def set_generator_distribution(self, distribution):
        if distribution not in DISTRIBUTIONS:
            raise ValueError("Invalid distribution")
        self.distribution = distribution
        self.command(26, 0, DISTRIBUTIONS[distribution])

    def set_generator_spectrum(self, spectrum):
        # TODO check if spectrum is valid
        if len(spectrum) != NUMBER_OF_GENERATOR_BINS:
            raise ValueError("Invalid spectrum")
        self.spectrum = spectrum
        for value in np.arange(NUMBER_OF_GENERATOR_BINS, dtype=np.uint64) << 32 | self.spectrum:
            self.command(28, 0, value)

    def reset_spectrum(self):
        self.command(27, 0, 0)

    def set_spectrum(self):
        raise NotImplementedError()

    def start_generator(self):
        self.command(29, 0, 0)

    def stop_generator(self):
        self.command(30, 0, 0)

    def reset_oscilloscope(self):
        self.command(2, 0, 0)

    def start_oscillocsope(self):
        self.command(19, 0, 0)

    def set_set_size(self, set_size):
        self.set_size = set_size

    def acquire_set(self):
        buffer = np.zeros(self.set_size * 2 * self.total_number_of_samples, dtype=np.int16)
        view = buffer.view(np.uint8)
        reshaped = buffer.reshape((2, self.total_number_of_samples, self.set_size), order='F').transpose((2, 0, 1))
        self.command(31, 0, self.set_size)

        for i in range(self.set_size):
            bytes_received = 0
            while bytes_received < self.osc_bytes:
                bytes_received += self.socket.recv_into(
                    view[i * self.osc_bytes + bytes_received :], self.osc_bytes - bytes_received
                )

            bytes_received = 0
            while bytes_received < self.cut_bytes:
                bytes_received += self.socket.recv_into(self.cut_view[bytes_received:], self.cut_bytes - bytes_received)

        return reshaped

    def acquire_single(self):
        while True:
            buffer = np.zeros(2 * self.total_number_of_samples, dtype=np.int16)
            view = buffer.view(np.uint8)
            reshaped = buffer.reshape((2, self.total_number_of_samples), order='F')
            self.command(31, 0, self.set_size)
            for i in range(self.set_size):
                bytes_received = 0
                while bytes_received < self.osc_bytes:
                    bytes_received += self.socket.recv_into(view[bytes_received:], self.osc_bytes - bytes_received)

                bytes_received = 0
                while bytes_received < self.cut_bytes:
                    bytes_received += self.socket.recv_into(
                        self.cut_view[bytes_received:], self.cut_bytes - bytes_received
                    )

                yield reshaped.copy()

    def testing_setup(self, ip):
        self.connect(ip)
        self.set_sample_rate(4)
        self.set_negator(0, "IN1")
        self.set_negator(0, "IN2")

        self.set_trigger_source("IN1")
        self.set_trigger_slope("rising")
        self.set_trigger_mode("normal")
        self.set_trigger_level(100)

        self.set_total_number_of_samples(1000)
        self.set_number_of_samples_before_trigger(100)

        self.set_generator_fall_time(10)
        self.set_generator_rise_time(100)
        self.set_generator_distribution("poisson")
        self.set_generator_rate(1000)

        self.set_generator_spectrum(np.load("generators/comb.npy"))
        self.start_generator()

        self.reset_oscilloscope()
        self.start_oscillocsope()


def waveform(buffer_io):
    """mimoCoRB2 Function: Use RedPitaya to acquire waveform data.

    <longer description>

    Type
    ----
    Importer

    Buffers
    -------
    sources
        0
    sinks
        1 with data_dtype: {'IN1': int16, 'IN2': int16}
        data_length decides the total number of samples (must be larger than number_of_samples_before_trigger and less than MAXIMUM_SAMPLES)
    observes
        0

    Configs
    -------
    ip: str
        IP address of the RedPitaya device.
    sample_rate: int
        Number of samples (125MHz) averaged into one. Must be one of the values in SAMPLE_RATES.
    negator_IN1: bool, optional (default=False)
        If True, the IN1 input is negated.
    negator_IN2: bool, optional (default=False)
        If True, the IN2 input is negated.
    trigger_slope: str, optional (default='rising')
        Slope of the trigger. Must be one of the values in TRIGGER_SLOPES.
    trigger_mode: str, optional (default='normal')
        Mode of the trigger. Must be one of the values in TRIGGER_MODES.
    trigger_level: int
        Level of the trigger. Must be between MIN_ADC_VALUE and MAX_ADC_VALUE.
    trigger_source: str, optional (default='IN1')
        Source of the trigger. Must be one of the values in INPUTS.
    number_of_samples_before_trigger: int
        Number of samples to acquire before the trigger. Must be an integer between 0 and the total number of samples.
    set_size: int, optional (default=100)
        Number of sets to acquire in one acquisition.
    """
    importer = Importer(buffer_io)

    config_dict = importer.config
    try:
        ip = config_dict['ip']
        sample_rate = config_dict['sample_rate']
        trigger_level = config_dict['trigger_level']
        number_of_samples_before_trigger = config_dict['number_of_samples_before_trigger']
    except KeyError as e:
        raise ValueError("ERROR! Missing configuration parameter: " + str(e))

    negator_IN1 = config_dict.get('negator_IN1', False)
    negator_IN2 = config_dict.get('negator_IN2', False)
    trigger_slope = config_dict.get('trigger_slope', 'rising')
    trigger_mode = config_dict.get('trigger_mode', 'normal')
    set_size = config_dict.get('set_size', 100)
    trigger_source = config_dict.get('trigger_source', 'IN1')

    rp = rpControll()
    rp.connect(ip)
    rp.set_sample_rate(sample_rate)
    rp.set_negator(negator_IN1, "IN1")
    rp.set_negator(negator_IN2, "IN2")
    rp.set_trigger_slope(trigger_slope)
    rp.set_trigger_mode(trigger_mode)
    rp.set_trigger_level(trigger_level)
    rp.set_number_of_samples_before_trigger(number_of_samples_before_trigger)

    rp.set_set_size(set_size)

    rp.set_trigger_source(trigger_source)  # TODO

    data_example = importer.data_example.copy()

    rp.set_total_number_of_samples(data_example.size)

    gen = rp.acquire_single()

    def ufunc():
        while True:
            ch1, ch2 = next(gen)
            data_example["IN1"] = ch1
            data_example["IN2"] = ch2
            yield data_example.copy()

    rp.reset_oscilloscope()
    rp.start_oscillocsope()

    importer(ufunc)


if __name__ == "__main__":
    print("This is a mimoCoRB module and is not meant to be run directly.")
