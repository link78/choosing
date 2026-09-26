import os
import unittest
from unittest.mock import patch

from choosing.api import resolve_server_host, resolve_server_port


class DeploymentConfigTests(unittest.TestCase):
    def test_resolve_server_host_defaults_to_all_interfaces(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_server_host(), "0.0.0.0")

    def test_resolve_server_port_reads_environment_variable(self):
        with patch.dict(os.environ, {"PORT": "9001"}, clear=True):
            self.assertEqual(resolve_server_port(), 9001)

    def test_resolve_server_port_rejects_invalid_values(self):
        with patch.dict(os.environ, {"PORT": "abc"}, clear=True):
            with self.assertRaisesRegex(ValueError, "PORT must be an integer"):
                resolve_server_port()

        with patch.dict(os.environ, {"PORT": "70000"}, clear=True):
            with self.assertRaisesRegex(ValueError, "PORT must be between 1 and 65535"):
                resolve_server_port()


if __name__ == "__main__":
    unittest.main()
