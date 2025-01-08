import multiprocessing
import logging

SOURCES = 0
SINKS = 1
OBSERVES = 2
CONFIG = 3


class mimoWorker:
    def __init__(self, name: str, function, args, number_of_processes: int):
        self.name = name
        self.function = function
        self.args = args
        self.number_of_processes = number_of_processes

        self.logger = logging.getLogger(name=name)
        self.processes = []

    def initialize_processes(self):
        if len(self.processes) > 0:
            raise RuntimeError("Processes already initialized")
        for i in range(self.number_of_processes):
            process = multiprocessing.Process(target=self.function, args=self.args, name=f'{self.name}_{i}')
            self.processes.append(process)

    def start_processes(self):
        for process in self.processes:
            process.start()

    def alive_processes(self):
        return [p.is_alive() for p in self.processes]

    def shutdown(self):
        for p in self.processes:
            if p.is_alive():
                self.logger.info(f"Waiting 3s for process {p.name} to finish")
                p.join(3)
            if p.is_alive():
                self.logger.info(f"Killing process {p.name}")
                p.terminate()
