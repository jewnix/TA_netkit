import import_declare_test

import sys

from splunklib import modularinput as smi
from netkit_speedtest import stream_events, validate_input


class NETKIT_SPEEDTEST_PROBE(smi.Script):
    def __init__(self):
        super(NETKIT_SPEEDTEST_PROBE, self).__init__()

    def get_scheme(self):
        scheme = smi.Scheme('netkit_speedtest_probe')
        scheme.description = 'Speedtest (Cloudflare throughput)'
        scheme.use_external_validation = True
        scheme.streaming_mode_xml = True
        scheme.use_single_instance = False

        scheme.add_argument(
            smi.Argument(
                'name',
                title='Name',
                description='Name',
                required_on_create=True
            )
        )
        scheme.add_argument(
            smi.Argument(
                'profile',
                required_on_create=True,
            )
        )
        scheme.add_argument(
            smi.Argument(
                'download_mb',
                required_on_create=False,
            )
        )
        scheme.add_argument(
            smi.Argument(
                'upload_mb',
                required_on_create=False,
            )
        )
        return scheme

    def validate_input(self, definition: smi.ValidationDefinition):
        return validate_input(definition)

    def stream_events(self, inputs: smi.InputDefinition, ew: smi.EventWriter):
        return stream_events(inputs, ew)


if __name__ == '__main__':
    exit_code = NETKIT_SPEEDTEST_PROBE().run(sys.argv)
    sys.exit(exit_code)