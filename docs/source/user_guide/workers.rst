Workers
=======

Workers are used for interactions between buffers.

A worker is defined by

* name
* function
* args
* number_of_processes

The name is used as an identifier for the worker. The function is the function that the worker will run with the provided args.
The number_of_processes is the number of processes that the worker will run.