import mimocorb2.control as ctrl
import logging
import argparse
import tempfile


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


def parse_args():
    parser = argparse.ArgumentParser(description="Run mimoCoRB2 control module with specified setup.")
    parser.add_argument(
        "setup_file",
        nargs="?",
        default="examples/muon/spin_setup.yaml",
        help="Path to the setup YAML file (default: examples/muon/spin_setup.yaml)",
    )
    parser.add_argument(
        "-c",
        "--control_mode",
        choices=["gui", "kbd"],
        default="gui",
        help="Control mode to use: 'gui' for graphical interface, 'kbd' for keyboard interface (default: gui)",
    )

    return parser.parse_args()


def main():
    log_path = configure_logging()
    args = parse_args()

    print(f"Using setup file: {args.setup_file} in {args.control_mode} mode. Logs will be saved to: {log_path}")
    control = ctrl.Control.from_setup_file(args.setup_file, mode=args.control_mode)
    control()


if __name__ == "__main__":
    main()
