from mimocorb2.mimo_buffer import mimoBuffer
from mimocorb2.mimo_worker import mimoWorker

import yaml
import os
import time
import queue
import threading
import multiprocessing as mp

from graphviz import Digraph


class Control:
    def __init__(self, setup_file, gui=True, kbd=True, log_stats=True):
        self.run_directory = None
        self.setup_dir = os.path.dirname(setup_file)

        self.roots = None

        self.gui = gui
        self.kbd = kbd

        with open(setup_file, 'r') as file:
            self.setup = yaml.safe_load(file)

        self.setup_run_directory()

        self.command_queue = mp.Queue()
        self.stats_queue = mp.Queue(1)
        self.last_stats_time = time.time()
        self.current_stats = None

        self.buffers = {name: mimoBuffer.from_setup(name, setup) for name, setup in self.setup['Buffers'].items()}

        self.workers = {
            name: mimoWorker.from_setup(name, setup, self.setup_dir, self.run_directory, self.buffers)
            for name, setup in self.setup['Workers'].items()
        }

        self.find_roots()
        self.visualize_data_flow(os.path.join(self.run_directory, 'data_flow'))

    def __call__(self):
        if self.kbd:
            import mimocorb2.control_terminal as ctrl_term

            self.terminal_thread = threading.Thread(
                target=ctrl_term.control_terminal, args=(self.command_queue, self.stats_queue)
            )
            self.terminal_thread.start()
        if self.gui:
            import mimocorb2.control_gui as ctrl_gui

            infos = ctrl_gui.get_infos_from_control(self)
            self.gui_process = mp.Process(target=ctrl_gui.run_gui, args=(self.command_queue, self.stats_queue, infos))
            self.gui_process.start()

        self.start_workers()
        while True:
            # update stats every second
            if time.time() - self.last_stats_time > 1:
                self.last_stats_time = time.time()
                self.current_stats = self.get_stats()
                # try to empty the stats queue to remove old stats
                try:
                    self.stats_queue.get_nowait()
                except queue.Empty:
                    pass
            # fill the stats queue with the current stats
            try:
                self.stats_queue.put(self.current_stats, block=False)
            except queue.Full:
                pass

            # check for commands
            try:
                command = self.command_queue.get_nowait()
                if command is None:
                    break
                self.execute_command(command)
            except queue.Empty:
                pass
            time.sleep(0.1)

        if self.kbd:
            self.terminal_thread.join()
        if self.gui:
            self.gui_process.join()

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

    def execute_command(self, command: list) -> None:
        if command[0] == 'buffer':
            self.execute_buffer_command(command[1:])
        elif command[0] == 'worker':
            self.execute_worker_command(command[1:])
        elif command[0] == 'stats':
            self.execute_stats_command(command[1:])
        else:
            print(f"Unknown command: {command[0]}")

    def execute_buffer_command(self, command: list) -> None:
        if command[0] == 'all':
            target = self.buffers.values()
        elif command[0] == 'roots':
            target = self.roots.values()
        elif command[0] == 'named':
            names = command[2]
            for name in names:
                if name not in self.buffers:
                    raise ValueError(f"Unknown buffer: {name}")
            target = [self.buffers[name] for name in names]
        else:
            print(f"Unknown buffer target: {command[0]}")

        if command[1] == 'shutdown':
            for b in target:
                b.send_flush_event()
        elif command[1] == 'pause':
            for b in target:
                b.pause()
        elif command[1] == 'resume':
            for b in target:
                b.resume()
        else:
            print(f"Unknown buffer command: {command[1]}")

    def execute_worker_command(self, command: list) -> None:
        if command[0] == 'all':
            target = self.workers.values()
        elif command[0] == 'named':
            names = command[2]
            for name in names:
                if name not in self.workers:
                    raise ValueError(f"Unknown worker: {name}")
            target = [self.workers[name] for name in names]
        else:
            print(f"Unknown worker target: {command[0]}")

        if command[1] == 'shutdown':
            for w in target:
                w.shutdown()
        else:
            print(f"Unknown worker command: {command[1]}")

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
            'time_active': self.get_time_active(),
        }
        return stats
