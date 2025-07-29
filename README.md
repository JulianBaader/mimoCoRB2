Introduction
============



What is mimoCoRB2?
------------------

mimoCoRB2 (multiple in multiple out configurable ringbuffer manager) provides a
central component of each data acquisition system needed to record and
preanalyse data from randomly occurring processes. Typical examples are
waveform data as provided by detectors common in quantum mechanical
measurements, or in nuclear, particle and astro particle physics, e. g. photo
tubes, Geiger counters, avalanche photo-diodes or modern SiPMs. The random
nature of such processes and the need to keep read-out dead times low requires
an input buffer for fast collection of data and an efficient buffer manager
delivering a constant data stream to the subsequent processing steps. While a
data source feeds data into the buffer, consumer processes receive the data to
filter, reduce, analyze or simply visualize the recorded data. In order to
optimally use the available resources, multi-core and multi-processing
techniques must be applied.



This project originated from an effort to structure and generalize data acquisition for several experiments in advanced
physics laboratory courses at Karlsruhe Institute of Technology (KIT) and has been extensively tested with Ubuntu
Linux.


What can it do?
---------------

Amongst the core features of mimoCoRB2 are:

* multiprocessing safe ringbuffer for NumPy structured arrays
* setup of multiple ringbuffers and workers from configuration files
* templates for common interactions between buffers (importing/exporting, filtering, processing, observing)
* pre built functions for common operations (oscilloscope, histogram, pulse height analysis)
* gui for monitoring and controlling the system

Running an example
------------------
Clone this repo and move into the directory
```bash
pip install .
mimocorb2 examples/muon/spin_setup.yaml
```