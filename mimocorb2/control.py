from mimocorb2.mimo_buffer import mimoBuffer
from mimocorb2.mimo_worker import mimoWorker
from pathlib import Path

import yaml
import os
import time
import queue
import threading
import multiprocessing as mp
import graphviz


class Control:
    def __init__(self, setup_dict: dict, setup_dir: Path | str, mode: str = 'kbd+stats') -> None:
        self.run_dir = None
        self.setup_dir = Path(setup_dir).resolve()

        self.roots = None

        self.modes = mode.split('+')

        self.setup = setup_dict

        self.set_up_run_dir()

        self.print_queue = mp.Queue()

        self.command_queue = mp.Queue()
        self.stats_queue = mp.Queue(1)
        self.last_stats_time = time.time()
        self.current_stats = None

        self.buffers = {name: mimoBuffer.from_setup(name, setup) for name, setup in self.setup['Buffers'].items()}

        self.workers = {
            name: mimoWorker.from_setup(name, setup, self.setup_dir, self.run_dir, self.buffers, self.print_queue)
            for name, setup in self.setup['Workers'].items()
        }

        self.find_roots()
        try:
            self.visualize_data_flow(os.path.join(self.run_dir, 'data_flow'))
        except graphviz.backend.ExecutableNotFound as e:
            print("Graphviz executables not found. Data flow visualization will not be generated.")
            print(e)
        self.save_setup()

    def __call__(self) -> None:
        """Start the control loop as well as the control interfaces."""
        if 'kbd' in self.modes:
            import mimocorb2.control_interfaces.control_terminal as ctrl_term

            self.terminal_thread = threading.Thread(
                target=ctrl_term.control_terminal, args=(self.command_queue, self.stats_queue, self.print_queue)
            )
            self.terminal_thread.start()
        if 'gui' in self.modes:
            import mimocorb2.control_interfaces.control_gui as ctrl_gui

            infos = ctrl_gui.get_infos_from_control(self)
            self.gui_process = mp.Process(
                target=ctrl_gui.run_gui, args=(self.command_queue, self.stats_queue, self.print_queue, infos)
            )
            self.gui_process.start()
        if 'stats' in self.modes:
            import mimocorb2.control_interfaces.control_stats_logger as ctrl_stats_logger

            self.stats_logger_thread = threading.Thread(
                target=ctrl_stats_logger.control_stats_logger,
                args=(self.command_queue, self.stats_queue, self.print_queue, self.run_dir),
            )
            self.stats_logger_thread.start()

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

        if 'kbd' in self.modes:
            self.terminal_thread.join()
        if 'gui' in self.modes:
            self.gui_process.join()
        if 'stats' in self.modes:
            self.stats_logger_thread.join()

    def save_setup(self):
        copy = self.setup.copy()
        for worker_name, worker in self.workers.items():
            copy['Workers'][worker_name]['config'] = worker.buffer_io.config.copy()
        setup_file = self.run_dir / 'setup.yaml'
        with setup_file.open('w') as f:
            yaml.safe_dump(copy, f, default_flow_style=False, sort_keys=False)

    def set_up_run_dir(self) -> None:
        """Set up the run directory"""
        target_dir = self.setup_dir / self.setup.get('target_directory', 'target')
        target_dir.mkdir(parents=True, exist_ok=True)

        self.start_time = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.run_dir = target_dir / f'run_{self.start_time}'
        self.run_dir.mkdir(parents=True, exist_ok=False)

        self.run_dir = self.run_dir.resolve()

    def find_roots(self) -> None:
        self.roots = {}
        for worker_name, worker_info in self.setup['Workers'].items():
            if len(worker_info.get('sources', [])) == 0 and len(worker_info.get('observes', [])) == 0:
                for buffer_name in worker_info.get('sinks', []):
                    self.roots[buffer_name] = self.buffers[buffer_name]

    def visualize_data_flow(self, file: str, **digraph_kwargs) -> None:
        dot = graphviz.Digraph(format='svg', **digraph_kwargs)

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

    def get_worker_stats(self) -> dict:
        """Get the statistics of all workers."""
        stats = {}
        for name, worker in self.workers.items():
            worker_stats = worker.get_stats()
            sum_alive = sum(worker_stats['alive_processes'])
            stats[name] = {
                'processes': sum_alive,
                'cpu_percent': sum(worker_stats['cpu_percents']),
            }
        return stats

    def get_time_active(self) -> float:
        """Return the time the workers have been active."""
        return time.time() - self.run_start_time

    def get_stats(self) -> dict:
        """Get the statistics of all workers and buffers."""
        buffer_stats = self.get_buffer_stats()
        worker_stats = self.get_worker_stats()
        time_active = self.get_time_active()
        total_processes_alive = sum(worker_stats[name]['processes'] for name in worker_stats)

        stats = {
            'buffers': buffer_stats,
            'workers': worker_stats,
            'time_active': time_active,
            'total_processes_alive': total_processes_alive,
        }
        return stats

    @classmethod
    def from_setup_file(cls, setup_file: Path | str, mode: str = 'kbd+stats') -> 'Control':
        """Create a Control instance from a setup file."""
        setup_file = Path(setup_file)
        if not setup_file.exists():
            raise FileNotFoundError(f"Setup file {setup_file} does not exist.")

        with setup_file.open('r') as f:
            setup_dict = yaml.safe_load(f)

        if not isinstance(setup_dict, dict):
            raise ValueError(f"Setup file {setup_file} does not contain a valid setup dictionary.")

        setup_dir = setup_file.resolve().parent
        return cls(setup_dict, setup_dir, mode=mode)
