Simple Workers
==============
Simple Workers can be built using the classes provided in the :py:module:`mimocorb2.worker_templates` module.

In order to document your workers, you can use the following docstring format:

.. literalinclude:: ../../../mimocorb2/functions/doc_template.py
   :language: python
   :lines: 1-
   :caption: mimoCoRB2 docstring template


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
    :members: __init__, __iter__

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

IsAlive
----------
IsAlive workers are used to check if the system or a specific buffer is still alive.

.. autoclass:: mimocorb2.worker_templates.IsAlive
    :members: __init__, __call__
