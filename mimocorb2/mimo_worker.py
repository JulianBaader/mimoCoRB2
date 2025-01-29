import multiprocessing
import logging
from typing import Callable

SOURCES = 0
SINKS = 1
OBSERVES = 2
CONFIG = 3


class mimoWorker:
    def __init__(self, name: str, function: Callable, args: list[list, list, list, dict], number_of_processes: int) -> None:
        self.name = name
        self.function = function
        self.args = args
        self.number_of_processes = number_of_processes

        self.logger = logging.getLogger(name=name)
        self.processes = []

    def initialize_processes(self) -> None:
        if len(self.processes) > 0:
            raise RuntimeError("Processes already initialized")
        for i in range(self.number_of_processes):
            process = multiprocessing.Process(target=self.function, args=self.args, name=f'{self.name}_{i}')
            self.processes.append(process)

    def start_processes(self) -> None:
        for process in self.processes:
            process.start()

    def alive_processes(self) -> list[bool]:
        return [p.is_alive() for p in self.processes]

    def shutdown(self) -> None:
        for p in self.processes:
            if p.is_alive():
                self.logger.info(f"Killing process {p.name}")
                p.terminate()
