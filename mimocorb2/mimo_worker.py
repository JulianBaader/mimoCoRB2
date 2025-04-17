import multiprocessing
import logging
from typing import Callable
import os
import sys
from mimocorb2.mimo_buffer import BufferReader, BufferWriter, BufferObserver

FUNCTIONS_FOLDER = os.path.join(os.path.dirname(__file__), 'functions')
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
            
    def __str__(self):
        """String representation of the BufferIO object."""
        read = [buffer.name for buffer in self.read]
        write = [buffer.name for buffer in self.write]
        observe = [buffer.name for buffer in self.observe]
        config = self.config
        return f"BufferIO(sources={read}, sinks={write}, observes={observe}, config={config})"

            
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
            process = multiprocessing.Process(target=self.function, args=(self.buffer_io,), name=f'{self.name}_{i}')
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
                
    def __str__(self):
        """String representation of the mimoWorker object."""
        return f"mimoWorker(name={self.name}, function={self.function.__name__}, buffer_io={str(self.buffer_io)}, number_of_processes={self.number_of_processes})"
    

    @classmethod
    def from_setup(cls, name: str, setup: dict, path: str, buffers: dict):
        """Initiate the Worker from a setup dict"""
        function_name = setup['function'].split('.')[-1]
        file = setup.get('file')
        if not file:
            file = os.path.join(FUNCTIONS_FOLDER, setup['function'].split('.')[0] + '.py')
        else:
            file = os.path.join(path, file)
        
        return cls(
            name = name,
            function = cls._import_function(file, function_name),
            buffer_io = BufferIO(
                sources = [BufferReader(buffers[name]) for name in setup.get('sources', [])],
                sinks = [BufferWriter(buffers[name]) for name in setup.get('sinks', [])],
                observes = [BufferObserver(buffers[name]) for name in setup.get('observes', [])],
                config = Config.from_setup(setup.get('config', {}), path=path),
            ),
            number_of_processes = setup.get('number_of_processes', 1),
        )
        
    @staticmethod        
    def _import_function(file: str, function_name: str) -> Callable:
        """Import a function from a file and return it."""
        directory = os.path.dirname(file)
        module_name = os.path.basename(file).removesuffix('.py')

        if directory not in sys.path:
            sys.path.append(directory)
            module = __import__(module_name, globals(), locals(), fromlist=[function_name])
            sys.path.remove(directory)
        else:
            module = __import__(module_name, globals(), locals(), fromlist=[function_name])
        if function_name not in vars(module):
            raise ImportError(f"Function {function_name} not found in module {file}")
        return vars(module)[function_name]
            