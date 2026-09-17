import json
import unittest
from pathlib import Path


class VercelConfigTests(unittest.TestCase):
    def test_vercel_entry_exports_fastapi_app(self):
        from fastapi import FastAPI
        from app import app

        self.assertIsInstance(app, FastAPI)

    def test_vercel_json_targets_app_with_sixty_second_limit(self):
        data = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(data["functions"]["app.py"]["maxDuration"], 60)
