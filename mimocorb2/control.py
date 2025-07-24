from mimocorb2.mimo_buffer import mimoBuffer
from mimocorb2.mimo_worker import mimoWorker
from pathlib import Path

import yaml
import os
import psutil
import time
import queue
import threading
import multiprocessing as mp
import graphviz
import tempfile
import logging


def configure_logging():
    # Create a named temporary file (not deleted automatically)
    log_file = tempfile.NamedTemporaryFile(prefix="mimocorb2_", suffix=".log", delete=False)
    log_path = log_file.name
    log_file.close()

    # Configure logging to only write to the file
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
        filename=log_path,
        filemode='w',  # Overwrite log file on each run
    )

    # Optional: reduce verbosity of 3rd-party libraries
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('PyQt5').setLevel(logging.WARNING)

    # Optional: store log path for debugging
    return log_path


class Control:
    """Central controller for managing buffers, workers, and interfaces in the mimoCorb2 framework.

    This class sets up the runtime environment based on a provided setup dictionary or file,
    initializes and controls all `mimoBuffer` and `mimoWorker` instances, and handles user interaction
    through terminal, GUI, or logging interfaces. It also tracks and reports system statistics.

    Parameters
    ----------
    setup_dict : dict
        A dictionary containing the setup configuration for buffers and workers.
        It must define "Buffers" and "Workers" keys, where each buffer/worker has its setup parameters.
    setup_dir : Path | str
        The directory path where the setup originated. Used to resolve paths for scripts and outputs.
    mode : str, optional
        A '+'-separated string to configure which interfaces to activate.
        Supported modes: 'kbd' (terminal), 'gui' (graphical interface), 'stats' (logging).
        Default is 'kbd+stats'.

    Attributes
    ----------
    setup : dict
        The complete configuration for the buffers and workers.
    setup_dir : Path
        Path to the setup directory.
    run_dir : Path
        Path to the run directory where logs, visualizations, and runtime data are stored.
    modes : list[str]
        List of active interface modes.
    buffers : dict[str, mimoBuffer]
        Dictionary of buffer names to buffer instances.
    workers : dict[str, mimoWorker]
        Dictionary of worker names to worker instances.
    roots : dict[str, mimoBuffer]
        Subset of buffers that act as roots (not used as sources or observations).
    print_queue : mp.Queue
        Queue used for collecting print/log output from subprocesses.
    stats_queue : mp.Queue
        Queue holding the most recent system statistics.
    command_queue : mp.Queue
        Queue for control commands issued by interfaces.
    current_stats : dict
        Most recently collected system statistics.
    last_stats_time : float
        Timestamp of the last statistics update.
    run_start_time : float
        Timestamp when the worker processes were started.
    terminal_thread : threading.Thread
        Thread running the keyboard control interface (if active).
    gui_process : mp.Process
        Process running the GUI interface (if active).
    stats_logger_thread : threading.Thread
        Thread running the statistics logger (if active).

    Methods
    -------
    __call__()
        Starts the control loop, interfaces, and workers. Main runtime entry point.
    get_stats()
        Returns a complete dictionary of all system statistics (buffers, workers, control, uptime).
    execute_command(command)
        Executes a command (e.g., pause/resume/shutdown) targeting buffers or workers.
    visualize_data_flow(file, **kwargs)
        Generates a Graphviz visualization of the data flow between buffers and workers.
    from_setup_file(setup_file, mode='kbd+stats')
        Class method to create a Control instance from a YAML setup file.
    """

    def __init__(self, setup_dict: dict, setup_dir: Path | str, mode: str = 'kbd+stats') -> None:
        log_path = configure_logging()
        print(f"Logs will be saved to: {log_path}")

        self.setup = setup_dict
        self.setup_dir = Path(setup_dir).resolve()
        self.modes = mode.split('+')

        self.set_up_run_dir()

        # Output queues
        self.print_queue = mp.Queue()
        self.stats_queue = mp.Queue(1)
        # Input queue
        self.command_queue = mp.Queue()

        self.last_stats_time = time.time()
        self.current_stats = None

        self.buffers = {name: mimoBuffer.from_setup(name, setup) for name, setup in self.setup['Buffers'].items()}
        self.workers = {
            name: mimoWorker.from_setup(name, setup, self.setup_dir, self.run_dir, self.buffers, self.print_queue)
            for name, setup in self.setup['Workers'].items()
        }

        self.find_roots()
        self.visualize_data_flow(os.path.join(self.run_dir, 'data_flow'))
        self.save_setup()

    def __call__(self) -> None:
        """Start the interfaces, workers, and control loop."""
        self.start_interfaces()
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

        self.join_interfaces()

    def save_setup(self):
        copy = self.setup.copy()
        for worker_name, worker in self.workers.items():
            copy['Workers'][worker_name]['config'] = worker.buffer_io.config.copy()
        setup_file = self.run_dir / 'setup.yaml'
        with setup_file.open('w') as f:
            yaml.safe_dump(copy, f, default_flow_style=False, sort_keys=False)

    def resolve_path(self, path_input: str) -> Path:
        """Resolve a path

        Parameters
        ----------
        path : str
            The path to resolve, can be absolute, relative or user home.
        """
        path = Path(path_input)
        if path_input.startswith('~'):
            # resolve home directory
            path = path.expanduser()

        if path.is_absolute():
            # absolute path, no need to resolve
            return path
        else:
            # relative path, resolve relative to setup_dir
            return self.setup_dir / path

    def set_up_run_dir(self) -> None:
        """Set up the run directory"""
        target_dir = self.resolve_path(self.setup.get('target_directory', 'target'))
        target_dir.mkdir(parents=True, exist_ok=True)

        self.start_time = time.strftime('%Y-%m-%d_%H-%M-%S')
        self.run_dir = target_dir / f'run_{self.start_time}'
        self.run_dir.mkdir(parents=True, exist_ok=False)

        self.run_dir = self.run_dir.resolve()

    def find_roots(self) -> None:
        """Find the root buffers that are not sources of any worker."""
        self.roots = {}
        for worker_name, worker_info in self.setup['Workers'].items():
            if len(worker_info.get('sources', [])) == 0 and len(worker_info.get('observes', [])) == 0:
                for buffer_name in worker_info.get('sinks', []):
                    self.roots[buffer_name] = self.buffers[buffer_name]

    def visualize_data_flow(self, file: str, **digraph_kwargs) -> None:
        """Visualize the data flow of the setup using graphviz."""
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

        try:
            dot.render(file, cleanup=True)
        except graphviz.backend.ExecutableNotFound as e:
            print("Graphviz executables not found. Data flow visualization will not be generated.")
            print(e)

    def start_workers(self) -> None:
        """Initialize and start all workers."""
        for w in self.workers.values():
            w.initialize_processes()
        self.run_start_time = time.time()
        for w in self.workers.values():
            w.start_processes()

    def start_interfaces(self) -> None:
        """Start the control interfaces."""
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

    def join_interfaces(self) -> None:
        """Join the control interfaces."""
        if 'kbd' in self.modes:
            self.terminal_thread.join()
        if 'gui' in self.modes:
            self.gui_process.join()
        if 'stats' in self.modes:
            self.stats_logger_thread.join()

    def execute_command(self, command: list) -> None:
        """Execute a command from the command queue.

        Parameters
        ----------
        command : list
            The command to execute. First element is the command type ('buffer', 'worker', 'stats'), followed by its arguments.
        """
        dispatch = {
            'buffer': self._execute_buffer_command,
            'worker': self._execute_worker_command,
        }
        handler = dispatch.get(command[0])
        if handler:
            handler(*command[1:])
        else:
            print(f"Unknown command: {command[0]}")

    def _execute_buffer_command(self, target: str | list, action: str) -> None:
        """Execute a command for a buffer.

        Parameters
        ----------
        target : str | list
            'all' to apply to all buffers
            'roots' to apply to all root buffers
            list[str] to apply to specific buffers
        action : str
            'shutdown'
            'pause'
            'resume'
        """
        action_dispatch = {
            'shutdown': lambda b: b.send_flush_event(),
            'pause': lambda b: b.pause(),
            'resume': lambda b: b.resume(),
        }
        if target == 'all':
            targets = self.buffers.keys()
        elif target == 'roots':
            targets = self.roots.keys()
        elif isinstance(target, list):
            targets = target
        else:
            raise ValueError(f"Invalid target for buffer command: {target}")

        for name in targets:
            if name in self.buffers:
                buffer = self.buffers[name]
                action_func = action_dispatch.get(action)
                if action_func:
                    action_func(buffer)
                else:
                    print(f"Unknown action for buffer {name}: {action}")
            else:
                print(f"Buffer {name} not found.")

    def _execute_worker_command(self, target: str | list, action: str) -> None:
        """Execute a command for a worker.

        Parameters
        ----------
        target : str | list
            'all' to apply to all workers
            list[str] to apply to specific workers
        action : str
            'shutdown'
        """
        action_dispatch = {
            'shutdown': lambda w: w.shutdown(),
        }
        if target == 'all':
            targets = self.workers.keys()
        elif isinstance(target, list):
            targets = target
        else:
            raise ValueError(f"Invalid target for worker command: {target}")

        for name in targets:
            if name in self.workers:
                worker = self.workers[name]
                action_func = action_dispatch.get(action)
                if action_func:
                    action_func(worker)
                else:
                    print(f"Unknown action for worker {name}: {action}")
            else:
                print(f"Worker {name} not found.")

    # statistics
    def get_buffer_stats(self) -> dict:
        """Get the statistics of all buffers.

        Returns
        -------
        dict
            buffer_name : dict
                See mimo_buffer.mimoBuffer.get_stats
        """
        return {name: b.get_stats() for name, b in self.buffers.items()}

    def get_worker_stats(self) -> dict:
        """Get the statistics of all workers.

        Returns
        -------
        dict
            worker_name : dict
                Dictionary containing:
                - processes : int
                    Number of processes that are alive in the worker.
                - cpu_percent : float
                    Average CPU usage of the worker processes.
        """
        stats = {}
        for name, worker in self.workers.items():
            worker_stats = worker.get_stats()
            sum_alive = sum(worker_stats['alive_processes'])
            stats[name] = {
                'processes': sum_alive,
                'cpu_percent': sum(worker_stats['cpu_percents']) / sum_alive if sum_alive > 0 else 0,
            }
        return stats

    def get_control_stats(self) -> dict:
        """Get the statistics of the control itself.

        Returns
        -------
        dict
            Dictionary containing:
            - cpu_percent : float
                CPU usage of the control process."""
        return {
            'cpu_percent': psutil.cpu_percent(),
        }

    def get_time_active(self) -> float:
        """Return the time the workers have been active."""
        return time.time() - self.run_start_time

    def get_stats(self) -> dict:
        """Get the statistics of all workers and buffers.

        Returns
        -------
        dict
            Dictionary containing:
            - buffers : dict
                Statistics of all buffers. (See Control.get_buffer_stats)
            - workers : dict
                Statistics of all workers. (See Control.get_worker_stats)
            - time_active : float
                Time the workers have been active in seconds.
            - total_processes_alive : int
                Total number of processes that are alive across all workers.
            - control : dict
                Statistics of the control itself. (See Control.get_control_stats)
        """
        buffer_stats = self.get_buffer_stats()
        worker_stats = self.get_worker_stats()
        time_active = self.get_time_active()
        total_processes_alive = sum(worker_stats[name]['processes'] for name in worker_stats)
        control_stats = self.get_control_stats()

        stats = {
            'buffers': buffer_stats,
            'workers': worker_stats,
            'time_active': time_active,
            'total_processes_alive': total_processes_alive,
            'control': control_stats,
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
