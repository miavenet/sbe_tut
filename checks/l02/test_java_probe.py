#!/usr/bin/env python3
"""The allocation probe must reject false zero-allocation claims."""
import unittest
from java_probe import probe_passes


class JavaProbeTests(unittest.TestCase):
    def test_reference_output(self):
        self.assertTrue(probe_passes(0, 'COPY_BYTES 0\nOWNING_BYTES 376000\n'))

    def test_fault_outputs(self):
        self.assertFalse(probe_passes(1, 'COPY_BYTES 0\nOWNING_BYTES 376000\n'))
        self.assertFalse(probe_passes(0, 'COPY_BYTES 160\nOWNING_BYTES 376000\n'))
        self.assertFalse(probe_passes(0, 'COPY_BYTES 0\nOWNING_BYTES 0\n'))
        self.assertFalse(probe_passes(0, 'COPY_BYTES 0\nOWNING_BYTES nonsense\n'))


if __name__ == '__main__': unittest.main()
