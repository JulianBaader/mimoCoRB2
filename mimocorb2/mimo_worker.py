import multiprocessing
import io
import logging
from typing import Callable
import os
import sys
import yaml
from mimocorb2.mimo_buffer import BufferReader, BufferWriter, BufferObserver

FUNCTIONS_FOLDER = os.path.join(os.path.dirname(__file__), 'functions')

logger = logging.getLogger(__name__)


class Config(dict):
    """Configuration of the mimoWorker

    A dictionary-like object that holds the configuration for the mimoWorker.

    Attributes
    ----------
    config_dict : dict
        A dictionary containing the configuration parameters.

    Methods
    -------
    from_setup(setup: str | dict | list, setup_dir: str)
        Load the configuration from a setup.
    """

    def __init__(self, config_dict):
        super().__init__(config_dict)

    @classmethod
    def from_setup(cls, setup: str | dict | list[str], setup_dir: str):
        """Load the configuration from a setup.

        Parameters
        ----------
        setup : str | dict | list[str]
            If a string or a list of strings is provided, the yaml files relative to the setup_dir are loaded.
            If a dictionary is provided, it is used as the configuration directly.
        setup_dir : str
            The directory where the setup file is located.

        Returns
        -------
        Config
            An instance of the Config class containing the loaded configuration.
        """
        if isinstance(setup, str):
            with open(os.path.join(setup_dir, setup), 'r') as file:
                config = yaml.safe_load(file)
        elif isinstance(setup, dict):
            config = setup
        elif isinstance(setup, list):
            config = {}
            for item in setup:
                if isinstance(item, str):
                    with open(os.path.join(setup_dir, item), 'r') as file:
                        config.update(yaml.safe_load(file))
                elif isinstance(item, dict):
                    config.update(item)
        else:
            raise TypeError("setup must be a string, dict, or list of strings/dicts")

        return cls(config)


class BufferIO:
    """Collection of buffers for input/output operations.

    Object which is passed to each worker process to provide access to the buffers.

    Attributes
    ----------
    name : str
        The name of the corresponding worker.
    sources : list[BufferReader]
        List of source buffers (read).
    sinks : list[BufferWriter]
        List of sink buffers (write).
    observes : list[BufferObserver]
        List of observe buffers.
    config : Config
        Configuration dictionary for the worker.
    setup_directory : str
        Directory where the setup file is located. (Load external data)
    run_directory : str
        Directory where the run is located. (Save external data)
    logger : logging.Logger

    Methods
    -------
    shutdown_sinks()
        Shutdown all sink buffers.
    __getitem__(key)
        Get the value of a key from the configuration dictionary.
    __str__()
        String representation of the BufferIO object.
    from_setup(name, setup, setup_dir, run_dir, buffers)
        Create a BufferIO object from a setup dictionary.

    Examples
    --------
    >>> with io.write[0] as (metadata, data):
    ...     # write data and metadata to the buffer
    ...     pass
    >>> with io.read[0] as (metadata, data):
    ...     # read data and metadata from the buffer
    ...     pass
    >>> with io.observe[0] as (metadata, data):
    ...     # observe data and metadata from the buffer
    ...     pass
    >>> io.shutdown_sinks()  # Shutdown all sink buffers
    """

    def __init__(
        self,
        name: str,
        sources: list[BufferReader],
        sinks: list[BufferWriter],
        observes: list[BufferObserver],
        config: Config,
        setup_directory: str,
        run_directory: str,
    ) -> None:
        self.name = name
        self.read = sources
        self.write = sinks
        self.observe = observes
        self.config = config
        self.logger = logging.getLogger(name=f'{__name__}.{self.name}')
        self.setup_directory = setup_directory
        self.run_directory = run_directory

    def shutdown_sinks(self) -> None:
        """Shutdown all sink buffers."""
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
        if key not in self.config:
            self.shutdown_sinks()
            self.logger.error(f"Key '{key}' not found in provided configuration.")
            raise KeyError(f"Key '{key}' not found in configuration of {self.name}.")
        return self.config[key]

    @classmethod
    def from_setup(cls, name, setup: dict, setup_dir: str, run_dir: str, buffers: dict):
        """Initiate the BufferIO from a setup dictionary."""
        sources = [BufferReader(buffers[name]) for name in setup.get('sources', [])]
        sinks = [BufferWriter(buffers[name]) for name in setup.get('sinks', [])]
        observes = [BufferObserver(buffers[name]) for name in setup.get('observes', [])]
        config = Config.from_setup(setup.get('config', {}), setup_dir)

        return cls(
            name=name,
            sources=sources,
            sinks=sinks,
            observes=observes,
            config=config,
            setup_directory=setup_dir,
            run_directory=run_dir,
        )


class mimoWorker:
    """Worker class for the execution of (muliple instances of) a function interacting with mimoBuffers.
    
    This class manages multiple instances of a function using multiprocessing.
    The function is provided the BufferIO object, which contains the (multiprocessing safe) buffers for input/output operations.
    Any print statements executed in the function are redirected to a multiprocessing queue for later retrieval.

    Parameters
    ----------
    name : str
        A unique name for the worker group.
    function : Callable
        The function to be executed by each process.
    buffer_io : BufferIO
        An instance of BufferIO containing the buffers for input/output operations.
    number_of_processes : int
        The number of processes to spawn.
    print_queue : multiprocessing.Queue
        A queue for capturing print output from the worker processes.

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
    __str__()
        Returns a string representation of the mimoWorker object.
    from_setup(name, setup, setup_dir, run_dir, buffers, print_queue)
        Class method to create a mimoWorker instance from a setup dictionary.
    """

    def __init__(
        self,
        name: str,
        function: Callable,
        buffer_io: BufferIO,
        number_of_processes: int,
        print_queue: multiprocessing.Queue,
    ) -> None:
        self.name = name
        self.function = function
        self.buffer_io = buffer_io
        self.number_of_processes = number_of_processes
        self.print_queue = print_queue

        logger.info(f"Creating mimoWorker: {str(self)}")
        self.logger = logging.getLogger(f'{__name__}.{self.name}')
        self.processes = []

    def initialize_processes(self) -> None:
        """Initialize worker processes."""
        if len(self.processes) > 0:
            raise RuntimeError("Processes already initialized")
        for i in range(self.number_of_processes):

            def redirected_stdout(buffer_io: BufferIO):
                """Redirect stdout to a buffer."""
                sys.stdout = QueueWriter(self.print_queue, self.name)
                #sys.stderr = QueueWriter(self.print_queue, self.name)
                self.function(buffer_io)

            process = multiprocessing.Process(target=redirected_stdout, args=(self.buffer_io,), name=f'{self.name}_{i}')
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
    def from_setup(
        cls, name: str, setup: dict, setup_dir: str, run_dir, buffers: dict, print_queue: multiprocessing.Queue
    ) -> 'mimoWorker':
        """Initiate the Worker from a setup dictionary.

        This method creates an instance of mimoWorker from a setup dictionary.
        This is required to ensure that the function is imported correctly and the BufferIO is set up with the correct buffers.
        
        Parameters
        ----------
        name : str
            A unique name for the worker group.
        setup : dict
            A dictionary containing the setup configuration.
        setup_dir : str
            The directory where the setup file is located.
        run_dir : str
            The directory where the run is located.
        buffers : dict
            A dictionary containing the buffers of the current run.
        print_queue : multiprocessing.Queue
            A queue for capturing print output from the worker processes.
            
        Returns
        -------
        mimoWorker
            An instance of the mimoWorker class initialized with the provided setup.
        """
        function_name = setup['function'].split('.')[-1]
        file = setup.get('file')
        if not file:
            file = os.path.join(FUNCTIONS_FOLDER, setup['function'].split('.')[0] + '.py')
        else:
            file = os.path.join(setup_dir, file)

        return cls(
            name=name,
            function=cls._import_function(file, function_name),
            buffer_io=BufferIO.from_setup(
                name=name,
                setup=setup,
                setup_dir=setup_dir,
                run_dir=run_dir,
                buffers=buffers,
            ),
            number_of_processes=setup.get('number_of_processes', 1),
            print_queue=print_queue,
        )

    @staticmethod
    def _import_function(file: str, function_name: str) -> Callable:
        """Import a function from a file and return it as a callable."""
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


class QueueWriter(io.TextIOBase):
    """A class to write to a multiprocessing queue, redirecting stdout/stderr.
    
    This class is used to capture print statements from worker processes and send them to a queue.
    
    Parameters
    ----------
    queue : multiprocessing.Queue
        The queue to which the messages will be sent.
    name : str
        The name of the worker process, used to identify the source of the messages.
    """
    def __init__(self, queue, name):
        """Initialize the QueueWriter with a queue and a name."""
        self.queue = queue
        self.name = name

    def write(self, msg):
        """Write a message to the queue."""
        if msg.strip():  # Avoid blank lines
            self.queue.put((self.name, msg))

    def flush(self):
        pass
