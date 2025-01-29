# mimoCoRB2

## run examples
```python main.py <setup_file>```

To shutdown, try **Shutdown Root Buffer**. This will shutdown every buffer which has no function writing to it (i.e. the root buffers). Ideally this shutdown will triple down into every other buffer and shutdown the corresponding processes.

If still some processes are running, try **Shutdown All Buffers**.
As a last resort use **Kill Workers** which will terminate all remaining processes.

Exit is only cleanly possible when no processes are alive.
## Infrastructure
### Buffer Objects
Buffer Objects consit of two queues and a shared memory.
The shared memory is divided into multiple slots.
The queues contain indices to these slots which are handeld as tokens. In the beginning one queue (empty_slots) contains all tokens. By requesting one of those tokens one gains acces to the corresponding slot. After writing to this slot one returns the token to the other queue (filled_slots).

To cleanly handel this requesting and returning context managers (mimoBuffer.Reader, mimoBuffer.Writer, mimoBuffer.Observer) are available.

### Worker Objects
Worker Objects consit of a callable function and instances of the above mentioned context managers.

The worker can start multiple processes of the callable function which then has acces to the buffers.

### Worker Templates
There are some template classes provided (Importer, Exporter, Filter, Processor, Observer).

These can be used to simply define worker functions.

### Functions
Inside the functions folder predefined functions are available.


### Setup
A setup.yaml file is designed as follows
```yaml
# Define all Buffers
Buffers:
    buffer_name:
        slot_count: int
        data_length: int
        data_dtype:
            channel_name: str # 'f4'
            # ... more channels
        overwrite: bool # optional
    # ... more buffers

# Define all Workers
Workers:
    worker_name: # example for an user defined function
        file: str
        function: str
        sinks: [str] # optional
        sources: [str] # optional
        observes: [str] # optional
        number_of_processes: int # optional, default = 1
        config: [str] or {...} # optional, default = {}
    worker_name2:
        function: 'module_name.function' 
        # without the file key or with file: ""
        # the provided function will be used
        sinks: [str] # optional
        sources: [str] # optional
        observes: [str] # optional
        number_of_processes: int # optional, default = 1
        config: [str] or {...} # optional, default = {}


# the config can either be a list of config files 
# or a config dict directly

Options:
    output_directory: str # optional, default = 'target'
    debug_workers: bool # optional, default = False
    overarching_config: [str] or {...}
```
All file references are interpreted relative to the setup file.