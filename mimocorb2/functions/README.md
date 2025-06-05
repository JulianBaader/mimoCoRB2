# Built-in Functions
In this directory built in functions for the mimoCoRB application are provided.
To use them in your application add a worker to the setup without the file key or an empty string as the file.

## Exporters
Exporters are functions which take data out of the mimoCoRB application.

* exporters.drain
    * Drain events from a buffer (usefull for developement/debugging)

## Observers
Observers are functions which randomly take a look at data from a buffer and then return that data to the buffer.
* observers.oscilloscope
    * Display an Oscilloscope of the data

## Misc

* misc.copy
    * Copy data from one Buffer to (multiple) other(s)

## Data
The data module can be used to import or export raw data from the mimoCoRB system. ".mimo" files consist of a pickled header and binary numpy data
* data.export
    * exports the data from a buffer as a ".mimo" file
* data.simulate_importer
    * !Not correctly implemented!
    * In theory this will put events into the system in the same order and rate as from when the data was taken
* data.clocked_importer
    * !Not correctly implemented!
    * In theory this will put events into the system at a fixed (uniform/poisson) rate.

## Analyzers
Analyzers can be used to process data
* analyzers.pha
    * A pulse height analyzer using the scipy.signal.find_peaks method