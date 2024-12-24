import yaml
from mimo_buffer import mimoBuffer
from mimo_worker import mimoWorker
import numpy as np
import multiprocessing
import os
from graphviz import Digraph


class mimoControl:
    def __init__(self, buffers_setup: dict, functions_setup: dict, options_setup: dict, function_configs: dict):
        
        self.buffers_setup = buffers_setup
        self.functions_setup = functions_setup
        self.options_setup = options_setup
        self.function_configs = function_configs
        
            
    def initialize_buffers(self):
        self.buffers_dict = {}
        for name, setup in self.buffers_setup_dict.items():
            self.buffers_dict[name] = mimoBuffer(
                name = name,
                slot_count = setup['slot_count'],
                data_length = setup['data_length'],
                data_dtype = np.dtype(setup['data_dtype']),
                overwrite = setup['overwrite']
                )
            
    def initialize_functions(self):
        self.functions_dict = {}
        for name, setup in self.functions_setup.items():
            self.functions_dict[name] = mimoWorker(
                name = name,
                function = setup['function'],
                args = (
                    self._get_buffers_from_strings(setup['source_list']),
                    self._get_buffers_from_strings(setup['sink_list']),
                    self._get_buffers_from_strings(setup['observe_list']),
                ),
                number_of_processes = setup['number_of_processes']
            )
            
    def _get_buffers_from_strings(self, strings: list[str]):
        [self.buffers_dict[name] for name in strings]
            
    def start_functions(self):
        for function in self.functions_dict.values():
            function.initialize_processes()
        for function in self.functions_dict.values():
            function.start_processes()
            
            
    def visualize_data_flow(self, **kwargs):
        dot = Digraph(**kwargs)
        for buffer_name in self.buffers_setup.keys():
            dot.node('B' + buffer_name)
        for function_name in self.functions_setup.keys():
            dot.node('F' + function_name)
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
        