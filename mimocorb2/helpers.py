from pathlib import Path


def resolve_path(path_input: str, setup_dir: Path | str) -> Path:
    """Resolve a path relative to the setup directory.

    Parameters
    ----------
    path_input : str
        The path to resolve, can be absolute, relative or user home.
    setup_dir : Path | str
        The directory where the setup file is located.

    Returns
    -------
    Path
        The resolved path.
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
        return Path(setup_dir).resolve() / path
