import unittest
from pathlib import Path


class DeploymentDocsTests(unittest.TestCase):
    def test_readme_has_vercel_turso_setup_steps(self):
        text = Path("README.md").read_text(encoding="utf-8")
        for marker in (
            "Vercel",
            "Turso",
            "TURSO_DATABASE_URL",
            "TURSO_AUTH_TOKEN",
            "面试官",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)
