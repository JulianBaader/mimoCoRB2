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
            
            

        
    def check_data_flow(self) -> bool:
        """Checks the data flow
        
        
        """
        # resort the setup, i.e. for each buffer a list of reader, writer and observer functions
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
        return True
    
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
       
    def visualize_arboresence(self, **kwargs):
        """TODO visualize only a view of the ringbuffers with the functions in between"""
        raise NotImplementedError