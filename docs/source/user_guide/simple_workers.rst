Simple Workers
==============
Simple Workers can be built using the classes provided in the :py:module:`mimocorb2.worker_templates` module.


Importer
--------
Importers are used to import data from an external source into the mimocorb2 system.
They will automatically add the metadata to each event.

.. autoclass:: mimocorb2.worker_templates.Importer
    :members: __init__, __call__

Exporter
--------
Exporters are used to export data from the mimocorb2 system.

.. autoclass:: mimocorb2.worker_templates.Exporter
    :members: __init__, __call__

Filter
------
Filters are used to filter data. This means that the data is not modified, but some of the data is removed.

.. autoclass:: mimocorb2.worker_templates.Filter
    :members: __init__, __call__

Processor
---------
Processors are used to process data. This means that the data is modified in some way.

.. autoclass:: mimocorb2.worker_templates.Processor
    :members: __init__, __call__

Observer
--------
Observers are used to observe data. This means that a copy of the data is exported.

.. autoclass:: mimocorb2.worker_templates.Observer
    :members: __init__, __call__
