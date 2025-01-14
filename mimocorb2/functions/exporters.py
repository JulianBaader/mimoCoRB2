from mimocorb2.function_templates import Exporter

def drain(*mimo_args):
    exporter = Exporter(mimo_args)
    generator = exporter()
    while True:
        data, metadata = next(generator)
        if data is None:
            break