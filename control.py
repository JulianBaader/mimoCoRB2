import yaml
from mimo_buffer import mimoBuffer, Reader, Writer, Observer
from mimo_worker import mimoWorker
import numpy as np
import os
from graphviz import Digraph
import time
import shutil


class mimoControl:
    def __init__(self, buffers_setup: dict, functions_setup: dict, function_configs: dict):
        self.buffers_setup = buffers_setup
        self.functions_setup = functions_setup
        self.function_configs = function_configs

    def initialize_buffers(self):
        self.buffers_dict = {}
        for name, setup in self.buffers_setup_dict.items():
            print(f"Initializing Buffer {name}") # TODO logging
            self.buffers_dict[name] = mimoBuffer(
                name=name,
                slot_count=setup['slot_count'],
                data_length=setup['data_length'],
                data_dtype=np.dtype(setup['data_dtype']),
                overwrite=setup['overwrite'],
            )
        
        self.buffers_for_shutdown = self.buffers_dict

    def initialize_functions(self):
        self.functions_dict = {}
        for name in self.functions_setup.items():
            setup = self.functions_setup[name]
            config = self.functions_config[name]
            print(f"Initializing Function {name}")
            self.functions_dict[name] = mimoWorker(
                name=name,
                function=setup['function'],
                args=(
                    Reader(self._get_buffers_from_strings(setup['source_list'])),
                    Writer(self._get_buffers_from_strings(setup['sink_list'])),
                    Observer(self._get_buffers_from_strings(setup['observe_list'])),
                    config,
                ),
                number_of_processes=setup['number_of_processes'],
            )

    def _get_buffers_from_strings(self, strings: list[str]):
        [self.buffers_dict[name] for name in strings]

    def start_functions(self):
        for name, function in self.functions_dict.items():
            print(f"Initalizing Function {name}") # TODO logging
            function.initialize_processes()
        for name, function in self.functions_dict.items():
            print(f"Starting Function {name}")
            function.start_processes()

    def check_data_flow(self) -> bool:
        """Checks the data flow"""
        # re-sort the setup, i.e. for each buffer a list of reader, writer and observer functions
        writers = {buffer_name: [] for buffer_name in self.buffers_setup.keys()}
        readers = {buffer_name: [] for buffer_name in self.buffers_setup.keys()}
        observers = {buffer_name: [] for buffer_name in self.buffers_setup.keys()}
        for function_name, setup in self.functions_setup.items():
            for buffer_name in setup['sink_list']:
                writers[buffer_name].append(function_name)
            for buffer_name in setup['source_list']:
                readers[buffer_name].append(function_name)
            for buffer_name in setup['observe_list']:
                observers[buffer_name].append(function_name)

        # check that each buffer has at most one writer
        for buffer_name, writer_list in writers.items():
            if len(writer_list) > 1:
                return False

        # check that there is only one root buffer and every other buffer is reachable from there

        # -> find all candidates for producer functions
        candidate_producer_functions = []
        for function_name, setup in self.functions_setup.items():
            if len(setup['source_list']) == 0 and len(setup['observe_list']) == 0 and len(setup['sink_list']) > 0:
                candidate_producer_functions.append(function_name)
        # -> check that only one producer function exists
        if len(candidate_producer_functions) != 1:
            return False
        producer_function = candidate_producer_functions[0]

        # -> check that the producer function has only one sink buffer
        root_buffers = self.functions_setup[producer_function]['sink_list']
        if len(root_buffers) != 1:
            return False
        root_buffer = root_buffers[0]

        # -> check that all other buffers are reachable from the root buffer
        reachable = set([root_buffer])
        while True:
            previous = reachable.copy()

            for buffer_name in reachable:
                # add all sinks of the functions, that read from this buffer to the reachables
                for function_name in readers[buffer_name]:
                    reachable.update(self.functions_setup[function_name]['sink_list'])

            if previous == reachable:
                break

        if set(self.buffers_setup.keys()) != reachable:
            return False

        # now every buffer has at most one writer and every buffer is reachable from the root buffer => data flow is an arborescence
        self.buffers_for_shutdown = {name: self._get_buffers_from_strings([name]) for name in root_buffers}
        return True
    
    def soft_shutdown_buffers(self):
        for name, buffer in self.buffers_for_shudown.items():
            print(f"Shutting down Buffer {name}") # TODO logging
            buffer.send_flush_event()
            
    def hard_shutdown_buffers(self):
        for name, buffer in self.buffers_dict.items():
            print(f"Shutting down Buffer {name}") # TODO logging
            buffer.send_flush_event()
            
    def shutdown_functions(self):
        for name, function in self.functions_dict.items():
            print(f"Shutting down Function {name}")
            function.shutdown()

    def visualize_buffers_and_functions(self, **kwargs):
        dot = Digraph(**kwargs)
        for buffer_name in self.buffers_setup.keys():
            dot.node('B' + buffer_name, shape='circle', label=buffer_name)
        for function_name in self.functions_setup.keys():
            dot.node('F' + function_name, shape='box', label=function_name)
        for function_name, setup in self.functions_setup.items():
            for source in setup['source_list']:
                dot.edge('B' + source, 'F' + function_name)
            for sink in setup['sink_list']:
                dot.edge('F' + function_name, 'B' + sink)
            for observe in setup['observe_list']:
                dot.edge('F' + function_name, 'B' + observe, style='dotted')
        dot.render('data_flow', cleanup=True)
        dot.view()
        # TODO how do i want to return the visualization?



class fileReader:
    def __init__(self, setup_file):
        self.setup_file = os.path.abspath(setup_file)
        self.setup_dir = os.path.dirname(self.setup_file)

        self.loaded_config_files = {}

    def __call__(self):
        self.load_setup()
        self.create_buffers_setup()
        self.create_functions_setup()
        self.create_config_dicts()
        return self.buffers_setup, self.functions_setup, self.function_configs

    def load_setup(self):
        # load the setup file
        with open(self.setup_file, 'r') as stream:
            setup = yaml.safe_load(stream)

        # read the setup
        self.options = setup.get('Options', {})
        self.buffers = setup.get('Buffers', {})
        self.functions = setup.get('Functions', {})

        # create the target directory
        self.output_directory = os.path.join(self.setup_dir, self.options.get('output_directory', 'target'))
        os.makedirs(self.output_directory, exist_ok=True)

        # create the run directory
        start_time = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.run_directory = os.path.join(
            self.output_directory, self.options.get('run_directory', 'run') + '_' + start_time
        )
        os.makedirs(self.run_directory, exist_ok=False)

        # copy the setup file to the run directory
        shutil.copy(self.setup_file, self.run_directory)

    def load_config_file(self, file: str):
        file = os.path.join(self.input_path, file)
        if file in self.loaded_config_files:
            return self.loaded_config_files[file]
        shutil.copy(file, self.run_directory)
        with open(file, 'r') as stream:
            config = yaml.safe_load(stream)
        self.loaded_config_files[file] = config
        return config

    def create_buffers_setup(self):
        # main overwrite
        overwrite = self.options.get('overwrite', True)

        self.buffers_setup = {}
        for name, setup in self.buffers.items():
            self.buffers_setup[name] = {
                'slot_count': setup.get('slot_count', 1),
                'data_length': setup.get('data_length', 1),
                'data_dtype': setup.get('data_dtype', 'float64'),
                'overwrite': setup.get('overwrite', overwrite),
            }

    def create_functions_setup(self):
        self.functions_setup = {}
        for name, setup in self.functions.items():
            self.functions_setup[name] = {
                'function': setup['function'],
                'source_list': setup.get('source_list', []),
                'sink_list': setup.get('sink_list', []),
                'observe_list': setup.get('observe_list', []),
                'number_of_processes': setup.get('number_of_processes', 1),
            }

    def create_config_dicts(self):
        # overarching config dict
        if 'overarching_config' in self.options:
            overarching_config = self.load_config_file(self.options['overarching_config'])
        else:
            overarching_config = {}

        self.function_configs = {key: overarching_config for key in self.functions_setup.keys()}

        # main config file
        if 'main_config' in self.options:
            main_config = self.load_config_file(self.options['main_config'])
        else:
            main_config = {}
        for function_name in self.functions_setup.keys():
            if function_name in main_config:
                self.function_configs[function_name].update(main_config[function_name])

        # individual config files
        for function_name, setup in self.functions_setup.items():
            if 'config' in setup:
                self.function_configs[function_name].update(self.load_config_file(setup['config']))

        # obligatory config
        OBLIGATORY_KEYS = ['run_directory', 'name']
        for function_name in self.functions_setup.keys():
            overwriting_keys = [key for key in OBLIGATORY_KEYS if key in self.function_configs[function_name]]
            if overwriting_keys:
                raise RuntimeWarning(f"Overwriting keys {overwriting_keys} in config of {function_name}")

            self.function_configs[function_name].update(
                {
                    'run_directory': self.run_directory,
                    'name': function_name,
                }
            )
