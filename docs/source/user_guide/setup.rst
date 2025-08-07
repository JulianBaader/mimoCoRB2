Setup
=====

The setup file which is provided to the main script is a yaml file that defines the buffers and workers that will be used in the application.
It describes the buffers and the data flow between them.

.. code-block:: yaml

    Buffers:
        buffer_name_1:
            slot_count: int
            data_length: int 
            data_dtype:
                field_name_1: field_dtype_1
                ...
        ...

    Workers:
        worker_name_1:
            file: path_to_function_file
            function: function_name
            config: dict | str | [str | dict]
            number_of_processes: int
            sources: [str]
            sinks: [str]
            observes: [str]
        ...
    base_config: dict | str | [str | dict]
    target_directory: str   # Path to the target directory where the run will be stored.
                            # /path/to/target_directory -> absolute path
                            # path/to/target_directory -> relative path to the setup file
                            # ~/path/to/target_directory -> relative path to the user home directory


Slot Count
----------
The slot count is the number of slots that the buffer will have. Each slot can hold a data packet in the form of a numpy structured array.
It should be higher than the number of processes that will be using the buffer, as well as high enough to buffer a reasonable amount of data.

Data Length
-----------
The data is stored in the form of a numpy structured array of shape (data_lenght,).
It is therefore the number of elements per field in the data.

Data Dtype
-----------
The data type of the data stored in the buffer. It is a dictionary where the keys are the field names and the values are the field data types.
The field data types are the same as the numpy data types. For example, 'int32', 'float64', 'S10' (string of length 10), etc.

File
-----
This is the path (relative to the setup file) to the file that contains the function that will be used in the worker.
If the key is missing or empty, the prebuilt functions will be used.

Function
--------
The name of the function that will be used in the worker.
(TODO see prebuilt functions)

Config
------
The configuration of the worker. It can be a dictionary, a string or a list of strings.
If it is a dictionary, it will be passed directly to the worker.
If it is a string or a list of strings the yaml file at each path (relative to the setup file) will be loaded in the config dictionary (duplicate keys will be overwritten).

Number of Processes
-------------------
The number of processes run by the worker.

Sources, Sinks, Observes
--------------------------
The sources, sinks and observes of the worker. They are the names of the buffers that will be used by the worker.
Sources are the buffers that will be used to read data from, sinks are the buffers that will be used to write data to and observes are the buffers that will be used to observe data.
