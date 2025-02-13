from mimocorb2.mimo_buffer import mimoBuffer, BufferReader, BufferWriter, BufferObserver
from mimocorb2.mimo_worker import mimoWorker

import os
import yaml
import logging
import numpy as np
import sys
import time

from graphviz import Digraph
from typing import Callable, Any

#STANDARD_OVERWRITE = True
FUNCTIONS_FOLDER = os.path.join(os.path.dirname(__file__), 'functions')


BUFFERS = {
    'slot_count': None,
    'data_length': None,
    'data_dtype': None,
  #  'overwrite': STANDARD_OVERWRITE,
}

WORKERS = {
    'function': None,
    'file': "",
    'config': [],
    'number_of_processes': 1,
    'sinks': [],
    'sources': [],
    'observes': [],
}

OPTIONS = {
    'output_directory': 'target',
    'debug_workers': False,
    'overarching_config': [],
    # 'setup_dir': None,  # added in FileReader
    # 'run_directory': None,  # added in SetupRun
}

# TODO This has to be made much more clear, i had a headache fixing this
# TODO maybe add a check somewhere, that sources are always BufferReader and so on
BUFFER_TYPES = ['sources', 'sinks', 'observes']
INTERFACE_TYPES = [BufferReader, BufferWriter, BufferObserver]


class SetupError(Exception):
    """Exception raised for errors in the setup process."""

    pass


class FileReader:
    """
    Reads and normalizes a provided YAML setup file defining buffers, workers and options.

    The setup file must be constructed as follows (yaml syntax):

    Buffers:
        buffer_name:
            slot_count: int
            data_length: int
            data_dtype:
                name: dtype
                ...
            #overwrite: bool (optional, default: True)
        ...

    Workers:
        worker_name:
            function: str
            file: str (optional, default: "")
            config: str | list[str] | dict (optional, default: [])
            number_of_processes: int
            sinks: list[str]
            sources: list[str]
            observes: list[str]
        ...

    Options:
        output_directory: str (optional, default: 'target')
        debug_workers: bool (optional, default: False)
        overarching_config: str | list[str] | dict (optional, default: [])


    Configs provided as strings or lists of strings are interpreted as paths to yaml files.
    Configs provided as a dictionary are used as is.

    When file is not provided, the function is assumed to be a built-in function.

    During normalisation each missing optional key is replaced with its default value.
    """

    def __init__(self, setup_file: str) -> None:
        self.setup_file = os.path.abspath(setup_file)
        self.setup_dir = os.path.dirname(self.setup_file)

        self.logger = logging.getLogger(__name__)

    def __call__(self) -> tuple[dict, str]:
        """Return the normalized setup"""
        buffers, workers, options = self.load_setup()
        norm_buffers = {
            name: self.normalize_section('Buffer: ' + name, data, BUFFERS) for name, data in buffers.items()
        }
        norm_workers = {
            name: self.normalize_section('Worker: ' + name, data, WORKERS) for name, data in workers.items()
        }

        norm_options = self.normalize_section('Options', options, OPTIONS)
        norm_options['setup_dir'] = self.setup_dir

        return {
            'Buffers': norm_buffers,
            'Workers': norm_workers,
            'Options': norm_options,
        }

    def load_setup(self) -> tuple[dict, dict, dict]:
        with open(self.setup_file, 'r') as f:
            setup = yaml.safe_load(f)

        if 'Options' not in setup:
            self.logger.debug('No Options section in setup file, defaulting to {}')
        options = setup.get('Options', {})
        if 'Buffers' not in setup:
            raise SetupError('No Buffers section in setup file')
        buffers = setup['Buffers']
        if 'Workers' not in setup:
            raise SetupError('No Workers section in setup file')
        workers = setup['Workers']

        return buffers, workers, options

    def normalize_section(self, section_name: str, section_data: dict, defaults: dict) -> dict:
        """
        Normalizes a section from the setup file, ensuring required keys are present.

        Parameters
        ----------
        section_name : str
            The name of the section (e.g., "Buffer: buffer_name" or "Worker: worker_name") for error messages.
        section_data : dict
            The dictionary containing the section data from the setup file.
        defaults : dict
            The dictionary of required and optional keys with their default values.
            None as default value means the key is required.

        Returns
        -------
        dict
            The normalized section data.
        """
        if not isinstance(section_data, dict):
            raise SetupError(f"{section_name} section is not a dictionary")

        normalized = {}
        for parameter, value in defaults.items():
            if parameter not in section_data and value is None:
                raise SetupError(f"{section_name} is missing the required {parameter} key.")
            if parameter not in section_data:
                self.logger.debug(f"{section_name} is missing the optional {parameter} key. Defaulting to {value}.")
            normalized[parameter] = section_data.get(parameter, value)
        return normalized

    def visualize_setup(self, file, **digraph_kwargs) -> None:
        """Creates a Graphviz visualization of the setup and saves it as an SVG file."""
        normalized_setup = self()
        dot = Digraph(format='svg', **digraph_kwargs)

        for buffer_name in normalized_setup['Buffers'].keys():
            dot.node('B' + buffer_name, label=buffer_name)
        for worker_name in normalized_setup['Workers'].keys():
            dot.node('F' + worker_name, shape='box', label=worker_name)

        for worker_name, worker_data in normalized_setup['Workers'].items():
            for source in worker_data['sources']:
                if source in normalized_setup['Buffers']:
                    dot.edge('B' + source, 'F' + worker_name)
                else:
                    raise SetupError(f"Worker {worker_name} references unknown source {source}")
            for sink in worker_data['sinks']:
                if sink in normalized_setup['Buffers']:
                    dot.edge('F' + worker_name, 'B' + sink)
                else:
                    raise SetupError(f"Worker {worker_name} references unknown sink {sink}")
            for observe in worker_data['observes']:
                if observe in normalized_setup['Buffers']:
                    dot.edge('B' + observe, 'F' + worker_name, style='dotted')
                else:
                    raise SetupError(f"Worker {worker_name} references unknown observe {observe}")

        dot.render(file, cleanup=True)


class SetupRun:
    """Processes and initializes the setup configuration, creating buffers and workers."""

    def __init__(self, normalized_setup: dict) -> None:
        self.setup = normalized_setup

        self.configs_are_dict = False
        self.functions_are_callable = False
        self.buffer_objects_created = False
        self.args_made = False
        self.workers_created = False

    def __call__(self) -> dict:
        """Execute the setup processes and return the initialized setup."""
        self.setup_run_directory()
        self.replace_configs()
        self.dump_setup()
        self.add_callable_functions()
        self.create_buffers()
        self.make_args()
        self.create_workers()

        return self.setup

    def setup_run_directory(self) -> None:
        """Setup the directory for the run output."""
        output_directory = os.path.join(self.setup['Options']['setup_dir'], self.setup['Options']['output_directory'])
        os.makedirs(output_directory, exist_ok=True)
        start_time = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.run_directory = os.path.join(output_directory, 'run' + '_' + start_time)
        os.makedirs(self.run_directory, exist_ok=False)
        self.run_directory = os.path.abspath(self.run_directory)
        self.setup['Options']['run_directory'] = self.run_directory

    # ---> config handeling
    def replace_configs(self) -> None:
        """Replace every config entry with the correct config dictionary."""
        overarching_config = self._ensure_config_dict("OVERARCHING", self.setup['Options']['overarching_config'])

        for name, info in self.setup['Workers'].items():
            config = overarching_config.copy()
            worker_config = self._ensure_config_dict(name, info['config'])
            shared_keys = list(config.keys() & worker_config.keys())
            if shared_keys:
                self.logger.debug(f"Worker {name} overwrites keys {shared_keys} of the overarching config.")
            config.update(worker_config)

            obligatory_config = {
                'name': name,
                'debug': self.setup['Options']['debug_workers'],
                'run_directory': self.run_directory,
            }
            shared_keys = list(config.keys() & obligatory_config.keys())
            if shared_keys:
                self.logger.debug(f"Worker {name} overwrites keys {shared_keys} of the obligatory config.")
            config.update(obligatory_config)
            info['config'] = config.copy()

        self.configs_are_dict = True

    def _ensure_config_dict(self, worker_name: str, worker_config: str | list[str] | dict) -> dict:
        """Converts a config entry to a dictionary if it is not already."""
        if isinstance(worker_config, dict):
            return worker_config
        elif isinstance(worker_config, str):
            worker_config = [worker_config]
        return self._config_files_to_dict(worker_name, worker_config)

    def _config_files_to_dict(self, worker_name: str, config_files: list[str]) -> dict:
        """Converts a list of config file paths to a dictionary."""
        config = {}
        for file in config_files:
            config_from_file = self._load_config_from_file(worker_name, file)
            for key, value in config_from_file.items():
                if key in config:
                    self.logger.warning(
                        f"Worker {worker_name} overwrites key {key} with the value from config file {file}"
                    )
                config[key] = value
        return config

    def _load_config_from_file(self, worker_name: str, file: str) -> dict:
        """Loads a config file and returns its content as a dictionary."""
        file = os.path.join(self.setup['Options']['setup_dir'], file)
        if not os.path.isfile(file):
            raise SetupError(f"Config file {file} of worker {worker_name} does not exist.")
        with open(file, 'r') as stream:
            config = yaml.safe_load(stream)  # empty file returns None
        if config is None:
            return {}
        else:
            return config

    # <--- config handeling

    def dump_setup(self) -> None:
        """Dump the setup to a yaml file in the run directory."""
        if not self.configs_are_dict:
            self.replace_configs()
        with open(os.path.join(self.run_directory, 'setup.yaml'), 'w') as file:
            yaml.dump(self.setup, file)

    # ---> function handeling
    def add_callable_functions(self) -> None:
        """Add the callable functions to the setup."""
        for name, info in self.setup['Workers'].items():
            file = info['file']
            function = info['function']

            if file == "":
                # use built-in functions
                split = function.split('.')
                if len(split) < 2:
                    raise SetupError(f"Function {function} of worker {name} is not a valid mimoCoRB2 function.")
                function = split.pop()
                module_name = split.pop() + '.py'
                file = os.path.join(FUNCTIONS_FOLDER, *split, module_name)
            else:
                # use function relative to setup file
                file = os.path.join(self.setup['Options']['setup_dir'], file)

            if not os.path.isfile(file):
                raise SetupError(f"File {file} of worker {name} does not exist.")

            info['callable_function'] = self._import_function_from_file(file, function)

        self.functions_are_callable = True

    def _import_function_from_file(self, file: str, function_name: str) -> Callable:
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

    # <--- function handeling

    # ---> buffer handeling
    def create_buffers(self) -> None:
        """Create the mimo_buffer objects."""
        for name, info in self.setup['Buffers'].items():
            if not self._is_whole(info['slot_count']):
                raise SetupError(f"Buffer {name} slot_count must be a positive integer.")
            if not self._is_whole(info['data_length']):
                raise SetupError(f"Buffer {name} data_length must be a positive integer.")
            info['data_dtype_obj'] = self._interpret_dtype(name, info['data_dtype'])
            #info['overwrite'] = bool(info['overwrite'])
            info['buffer_obj'] = mimoBuffer(
                name=name,
                slot_count=info['slot_count'],
                data_length=info['data_length'],
                data_dtype=info['data_dtype_obj'],
                #overwrite=info['overwrite'],
            )
        self.buffer_objects_created = True

    def _interpret_dtype(self, buffer_name: str, dtype_setup: dict) -> np.dtype:
        """Interpret thy dtype setup and return a numpy dtype."""
        try:
            return np.dtype([(name, dtype) for name, dtype in dtype_setup.items()])
        except (TypeError, ValueError):
            raise SetupError(f"Buffer {buffer_name} data_dtype {dtype_setup} can not be interpreted as a numpy dtype.")

    # <--- buffer handeling

    # ---> worker handeling
    def make_args(self) -> None:
        """Generate the arguments for the workers. args = [sources, sinks, observes, config]"""
        if not self.buffer_objects_created:
            self.create_buffers()
        if not self.configs_are_dict:
            self.replace_configs()

        for name, info in self.setup['Workers'].items():
            # args = [sources, sinks, observes, config]
            args = [[], [], [], None]
            for i in range(3):  # sources, sinks, observes
                args[i] = self._make_interface_list(name, info[BUFFER_TYPES[i]], i)
            args[3] = info['config']
            info['args'] = args
        self.args_made = True

    def _make_interface_list(
        self, worker_name: str, buffer_list: list[str], arg_index: int
    ) -> list[BufferReader | BufferWriter | BufferObserver]:
        """Create a list of buffer interfaces for a worker."""
        interface_list = []
        for buffer_name in buffer_list:
            if buffer_name not in self.setup['Buffers']:
                raise SetupError(f"Worker {worker_name} references unknown {BUFFER_TYPES[arg_index]} {buffer_name}")
            interface_list.append(INTERFACE_TYPES[arg_index](self.setup['Buffers'][buffer_name]['buffer_obj']))
        return interface_list

    def create_workers(self) -> None:
        """Create the mimo_worker objects."""
        if not self.functions_are_callable:
            self.add_callable_functions()
        if not self.args_made:
            self.make_args()

        for name, info in self.setup['Workers'].items():
            if not self._is_whole(info['number_of_processes']):
                raise SetupError(f"Worker {name} number_of_processes must be a positive integer.")
            info['worker_obj'] = mimoWorker(
                name=name,
                function=info['callable_function'],
                args=info['args'],
                number_of_processes=info['number_of_processes'],
            )
        self.workers_created = True

    @staticmethod
    def _is_whole(value: Any) -> bool:
        """Check if a value is a positive integer."""
        return isinstance(value, int) and value > 0


class Control:
    def __init__(self, initialized_setup: dict) -> None:
        self.setup = initialized_setup
        self.logger = logging.getLogger(__name__)
        self.find_buffers_for_clean_shutdown()

        self.total_processes = sum([info['number_of_processes'] for info in self.setup['Workers'].values()])

    def find_buffers_for_clean_shutdown(self) -> None:
        """Find all buffers that do not have any sources or observes and add them to the shutdown list."""
        buffers = []
        for name, info in self.setup['Workers'].items():
            if len(info['sources']) == 0 and len(info['observes']) == 0:
                buffers.extend(info['sinks'])
        self.buffers_for_shutdown = buffers

    def clean_shutdown(self) -> None:
        """Shut down all buffers that do not have any sources or observes."""
        for name in self.buffers_for_shutdown:
            self.logger.info(f"Shutting down buffer {name}")
            self.setup['Buffers'][name]['buffer_obj'].send_flush_event()

    def hard_shutdown(self) -> None:
        """Shut down all buffers."""
        for name, info in self.setup['Buffers'].items():
            self.logger.info(f"Shutting down buffer {name}")
            info['buffer_obj'].send_flush_event()

    def get_buffer_stats(self) -> dict:
        """Get the statistics of all buffers."""
        stats = {}
        current_time = time.time()
        for name, info in self.setup['Buffers'].items():
            stats[name] = info['buffer_obj'].get_stats()
        self.last_stats_time = current_time
        return stats

    def get_active_workers(self) -> dict:
        """Get the number of active processes for each worker."""
        active = {}
        for name, info in self.setup['Workers'].items():
            active[name] = sum(info['worker_obj'].alive_processes())
        return active

    def kill_workers(self) -> None:
        """Kill all workers."""
        for name, info in self.setup['Workers'].items():
            self.logger.info(f"Shutting down worker {name}")
            info['worker_obj'].shutdown()

    def start_workers(self) -> None:
        """Initialize and start all workers."""
        for name, info in self.setup['Workers'].items():
            self.logger.info(f"Initalizing processes for worker {name}")
            info['worker_obj'].initialize_processes()
        self.start_time = time.time()
        self.last_stats_time = self.start_time
        for name, info in self.setup['Workers'].items():
            self.logger.info(f"Starting processes for worker {name}")
            info['worker_obj'].start_processes()

    def get_time_active(self) -> float:
        """Return the time the workers have been active."""
        return time.time() - self.start_time
