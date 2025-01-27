from mimocorb2.mimo_buffer import mimoBuffer, BufferReader, BufferWriter, BufferObserver
from mimocorb2.mimo_worker import mimoWorker

import os
import yaml
import logging
import numpy as np
import sys
import shutil
import time

STANDARD_OVERWRITE = True
FUNCTIONS_FOLDER = os.path.join(os.path.dirname(__file__), 'functions')


BUFFERS = {
    'slot_count': None,
    'data_length': None,
    'data_dtype': None,
    'overwrite': STANDARD_OVERWRITE,
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
}

BUFFER_TYPES = ['sinks', 'sources', 'observes']





class SetupError(Exception):
    pass

class FileReader:
    def __init__(self, setup_file):
        self.setup_file = os.path.abspath(setup_file)
        self.setup_dir = os.path.dirname(self.setup_file)

        self.logger = logging.getLogger(__name__)
        
    def __call__(self):
        buffers, workers, options = self.load_setup()
        norm_buffers = {name: self.normalize_section('Buffer: ' + name, data, BUFFERS) for name, data in buffers}
        norm_workers = {name: self.normalize_section('Worker: ' + name, data, WORKERS) for name, data in workers}
        
        norm_options = self.normalize_section('Options', options, OPTIONS)

        
        return {
            'Buffers': norm_buffers, 
            'Workers': norm_workers, 
            'Options': norm_options,
        }
            
        
    def load_setup(self):
        with open(self.setup_file, 'r') as f:
            setup = yaml.safe_load(f)
            
        if 'Options' not in setup:
            self.logger.debug('No Options section in setup file, defaulting to \{\}')
        options = setup.get('Options', {})
        if 'Buffers' not in setup:
            raise SetupError('No Buffers section in setup file')
        buffers = setup['Buffers']
        if 'Workers' not in setup:
            raise SetupError('No Workers section in setup file')
        workers = setup['Workers']
        
        return buffers, workers, options

        
        
    def normalize_section(self, section_name, section_data, defaults):
        """
        Normalize a section from the setup file (e.g., buffers or workers).

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
    

class SetupRun:
    """
    
    This class assumes the setup provided is normalized in the following way.
    setup = {
        'Buffers': {buffer_name: BUFFERS, ...}
        'Workers': {worker_name: WORKERS, ...}
        'Options': OPTIONS
    }
    """
    def __init__(self, setup):
        self.setup = setup
        
        self.configs_are_dict = False
        self.functions_are_callable = False
        self.buffer_objects_created = False
        
        
    def setup_run_directory(self):
        output_directory = self.setup['Options']['output_directory']
        os.makedirs(output_directory, exist_ok=True)
        start_time = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.run_directory = os.path.join(output_directory, 'run' + '_' + start_time)
        os.makedirs(self.run_directory, exist_ok=False)
        
    
    
    # ---> config handeling
    def replace_configs(self):
        overarching_config = self._ensure_config_dict(self.setup['Options']['overarching_config'])
        
        for name, info in self.setup['Workers'].items():
            config = overarching_config.copy()
            worker_config = self._ensure_config_dict(name, info['config'])            
            shared_keys = list(config.keys() & worker_config.keys())
            if shared_keys:
                self.logger.debug(f"Worker {name} overwrites keys {shared_keys} of the overarching config.")
            config.update(worker_config)
            info['config'] = config
            
        self.configs_are_dict = True
            
    def _ensure_config_dict(self, worker_name: str, worker_config: str | list[str] | dict) -> dict:
        if isinstance(worker_config, dict):
            return worker_config
        elif isinstance(worker_config, str):
            worker_config = [worker_config]
        return self._config_files_to_dict(worker_name, worker_config)    
        
    def _config_files_to_dict(self, worker_name: str, config_files: list[str]) -> dict:
        config = {}
        for file in config_files:
            config_from_file = self._load_config_from_file(worker_name, file)
            for key, value in config_from_file.items():
                if key in config:
                    self.logger.warning(f"Worker {worker_name} overwrites key {key} with the value from config file {file}")
                config[key] = value
        return config
    
    def _load_config_from_file(self, worker_name, file):
        file = os.path.join(self.setup_dir, file)
        if not os.path.isfile(file):
            raise SetupError(f"Config file {file} of worker {worker_name} does not exist.")
        with open(file, 'r') as stream:
            config = yaml.safe_load(stream) # empty file returns None
        if config is None:
            return {}
        else:
            return config
    
        
    # <--- config handeling
    
    def dump_setup(self):
        if not self.configs_are_dict:
            self.replace_configs()
        with open(os.path.join(self.run_directory, 'setup.yaml'), 'w') as file:
            yaml.dump(self.setup, file)

    # ---> function handeling
    def add_callable_functions(self):
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
                file = os.path.join(self.setup_dir, file)
            
            if not os.path.isfile(file):
                raise SetupError(f"File {file} of worker {name} does not exist.")
            
            info['callable_function'] = self._import_function_from_file(file, function)
            
        self.functions_are_callable = True

    def _import_function_from_file(file, function_name):
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
    def create_buffers(self):
        for name, info in self.setup['Buffers'].items():
            if not self._is_whole(info['slot_count']):
                raise SetupError(f"Buffer {name} slot_count must be a positive integer.")
            if not self._is_whole(info['data_length']):
                raise SetupError(f"Buffer {name} data_length must be a positive integer.")
            try:
                info['data_dtype_obj'] = np.dtype(info['data_dtype'])
            except (TypeError, ValueError):
                raise SetupError(f"Buffer {name} data_dtype can not be interpreted as a numpy dtype.")
            info['overwrite'] = bool(info['overwrite'])
            info['buffer_obj'] = mimoBuffer(
                name = name,
                slot_count = info['slot_count'],
                data_length = info['data_length'],
                data_dtype = info['data_dtype_obj'],
                overwrite = info['overwrite']
            )
        self.buffer_objects_created = True
        
    # <--- buffer handeling
    
    # ---> worker handeling
    def replace_buffer_references(self):
        if not self.buffer_objects_created:
            self.create_buffers()
            
        for name, info in self.setup['Workers'].items():
            for bt in BUFFER_TYPES:
                for buffer_name in info[bt]:
                    if buffer_name not in self.setup['Buffers']:
                        raise SetupError(f"Worker {name} references unknown {bt} {buffer_name}")
                    info[bt][buffer_name] = self.setup['Buffers'][buffer_name]['buffer_obj']
            
        

    
    @staticmethod
    def _is_whole(self, value):
        return isinstance(value, int) and value > 0
    
    # def make_bool(self, value, msg):
    #     try:
    #         boolean = bool(value)
    #     except ValueError:
    #         raise SetupError(f"{msg} {value} can not be interpreted as a boolean.")
    #     if boolean != value:
    #         self.logger.warning(f"{msg} {value} is not a boolean. Casting to {boolean}.")
    #     return boolean
    
        
            
    # def analyze_buffers(self):
    #     for buffer_name, buffer in self.buffers.items():
    #         buffer['slot_count'] = self.make_whole(buffer['slot_count'], f"Buffer {buffer_name} slot_count")
    #         buffer['data_length'] = self.make_whole(buffer['data_length'], f"Buffer {buffer_name} data_length")
    #         try:
    #             buffer['data_dtype'] = np.dtype(buffer['data_dtype'])
    #         except TypeError:
    #             raise SetupError(f"Buffer {buffer_name} data_dtype can not be interpreted as a numpy dtype.")
            
    #         buffer['overwrite'] = self.make_bool(buffer['overwrite'], f"Buffer {buffer_name} overwrite")
            
    # def analyze_workers(self):
    #     for worker_name, worker in self.workers.items():
    #         worker['number_of_processes'] = self.make_whole(worker['number_of_processes'], f"Worker {worker_name} number_of_processes")
            
    #         worker['file'], worker['function'] = self.analyze_function(worker_name, worker['file'], worker['function'])
    #         worker['function'] = self.import_function_from_file(worker['file'], worker['function'])
    #         worker.pop('file')
            
    #         worker['config'] = self.options['overarching_config'] + worker['config']
            
    #         for bt in BUFFER_TYPES:
    #             for buffer_name in worker[bt]:
    #                 if buffer_name not in self.buffers:
    #                     raise SetupError(f"Worker {worker_name} references unknown {bt} {buffer_name}")
                    
    # def load_config_file(self, file):
    #     file = os.path.join(self.setup_dir, file)
    #     with open(file, 'r') as stream:
    #         config = yaml.safe_load(stream) # empty file returns None
    #     if config is None:
    #         return {}
    #     else:
    #         return config
        
    
    # def create_config_dict(self, worker_name, config_files):
    #     config = {}
    #     for file in config_files:
    #         file_config = self.load_config_file(file)
    #         for key, value in file_config.items():
    #             if key in config:
    #                 self.logger.warning(f"Worker {worker_name} overwrites key {key} with the value from config file {file}")
    #             config[key] = value
                
    #     obligatory_config = {
    #         'run_directory': self.run_directory,
    #         'name': worker_name,
    #         'debug': self.options['debug_workers']
    #     }
    #     for key, value in obligatory_config:
    #         if key in config:
    #             self.logger.warning(f"Worker {worker_name} overwrites key {key} with the value from the obligatory config")
    #         config[key] = value
    #     return config
    
    
    