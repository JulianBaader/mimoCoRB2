mimo_buffer
...........

The mimo_buffer is at the core of the mimoCoRB application.
It is designed as a circular buffer that can be accessed by multiple processes at the same time.
The buffer is devided into multiple slots. Each slot contains metadata and data.