import contextlib
import io
import sys
import tempfile
import unittest

import ruv


class FakeSMU:
    """Stands in for the kernel driver: keeps offsets and answers like the SMU."""

    def __init__(self, initial=None, fail_set=()):
        self.state = dict(initial or {})
        self.fail_set = set(fail_set)
        self.calls = []

    def __call__(self, op, arg1=0, *args):
        self.calls.append((op, arg1))
        core = (arg1 >> 20) & 0xF
        if op == ruv.SMU_OP_SET_CO:
            if core in self.fail_set:
                return None
            value = arg1 & 0xFFFF
            self.state[core] = value - 0x10000 if value >= 0x8000 else value
            return (0,) * 6
        if op == ruv.SMU_OP_GET_CO:
            value = self.state.get(core, 0) & 0xFFFF
            return (value, 0, 0, 0, 0, 0)
        raise AssertionError(f"unexpected SMU op {op:#x}")


class RuvTest(unittest.TestCase):
    def setUp(self):
        self.smu = FakeSMU()
        self.saved = {
            name: getattr(ruv, name)
            for name in ("smu_command", "is_root", "cpu_supported", "driver_loaded")
        }
        self.argv = sys.argv
        ruv.smu_command = self.smu
        ruv.is_root = lambda: True
        ruv.cpu_supported = lambda: True
        ruv.driver_loaded = lambda: True
        self.addCleanup(self.restore)

    def restore(self):
        sys.argv = self.argv
        for name, value in self.saved.items():
            setattr(ruv, name, value)

    def run_main(self, *argv):
        sys.argv = ["ruv.py", *argv]
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            ruv.main()

    def cpuinfo_says(self, text):
        with tempfile.NamedTemporaryFile("w") as fp:
            fp.write(text)
            fp.flush()
            saved, ruv.CPUINFO = ruv.CPUINFO, fp.name
            try:
                return self.saved["cpu_supported"]()
            finally:
                ruv.CPUINFO = saved

    def test_reads_negative_offset_as_signed(self):
        self.smu.state[0] = -30
        self.assertEqual(ruv.get_core_offset(0), -30)

    def test_writes_offset_with_core_index(self):
        self.assertTrue(ruv.set_core_offset(3, -30))
        self.assertEqual(self.smu.calls, [(ruv.SMU_OP_SET_CO, (3 << 20) | 0xFFE2)])

    def test_cpu_supported_reads_family_and_model(self):
        vermeer = "cpu family\t: 25\nmodel\t\t: 33\nmodel name\t: AMD Ryzen 7 5800X3D\n"
        self.assertTrue(self.cpuinfo_says(vermeer))
        self.assertFalse(self.cpuinfo_says(vermeer.replace(": 25", ": 23")))
        self.assertFalse(self.cpuinfo_says(vermeer.replace(": 33", ": 97")))

    def test_rejects_out_of_range_offset(self):
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-o", "31")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.calls, [])

    def test_rejects_out_of_range_corecount(self):
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-l", "-c", "9")
        self.assertEqual(exit.exception.code, 2)

    def test_failed_core_rolls_back_every_offset(self):
        self.smu.state = {core: -15 for core in range(8)}
        self.smu.fail_set = {5}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-c", "8", "-o", "-20")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.state, {core: -15 for core in range(8)})


if __name__ == "__main__":
    unittest.main()
