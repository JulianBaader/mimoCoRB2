from mimocorb2.worker_templates import Filter


def copy(buffer_io):
    """mimoCoRB Filter: Copy data from one buffer into (multiple) other buffer(s)."""
    processor = Filter(buffer_io)

    def ufunc(data):
        return True

    processor(ufunc)
