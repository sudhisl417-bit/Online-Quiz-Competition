"""Smoke tests that run the *real* app with Streamlit's AppTest framework.

    python -m unittest tests.test_app_smoke -v

They are skipped automatically when Streamlit (>= 1.28) is not installed.
"""

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Use a throw-away database. Must be set before quiz_app is first imported.
_TMP = tempfile.TemporaryDirectory()
os.environ["QUIZ_DB_PATH"] = str(pathlib.Path(_TMP.name) / "smoke.db")

try:
    from streamlit.testing.v1 import AppTest
except Exception:                                      # pragma: no cover
    AppTest = None


def _button(at, text):
    return next(b for b in at.button if text in b.label)


@unittest.skipIf(AppTest is None, "Streamlit AppTest is not available")
class SmokeTests(unittest.TestCase):
    def new_app(self):
        return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()

    def test_login_page_renders(self):
        at = self.new_app()
        self.assertFalse(at.exception, at.exception)

    def test_second_session_also_renders(self):
        self.new_app()
        at = self.new_app()                            # the original app crashed here
        self.assertFalse(at.exception, at.exception)

    def test_admin_can_sign_in(self):
        at = self.new_app()
        at.radio(key="login_role").set_value("🛠️  Admin").run()
        at.text_input[0].input("ansh")
        at.text_input[1].input("12345678")
        _button(at, "Sign in").click().run()
        self.assertFalse(at.exception, at.exception)
        self.assertEqual(at.session_state["role"], "admin")


if __name__ == "__main__":
    unittest.main()
