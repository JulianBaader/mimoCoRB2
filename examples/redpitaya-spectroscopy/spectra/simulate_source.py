import numpy as np
import re
import scipy
from mimocorb2.worker_templates import Importer
import time
import os


def convert_html_to_numpy(file: str) -> list[np.ndarray]:
    """Read in the html file and extract the clean spectrum data."""
    with open(file, "r", encoding="utf-8") as file:
        html_content = file.read()

    x_matches = re.findall(r'"x":\[(.*?)\]', html_content)
    y_matches = re.findall(r'"y":\[(.*?)\]', html_content)

    # Extract the second occurrence -> Clean spectrum
    if len(x_matches) >= 2 and len(y_matches) >= 2:
        x_data = np.array(list(map(float, x_matches[1].split(','))))
        y_data = np.array(list(map(float, y_matches[1].split(','))))

        return x_data, y_data
    else:
        raise RuntimeError("Failed to extract clean spectrum from the html file.")


def simulate_source(buffer_io):
    importer = Importer(buffer_io)
    config = importer.config

    M = config.get("M", 1)
    tau = config.get("tau", 1)
    trigger_level = config.get("trigger_level", 0)
    number_of_samples_before_trigger = config.get("number_of_samples_before_trigger", 0)
    energy_conversion = config.get("energy_conversion", [1, 0])  # [slope, offset]
    slope = energy_conversion[0]
    offset = energy_conversion[1]
    noise = config.get("noise", 0)
    file = os.path.join(importer.setup_directory, config.get("file", "spectra/Co-60.html"))
    average_rate = config.get("average_rate", 100)

    number_of_samples = importer.data_example.size

    t = np.arange(0, number_of_samples)
    # generate pulse form
    pulse = 1 / scipy.special.factorial(M) * np.exp(-1 / tau * t) * (1 / tau * t) ** M
    # set max to 1
    pulse /= pulse.max()

    def generate_pulse(energy):
        value = energy * slope + offset
        scaled_pulse = pulse * value
        # scaled_pulse += np.random.normal(0, noise, number_of_samples)
        trigger_time = np.argmax(scaled_pulse > trigger_level)

        output = np.zeros(number_of_samples)
        output[trigger_time + number_of_samples_before_trigger :] = scaled_pulse[
            : number_of_samples - trigger_time - number_of_samples_before_trigger
        ]
        # output = np.clip
        output += np.random.normal(0, noise, number_of_samples)
        return output

    energys, counts = convert_html_to_numpy(file)

    counts = np.clip(counts, 0, None)
    counts /= counts.sum()

    def ufunc():
        while True:
            energy = np.random.choice(energys, p=counts)
            yield generate_pulse(energy)
            time.sleep(1 / average_rate)  # TODO Poisson process

    importer(ufunc)
