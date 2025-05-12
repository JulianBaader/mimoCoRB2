"""This module provides a minimal implementation of terminal control for the mimocorb2 application."""

import queue
import json

COMMANDS = {
    'pause roots': ['buffer', 'roots', 'pause'],
    'pause all': ['buffer', 'all', 'pause'],
    'resume roots': ['buffer', 'roots', 'resume'],
    'resume all': ['buffer', 'all', 'resume'],
    'shutdown roots': ['buffer', 'roots', 'shutdown'],
    'shutdown all': ['buffer', 'all', 'shutdown'],
    'shutdown workers': ['worker', 'all', 'shutdown'],
}


def control_terminal(command_queue: queue, stats_queue: queue):
    """
    A simple terminal interface for controlling the mimocorb2 application.

    Args:
        command_queue (queue.Queue): Queue for sending commands to the control.
        stats_queue (queue.Queue): Queue for receiving statistics from the control.
    """
    print("Control Terminal: Type 'help' for available commands.")
    
    while True:
        try:
            command = input("mimocorb2> ").lower()
            if command in COMMANDS:
                command_queue.put(COMMANDS[command])
            elif command == 'stats':
                print(json.dumps(stats_queue.get(), indent=4, sort_keys=True))
            elif command == 'help':
                print("Available commands:")
                for cmd in COMMANDS:
                    print(f"  {cmd}")
                print("  stats")
                print("  help")
            elif command == 'exit':
                worker_stats = stats_queue.get()['workers']
                if sum(worker_stats.values()) > 0:
                    print("Warning: Some workers are still active. Use 'shutdown workers' to stop them.")
                else:
                    command_queue.put(None)
                    print("Exiting control terminal.")
                    break
            else:
                print(f"Unknown command: {command}. Type 'help' for available commands.")
        except EOFError:
            break