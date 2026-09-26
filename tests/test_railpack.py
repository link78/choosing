from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RailpackCompatibilityTests(unittest.TestCase):
    def test_start_script_exists_and_uses_python_module_entrypoint(self):
        start_script = ROOT / "start.sh"

        self.assertTrue(start_script.exists())
        self.assertEqual(start_script.read_text(encoding="utf-8"), "#!/bin/sh\nset -eu\n\nexec python -m choosing.api\n")

    def test_requirements_file_exists_for_python_app_detection(self):
        requirements_file = ROOT / "requirements.txt"

        self.assertTrue(requirements_file.exists())
        self.assertIn("No external runtime dependencies", requirements_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
