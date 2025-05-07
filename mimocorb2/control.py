from mimocorb2.mimo_buffer import mimoBuffer
from mimocorb2.mimo_worker import mimoWorker

import yaml
import os
import time
import multiprocessing

from graphviz import Digraph


class Control:
    def __init__(self, setup_file, gui=True):
        self.run_directory = None
        self.setup_dir = os.path.dirname(setup_file)
        
        self.roots = None
        
        with open(setup_file, 'r') as file:
            self.setup = yaml.safe_load(file)
            
        self.setup_run_directory()
        
        
        
        self.buffers = {
            name: mimoBuffer.from_setup(name, setup) for name, setup in self.setup['Buffers'].items()
        }
        
        self.workers = {
            name: mimoWorker.from_setup(name, setup, self.setup_dir, self.run_directory, self.buffers) for name, setup in self.setup['Workers'].items()
        }
        
        self.find_roots()
        self.visualize_data_flow(os.path.join(self.run_directory, 'data_flow'))
        
        
    def save_setup():
        raise NotImplementedError("Saving setup is not implemented yet.")
        
        
        
    
    def setup_run_directory(self):
        """Setup the run directory"""
        target_directory = os.path.join(self.setup_dir, self.setup.get('target_directory', 'target'))
        os.makedirs(target_directory, exist_ok=True)
        self.start_time = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.run_directory = os.path.join(target_directory, 'run' + '_' + self.start_time)
        os.makedirs(self.run_directory, exist_ok=False)
        self.run_directory = os.path.abspath(self.run_directory)
        
    def find_roots(self):
        self.roots = {}
        for worker_name, worker_info in self.setup['Workers'].items():
            if len(worker_info.get('sources', [])) == 0 and len(worker_info.get('observes', [])) == 0:
                for buffer_name in worker_info.get('sinks', []):
                    self.roots[buffer_name] = self.buffers[buffer_name]
                    
    def visualize_data_flow(self, file, **digraph_kwargs):
        dot = Digraph(format='svg', **digraph_kwargs)
        
        # Buffer Nodes
        for name in self.buffers:
            color = 'blue' if name in self.roots else 'black'
            dot.node('B' + name, label=name, color=color)
        
        # Worker Nodes
        for name, worker in self.workers.items():
            dot.node('W' + name, shape='box', label=name)
            
        # Edges
        for name, info in self.setup['Workers'].items():
            for source in info.get('sources', []):
                dot.edge('B' + source, 'W' + name)
            for sink in info.get('sinks', []):
                dot.edge('W' + name, 'B' + sink)
            for observe in info.get('observes', []):
                dot.edge('B' + observe, 'W' + name, style='dotted')
                
        dot.render(file, cleanup=True)

    
    
    def start_workers(self) -> None:
        """Initialize and start all workers."""
        for w in self.workers.values():
            w.initialize_processes()
        self.run_start_time = time.time()
        for w in self.workers.values():
            w.start_processes()

    
    
    # root buffer operations
    def shutdown_roots(self) -> None:
        for r in self.roots.values():
            r.send_flush_event()
    
    def pause_roots(self) -> None:
        for r in self.roots.values():
            r.pause()
            
    def resume_roots(self) -> None:
        for r in self.roots.values():
            r.resume()
            
    # global operations            
    def kill_workers(self) -> None:
        for w in self.workers.values():
            w.shutdown()
            
    def shutdown_buffers(self) -> None:
        for b in self.buffers.values():
            b.send_flush_event()
    
    # statistics
    def get_buffer_stats(self) -> dict:
        """Get the statistics of all buffers."""
        return {name: b.get_stats() for name, b in self.buffers.items()}

    def get_active_workers(self) -> dict:
        """Get the number of active processes for each worker."""
        return {name: sum(w.alive_processes()) for name, w in self.workers.items()}
    
    
    def get_time_active(self) -> float:
        """Return the time the workers have been active."""
        return time.time() - self.run_start_time
    
    def get_stats(self) -> dict:
        """Get the statistics of all workers and buffers."""
        stats = {
            'buffers': self.get_buffer_stats(),
            'workers': self.get_active_workers(),
            'time_active': self.get_time_active()
        }
        return stats
    
    def get_stats_timed(self) -> dict:
        """Get the statistics of all workers and buffers, but only once every second."""
        if time.time() - self.last_stats_time > 1 or self.current_stats is None:
            self.last_stats_time = time.time()
            self.current_stats = self.get_stats()
        return self.current_stats