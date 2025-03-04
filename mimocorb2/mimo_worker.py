import multiprocessing
import logging
from typing import Callable
from mimocorb2.mimo_buffer import BufferReader, BufferWriter, BufferObserver

SOURCES = 0
SINKS = 1
OBSERVES = 2
CONFIG = 3


class BufferIO:
    """Collection of buffers for input/output operations.
    
    Object which is passed to each worker process to provide access to the buffers.
    
    Attributes
    ----------
    sources : list[BufferReader]
    sinks : list[BufferWriter]
    observes : list[BufferObserver]
    config : dict
    logger : logging.Logger
    
    Methods
    -------
    shutdown_sinks()
        Shutdown all sink buffers.
    __getitem__(key)
        Get the value of a key from the configuration dictionary.
    
    Examples
    --------
    >>> with io.write[0] as (metadata, data):
    """
    def __init__(self, sources: list[BufferReader], sinks: list[BufferWriter], observes: list[BufferObserver], config: dict) -> None:
        self.read = sources
        self.write = sinks
        self.observe = observes
        self.config = config
        self.logger = logging.getLogger(name=config['name'])
        
    def shutdown_sinks(self) -> None:
        for writer in self.write:
            writer.shutdown_buffer()

            
    def __getitem__(self, key):
        return self.config[key]
    
    
        

class mimoWorker:
    """
    Worker class for the execution of (muliple instances of) function interacting with mimoBuffers.

    Parameters
    ----------
    name : str
        A unique name for the worker group.
    function : Callable
        The function to be executed by each process.
    args : list[list, list, list, dict]
        A list containing four elements:
        - List of source buffers (SOURCES)
        - List of sink buffers (SINKS)
        - List of observe buffers (OBSERVES)
        - Configuration dictionary (CONFIG)
    number_of_processes : int
        The number of processes to spawn.

    Attributes
    ----------
    name : str
        The name of the worker group.
    function : Callable
        The function executed by each process.
    args : list[list, list, list, dict]
        Arguments passed to each process.
    number_of_processes : int
        The number of processes to spawn.
    logger : logging.Logger
        Logger for tracking process activity.
    processes : list[multiprocessing.Process]
        A list of managed worker processes.

    Methods
    -------
    initialize_processes()
        Initializes worker processes but does not start them.
    start_processes()
        Starts all initialized worker processes.
    alive_processes() -> list[bool]
        Returns a list indicating the status of each process (True if alive, False otherwise).
    shutdown()
        Terminates all active worker processes.
    """

    def __init__(
        self, name: str, function: Callable, buffer_io: BufferIO, number_of_processes: int
    ) -> None:
        self.name = name
        self.function = function
        self.buffer_io = buffer_io
        self.number_of_processes = number_of_processes

        self.logger = logging.getLogger(name=name)
        self.processes = []

    def initialize_processes(self) -> None:
        """Initialize worker processes."""
        if len(self.processes) > 0:
            raise RuntimeError("Processes already initialized")
        for i in range(self.number_of_processes):
            process = multiprocessing.Process(target=self.function, args=[self.buffer_io], name=f'{self.name}_{i}')
            self.processes.append(process)

    def start_processes(self) -> None:
        """Start worker processes."""
        for process in self.processes:
            process.start()

    def alive_processes(self) -> list[bool]:
        """Checks which processes are still alive."""
        return [p.is_alive() for p in self.processes]

    def shutdown(self) -> None:
        """Shutdown worker processes."""
        for p in self.processes:
            if p.is_alive():
                self.logger.info(f"Killing process {p.name}")
                p.terminate()
