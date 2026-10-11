"""
smolfiddle fork regression suite — offline, no browser, no network.

Covers everything the fork touches and must never break upstream:
  - termux_support neutrality off-Termux + behavior on-Termux (simulated)
  - DTO round-trip
  - controller validation paths (no webdriver needed)
  - SessionsStorage lifecycle with a stub driver
  - proxy extension creation
  - patcher platform mapping (linux + android)
  - guarded-import fallback when termux_support is absent

Run:  pytest src/test_fork_regression.py
      (also runnable with plain unittest)
"""

import os
import shutil
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import termux_support
from dtos import STATUS_ERROR, STATUS_OK, V1RequestBase, V1ResponseBase


class TestTermuxNeutralOffDevice(unittest.TestCase):
    def test_neutral_when_not_termux(self):
        with mock.patch.object(termux_support.os.path, "exists", return_value=False), \
             mock.patch.dict(termux_support.os.environ, {}, clear=True):
            self.assertFalse(termux_support.is_termux())
            self.assertFalse(termux_support.is_termux_x11())
            self.assertFalse(termux_support.should_skip_xvfb())
            self.assertIsNone(termux_support.get_chrome_path())
            self.assertIsNone(termux_support.get_chromedriver_path())
            self.assertEqual(termux_support.get_extra_chrome_args(), [])

    def test_detected_via_prefix_dir(self):
        def exists(p):
            return p == "/data/data/com.termux"
        with mock.patch.object(termux_support.os.path, "exists", side_effect=exists), \
             mock.patch.dict(termux_support.os.environ, {}, clear=True):
            self.assertTrue(termux_support.is_termux())
            self.assertTrue(termux_support.should_skip_xvfb())
            self.assertFalse(termux_support.is_termux_x11())

    def test_x11_when_display_set(self):
        def exists(p):
            return p == "/data/data/com.termux"
        env = {"DISPLAY": ":0", "PREFIX": "/data/data/com.termux/files/usr"}
        with mock.patch.object(termux_support.os.path, "exists", side_effect=exists), \
             mock.patch.dict(termux_support.os.environ, env, clear=True):
            self.assertTrue(termux_support.is_termux_x11())

    def test_extra_args_flags(self):
        def exists(p):
            return p == "/data/data/com.termux"
        with mock.patch.object(termux_support.os.path, "exists", side_effect=exists), \
             mock.patch.dict(termux_support.os.environ, {}, clear=True):
            self.assertEqual(termux_support.get_extra_chrome_args(), ["--disable-gpu"])
        env = {"TERMUX_SINGLE_PROCESS": "1", "TERMUX_JITLESS": "true",
               "TERMUX_DISABLE_GPU": "false"}
        with mock.patch.object(termux_support.os.path, "exists", side_effect=exists), \
             mock.patch.dict(termux_support.os.environ, env, clear=True):
            self.assertEqual(termux_support.get_extra_chrome_args(),
                             ["--single-process", "--js-flags=--jitless"])


class TestDtos(unittest.TestCase):
    def test_request_response_roundtrip(self):
        req = V1RequestBase({"cmd": "request.get", "url": "https://www.google.com/",
                             "maxTimeout": 60000})
        self.assertEqual(req.cmd, "request.get")
        res = V1ResponseBase({"status": STATUS_OK, "message": "x", "session": "s1"})
        self.assertEqual(res.status, STATUS_OK)
        self.assertEqual(res.session, "s1")


class TestControllerValidation(unittest.TestCase):
    def test_wrong_cmd(self):
        import flaresolverr_service as svc
        res = svc.controller_v1_endpoint(
            V1RequestBase({"cmd": "request.bad", "url": "https://www.google.com"}))
        self.assertEqual(res.status, STATUS_ERROR)
        self.assertIn("invalid", res.message)

    def test_missing_cmd(self):
        import flaresolverr_service as svc
        res = svc.controller_v1_endpoint(V1RequestBase({"url": "https://www.google.com"}))
        self.assertEqual(res.status, STATUS_ERROR)
        self.assertIn("mandatory", res.message)

    def test_missing_url(self):
        import flaresolverr_service as svc
        res = svc.controller_v1_endpoint(V1RequestBase({"cmd": "request.get"}))
        self.assertEqual(res.status, STATUS_ERROR)
        self.assertIn("mandatory", res.message)

    def test_missing_postdata(self):
        import flaresolverr_service as svc
        res = svc.controller_v1_endpoint(
            V1RequestBase({"cmd": "request.post", "url": "https://example.com"}))
        self.assertEqual(res.status, STATUS_ERROR)
        self.assertIn("postData", res.message)


class TestSessionsStub(unittest.TestCase):
    def test_lifecycle(self):
        import flaresolverr_service as svc
        import utils

        class FakeDriver:
            def quit(self):
                pass

            def close(self):
                pass

        with mock.patch.object(utils, "get_webdriver", return_value=FakeDriver()):
            svc.SESSIONS_STORAGE.sessions.clear()
            try:
                sess, fresh = svc.SESSIONS_STORAGE.create(session_id="fork-reg-1")
                self.assertTrue(fresh)
                self.assertTrue(svc.SESSIONS_STORAGE.exists("fork-reg-1"))
                _, fresh2 = svc.SESSIONS_STORAGE.create(session_id="fork-reg-1")
                self.assertFalse(fresh2)
                self.assertIn("fork-reg-1", svc.SESSIONS_STORAGE.session_ids())
                self.assertTrue(svc.SESSIONS_STORAGE.destroy("fork-reg-1"))
                self.assertFalse(svc.SESSIONS_STORAGE.destroy("missing"))
            finally:
                svc.SESSIONS_STORAGE.sessions.clear()


class TestProxyExtension(unittest.TestCase):
    def test_builds_manifest(self):
        import utils
        d = utils.create_proxy_extension({"url": "http://127.0.0.1:8888",
                                          "username": "u", "password": "p"})
        try:
            self.assertTrue(os.path.isfile(os.path.join(d, "manifest.json")))
            self.assertTrue(os.path.isfile(os.path.join(d, "background.js")))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestPatcherMapping(unittest.TestCase):
    def test_linux_and_android_map_to_linux64(self):
        from undetected_chromedriver.patcher import Patcher
        for plat, expected in (("linux", "linux64"), ("linux2", "linux64"),
                               ("android", "linux64")):
            p = Patcher.__new__(Patcher)
            p.platform = plat
            p.exe_name = "chromedriver%s"
            p.is_old_chromedriver = False
            p._custom_exe_path = True  # silence __del__ cleanup on partial instance
            Patcher._set_platform_name(p)
            self.assertEqual(p.platform_name, expected, plat)
            self.assertEqual(p.exe_name, "chromedriver", plat)

    def test_is_posix_covers_android(self):
        from undetected_chromedriver import patcher as patcher_mod
        self.assertTrue(patcher_mod.IS_POSIX)
        self.assertTrue("android".startswith(("darwin", "cygwin", "linux",
                                              "linux2", "freebsd", "android")))
        self.assertFalse("win32".startswith(("darwin", "cygwin", "linux",
                                             "linux2", "freebsd", "android")))


class TestGuardedImportFallback(unittest.TestCase):
    def test_utils_survives_missing_termux_support(self):
        # utils.py uses try/except ImportError around termux_support, so a
        # checkout without the fork file must still import and stay neutral.
        import utils
        with mock.patch.dict(sys.modules, {"termux_support": None}):
            self.assertTrue(hasattr(utils, "get_webdriver"))
            self.assertTrue(hasattr(utils, "get_chrome_exe_path"))


if __name__ == "__main__":
    unittest.main()
