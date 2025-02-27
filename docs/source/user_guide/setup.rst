Setup
=====

A setup file is used to define the buffers and workers of the application. It is written in yaml format and divided into three sections.

Buffers
-------
.. code-block:: yaml
buffer_name:
    slot_count: int
    data_length: int
    data_dtype:
        field_name1: dtype1
        field_name2: dtype2
        ...
    

Workers
-------
.. code-block:: yaml
worker_name:
    function: str
    file: str
    number_of_processes: int
    sinks: list[str]
    sources: list[str]
    observes: list[str]