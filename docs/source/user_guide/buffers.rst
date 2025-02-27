Buffers
=======

Buffers are at the core of mimoCoRB2. 
Each buffer is defined by

* name
* slot_count
* data_length
* data_dtype 

Each buffer is divided into slots, where each slot holds data and metadata.
Data is a numpy structured array of shape (data_length,) and dtype data_dtype.
Metadata is a numpy structured array of shape (1,) and dtype metadata_dtype.

.. autoattribute:: mimocorb2.mimo_buffer.mimoBuffer.metadata_dtype

Buffers are implemented in a multiprocessing safe way using shared memory.
This means multiple processes can read and write to the same buffer at the same time without any issues. 