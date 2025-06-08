from mimocorb2.worker_templates import Filter


def copy(buffer_io):
    """mimoCoRB2 Function: Copy data from one source to multiple sinks.

    Copys data from a source buffer to multiple sink buffers. This function is useful for duplicating data streams within the mimoCoRB2 framework.

    Type
    ----
    Filter

    Buffers
    -------
    sources
        1 source buffer containing the data to be copied
    sinks
        1 or more sink buffers that will receive the copied data
    observes
        0
    """
    processor = Filter(buffer_io)

    def ufunc(data):
        return True

    processor(ufunc)
