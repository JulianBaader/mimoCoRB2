import mimocorb2.control as ctrl
import argparse


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
        choices=["gui+stats", "kbd+stats", "gui", "kbd"],
        default="gui+stats",
        help="Control mode to use: 'gui' for graphical interface, 'kbd' for keyboard interface (default: gui)",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Using setup file: {args.setup_file} in {args.control_mode} mode.")
    control = ctrl.Control.from_setup_file(args.setup_file, mode=args.control_mode)
    control()


if __name__ == "__main__":
    main()
