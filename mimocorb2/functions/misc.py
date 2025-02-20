from mimocorb2.worker_templates import Filter


def copy(*mimo_args):
    """mimoCoRB Filter: Copy data from one buffer into (multiple) other buffer(s)."""
    processor = Filter(mimo_args)

    def ufunc(data):
        return True

    processor(ufunc)
