import contextlib
import fcntl
import io
import os
import signal
import sys
import tempfile
import unittest
from unittest import mock

import ruv


class FakeSMU:
    """Stands in for the kernel driver: keeps offsets and answers like the SMU."""

    def __init__(
        self,
        initial=None,
        fail_set=(),
        fail_get=(),
        interrupt_set=(),
        stuck_reset=(),
        term_set=(),
    ):
        self.state = dict(initial or {})
        self.fail_set = set(fail_set)
        self.fail_get = set(fail_get)
        self.interrupt_set = set(interrupt_set)
        self.stuck_reset = set(stuck_reset)
        self.term_set = set(term_set)
        self.calls = []

    def __call__(self, op, arg1=0, *args):
        self.calls.append((op, arg1))
        core = (arg1 >> 20) & 0xF
        if op == ruv.SMU_OP_SET_CO:
            if core in self.fail_set:
                return None
            if core in self.interrupt_set:
                self.interrupt_set.discard(core)  # only the first write is interrupted
                raise KeyboardInterrupt
            if core in self.term_set:
                self.term_set.discard(core)
                assert signal.getsignal(signal.SIGTERM) is ruv.interrupt_on_term
                os.kill(os.getpid(), signal.SIGTERM)
            value = arg1 & 0xFFFF
            self.state[core] = value - 0x10000 if value >= 0x8000 else value
            return (0,) * 6
        if op == ruv.SMU_OP_GET_CO:
            if core in self.fail_get:
                return None
            value = self.state.get(core, 0) & 0xFFFF
            return (value, 0, 0, 0, 0, 0)
        if op == ruv.SMU_OP_RESET_CO:
            self.state = {
                core: value
                for core, value in self.state.items()
                if core in self.stuck_reset
            }
            return (0,) * 6
        raise AssertionError(f"unexpected SMU op {op:#x}")


class RuvTest(unittest.TestCase):
    def setUp(self):
        self.smu = FakeSMU()
        self.saved = {
            name: getattr(ruv, name) for name in ("smu_command", "cpu_supported")
        }
        self.argv = sys.argv
        ruv.smu_command = self.smu
        ruv.cpu_supported = lambda: True
        self.patch("ruv.os.geteuid", 0)
        self.patch("ruv.os.path.isfile", True)
        lock_dir = tempfile.TemporaryDirectory()
        self.addCleanup(lock_dir.cleanup)
        lock_path = mock.patch("ruv.LOCK_PATH", f"{lock_dir.name}/ruv.lock")
        lock_path.start()
        self.addCleanup(lock_path.stop)
        self.signals = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        self.addCleanup(self.restore_signals)
        self.addCleanup(self.restore)

    def restore_signals(self):
        for sig, handler in self.signals.items():
            signal.signal(sig, handler)

    def patch(self, target, value):
        patcher = mock.patch(target, return_value=value)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_cpu_supported_requires_5800x3d(self):
        vermeer = "cpu family\t: 25\nmodel\t\t: 33\nmodel name\t: AMD Ryzen 7 5800X3D 8-Core Processor\n"
        self.assertTrue(self.cpuinfo_says(vermeer))
        self.assertFalse(self.cpuinfo_says(vermeer.replace(": 25", ": 23")))
        self.assertFalse(self.cpuinfo_says(vermeer.replace(": 33", ": 97")))
        self.assertFalse(self.cpuinfo_says(vermeer.replace("5800X3D", "5950X")))

    def test_rejects_out_of_range_offset(self):
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-o", "31")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.calls, [])

    def test_rejects_out_of_range_corecount(self):
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-l", "-c", "9")
        self.assertEqual(exit.exception.code, 2)

    def test_help_works_without_root_or_driver(self):
        with (
            mock.patch("ruv.os.geteuid", return_value=1000),
            mock.patch("ruv.os.path.isfile", return_value=False),
            self.assertRaises(SystemExit) as exit,
        ):
            self.run_main("-h")
        self.assertEqual(exit.exception.code, 0)

    def test_refuses_to_run_without_root(self):
        with (
            mock.patch("ruv.os.geteuid", return_value=1000),
            self.assertRaises(SystemExit) as exit,
        ):
            self.run_main("-l")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.calls, [])

    def test_reset_verifies_every_core(self):
        self.smu.state = {core: -20 for core in range(8)}
        self.smu.stuck_reset = {6}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-r")
        self.assertEqual(exit.exception.code, 1)

    def test_reset_passes_when_all_cores_read_zero(self):
        self.smu.state = {core: -20 for core in range(8)}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-r")
        self.assertEqual(exit.exception.code, 0)

    def test_reset_verifies_cores_beyond_corecount(self):
        self.smu.state = {core: -20 for core in range(8)}
        self.smu.stuck_reset = {6}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-r", "-c", "4")
        self.assertEqual(exit.exception.code, 1)

    def test_lock_is_held_for_the_whole_run(self):
        probes = []

        def probed_smu(op, arg1=0, *args):
            with open(ruv.LOCK_PATH, "w") as other:
                try:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    probes.append(True)
                else:
                    probes.append(False)
            return self.smu(op, arg1, *args)

        ruv.smu_command = probed_smu
        self.run_main("-o", "-20")
        self.assertTrue(probes)
        self.assertTrue(all(probes))

    def test_second_run_fails_fast_when_locked(self):
        with open(ruv.LOCK_PATH, "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(SystemExit) as exit:
                self.run_main("-o", "-20")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.calls, [])

    def test_failed_core_rolls_back_every_offset(self):
        self.smu.state = {core: -15 for core in range(8)}
        self.smu.fail_set = {5}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-c", "8", "-o", "-20")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.state, {core: -15 for core in range(8)})

    def test_incomplete_snapshot_aborts_before_writing(self):
        self.smu.state = {core: -15 for core in range(8)}
        self.smu.fail_get = {0}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-o", "-20")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(
            self.smu.calls, [(ruv.SMU_OP_GET_CO, core << 20) for core in range(8)]
        )
        self.assertEqual(self.smu.state, {core: -15 for core in range(8)})

    def test_interrupt_rolls_back_every_offset(self):
        self.smu.state = {core: -15 for core in range(8)}
        self.smu.interrupt_set = {3}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-o", "-20")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.state, {core: -15 for core in range(8)})

    def test_sigterm_rolls_back_every_offset(self):
        self.smu.state = {core: -15 for core in range(8)}
        self.smu.term_set = {3}
        with self.assertRaises(SystemExit) as exit:
            self.run_main("-o", "-20")
        self.assertEqual(exit.exception.code, 1)
        self.assertEqual(self.smu.state, {core: -15 for core in range(8)})


if __name__ == "__main__":
    unittest.main()
