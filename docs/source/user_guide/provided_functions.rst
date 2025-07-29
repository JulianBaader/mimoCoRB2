Prebuilt Functions
========================
Mimocorb2 comes with a set of built-in functions for common tasks. To use them, ommit the 'file' keyword or use an empty string in the Worker Setup.
The functions are listet below:

Exporters
---------
.. automethod:: mimocorb2.functions.exporters.drain
.. automethod:: mimocorb2.functions.exporters.histogram
.. automethod:: mimocorb2.functions.exporters.csv

Visualizers
-------------
.. automethod:: mimocorb2.functions.visualizers.csv
.. automethod:: mimocorb2.functions.visualizers.histogram

Analyzers
---------
.. automethod:: mimocorb2.functions.analyzers.pha

Data
------
.. automethod:: mimocorb2.functions.data.export
.. automethod:: mimocorb2.functions.data.simulate_importer
.. automethod:: mimocorb2.functions.data.clocked_importer

Misc
----
.. automethod:: mimocorb2.functions.misc.copy

Observers
---------
.. automethod:: mimocorb2.functions.observers.oscilloscope

Importers
---------
redpitaya
^^^^^^^^^^
.. automethod:: mimocorb2.functions.importers.redpitaya.waveform