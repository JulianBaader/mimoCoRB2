Examples
--------

mimoCoRB2 comes with a set of examples that can be used to get started quickly. The
examples are located in the `examples` directory of the mimoCoRB2 package alongside
an explenation of the experiment. Each example is self-contained and can be run
independently. The examples stem from experiments currently running at KIT and are
meant to be used as a starting point for your own experiments.

To run the examples, you need to have the whole git repository cloned and installed.
Then, you can run the examples by using the following command:
```bash
mimocorb2 <setup_file>
```
where `<setup_file>` is the path to the setup file of the example you want to run.
For example, to run the `muon` setup, you would use:
```bash
mimocorb2 examples/muon/spin_setup.yaml
```

Available examples include:
- ```examples/mimo_files/write_setup.yaml```: A simple example that writes waveform data in the mimo format.
- ```examples/mimo_files/read_setup.yaml```: A simple example that reads said waveform data.
- ```examples/redpitaya-spectroscopy/setup.yaml```: An example of a redpitaya-based gamma spectroscopy experiment.
- ```examples/muon/spin_setup.yaml```: An example of a muon experiment.
- ```examples/simple/setup.yaml```: A simple pulseheight analysis example.

See the respective `examples/<example_name>/README.md` files for more details on each example.

The following section provides a brief overview of the standard interface with the muon example.

Muon Example Overview
----------------------
When running the muon example, multiple windows will open:

1. **Two Oscilloscopes**: These display the waveforms of the incomming data and the interesting data.

    .. image:: screenshots/oscilloscope.png
        :alt: Screenshot of an oscilloscope windows in the muon example
        :width: 500px
        :align: center

2. **Two Histograms**: These show the distribution of interesting parameters.

    .. image:: screenshots/hist.png
        :alt: Screenshot of a histogram window in the muon example
        :width: 500px
        :align: center

3. **Buffer Manager**: This window allows you to manage the whole DAQ suite.

    .. image:: screenshots/rate.png
        :alt: Screenshot of the buffer manager window in the muon example (Rate Tab)
        :width: 500px
        :align: center

The buffer manager has multiple tabs:

- **Rate Information**: Displays the rate of each buffer.
- **CPU Information**: Shows the CPU usage of each worker.
- **Process Information**: Shows how many processes each worker is running.
- **Buffer Information**: Displays the current state of each buffer.
- **Logs**: Shows the print statements of each worker.

Underneath the tabs, you can find a table, with exact numbers on the 'root buffers'
In the row below the table, some additional information is displayed, such as the
time the experiment has been running and the number of processes running.

At the bottom of the window, you can find the buttons to control the experiment:

- **Pause/Resume Roots** - Pauses or resumes the root buffers. (-> Any incoming data is discarded while paused.)
- **Shutdown Root Buffer** - Shuts down the root buffers which (ideally) shuts down all other buffers once they are empty.
- **Shutdown all Buffers** - Incase that there are still processes running, this will signal to all buffers to shut down.
- **Shutdown Workers** - Incase after that there are still processes running this will kill them (you might lose data).
- **Exit** - Closes the buffer manager. This is only possible if all processes are finished.

Each run of the experiment creates a new run directory in the `target_directory` specified in the
setup file (default is inside the same directory as the setup file).

For every experiment run, the following files are created:

- `data_flow.svg`: A diagram of the Buffers and Workers used in the experiment.
- `setup.yaml`: The complete setup used for the experiment (including configs).
- `stats.csv`: A CSV file containing statistics about the experiment run.
In case of the muon example, the following additional files are created:

- `PulseParametersUp_Export.csv` and `PulseParametersDown_Export.csv`: CSV files containing the parameters of the pulses detected in the up and down direction.
- `AcceptedPulses.mimo`: A MIMO file containing the accepted pulses.
- `Histograms_PulseParametersUp/` and `Histograms_PulseParametersDown/`: Directories containing the histograms of the pulse parameters in the up and down direction, respectively.
