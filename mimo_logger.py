"""TODO implement a logging system designed for the ringbuffer

This means i want everything to have a single mode.
Single warning for example will warn the user but only once, even if the same warning is called multiple times.
This allows the user to see the warning but not be spammed by it.
"""


class Logger:
    def __init__(self, name):
        self.warnings = []
        self.debugs = []
        self.name = name

    def warning(self, message):
        self.warnings.append(message)
        print(self.name + ": " + message)

    def single_warning(self, message):
        if message not in self.warnings:
            self.warning(message)

    def debug(self, message):
        self.debugs.append(message)
        print(self.name + ": " + message)

    def single_debug(self, message):
        if message not in self.debugs:
            self.debug(message)
