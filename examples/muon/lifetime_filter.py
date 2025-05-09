"""Module **lifetime_filter**

This (rather complex) module filters waveform data to search for valid
signal pulses in the channel data. The goal is to clearly identify coincidences
of signals in different layers (indiating the passage of a cosmic ray particle,
a muon) and find double-pulse signatures that a muon was stopped in
or near a detection layer where the resulting decay-electron produced a delayed
pulse. The time difference between the initial and the delayed pulses is
the individual lifetime of the muon.

Wave forms passing this filter-criterion an passed on to a new buffer; the
decay time and the properties of the signal pulses (height, integral and
postition in time) are written to another buffer.

The relevant configuration parameters can be found in the section
*calculate_decay_time:* of the configuration file.

"""

from mimocorb2.worker_templates import Processor
import numpy as np
import os
import sys

from filters import *


def calculate_decay_time(buffer_io):
    """Calculate decay time as time between double pulses

    Input:
      pulse wave forms

    Returns:
      None if failed, int or list of pulse parameters if successful

      Note: output produced when filter is passed depends on number of defined sinks:

      - one sink:   input data
      - two sinks:  input data and double-pulse parameters
      - three sinks: input data and double-pulse parameters separately for upwards and
        for downwards going decay electrons

    """

    processor = Processor(buffer_io)
    config = processor.config

    # Load configuration
    sample_time_ns = config["sample_time_ns"]
    analogue_offset = config["analogue_offset"] * 1000
    peak_minimal_prominence_initial = config["peak_minimal_prominence_initial"]
    peak_minimal_prominence_secondary = config["peak_minimal_prominence_secondary"]
    peak_minimal_prominence = min(peak_minimal_prominence_initial, peak_minimal_prominence_secondary)
    peak_minimal_distance = config["peak_minimal_distance"]
    peak_minimal_width = config["peak_minimal_width"]
    trigger_position_tolerance = config["trigger_position_tolerance"]
    signatures = config["signatures"]

    # Load reference pulse
    reference_pulse = None if "reference_pulse_file" not in config else np.fromfile(config["reference_pulse_file"])

    pulse_par_dtype = processor.data_out_examples[1].dtype

    def find_double_pulses(input_data):
        """filter data, function to be called by instance of class mimoCoRB.rbTransfer

        Args:  input data as structured ndarray

        Returns: list of parameterized data
        """

        # Find all the peaks and store them in a dictionary
        peaks, peaks_prop = tag_peaks(
            input_data,
            peak_minimal_prominence,
            peak_minimal_distance,
            peak_minimal_width,
        )

        # Group the found peaks (assumtion from here on: 1st group = muon, 2nd group = electron/positron)
        correlation_matrix = correlate_peaks(peaks, trigger_position_tolerance)

        # Are there at least two peaks?
        if len(correlation_matrix) < 2:
            return None

        # Make sure "minimal prominence" criteria are met
        for ch in correlation_matrix.dtype.names:
            idx = correlation_matrix[ch][0]  # 1st pulse
            if idx >= 0:
                if (
                    peaks_prop[ch]["prominences"][idx] * config["{:s}_scaling".format(ch)]
                    < peak_minimal_prominence_initial
                ):
                    correlation_matrix[ch][0] = -1
            idx = correlation_matrix[ch][1]  # 2nd pulse
            if idx >= 0:
                if (
                    peaks_prop[ch]["prominences"][idx] * config["{:s}_scaling".format(ch)]
                    < peak_minimal_prominence_secondary
                ):
                    correlation_matrix[ch][1] = -1

        pulse_parameters = None
        signature_type = None
        # Look for double pulses (hinting towards a muon decay)
        for _sigtype, sig in enumerate(signatures):
            if match_signature(correlation_matrix, sig):
                pulse_parameters = np.zeros((1,), dtype=pulse_par_dtype)
                first_pos = []
                second_pos = []
                for ch in correlation_matrix.dtype.names:
                    # Process first peak (muon) and second peak (decay electron)
                    for i in range(2):
                        idx = correlation_matrix[ch][i]
                        if idx >= 0:
                            p_pos = peaks[ch][idx]
                            p_height = peaks_prop[ch]["prominences"][idx]
                            this_pulse, p_new_pos, p_int = normed_pulse(
                                input_data[ch], p_pos, p_height, analogue_offset
                            )
                            if reference_pulse is not None:
                                correction = correlate_pulses(this_pulse, reference_pulse)
                                p_pos = p_new_pos + correction
                            if i == 0:
                                first_pos.append(p_pos)
                                pulse_parameters["1st_{:s}_p".format(ch)] = p_pos
                                pulse_parameters["1st_{:s}_h".format(ch)] = p_height
                                pulse_parameters["1st_{:s}_int".format(ch)] = (p_int,)
                            else:
                                second_pos.append(p_pos)
                                pulse_parameters["2nd_{:s}_p".format(ch)] = p_pos
                                pulse_parameters["2nd_{:s}_h".format(ch)] = p_height
                                pulse_parameters["2nd_{:s}_int".format(ch)] = p_int

                pulse_parameters["decay_time"] = [
                    (np.mean(second_pos) - np.mean(first_pos)) * sample_time_ns,
                ]
                signature_type = _sigtype

        if pulse_parameters is None:
            return None

        if signature_type == 0:
            return [input_data, pulse_parameters, None]
        elif signature_type == 1:
            return [input_data, None, pulse_parameters]

    processor(find_double_pulses)


if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, "-"))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
