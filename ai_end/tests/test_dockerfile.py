from pathlib import Path
import unittest


class DockerfileLayoutTests(unittest.TestCase):
    def test_should_copy_backend_and_ai_end_from_repo_root_context(self) -> None:
        dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("COPY ai_end ./ai_end", dockerfile_text)
        self.assertIn("COPY backend ./backend", dockerfile_text)


if __name__ == "__main__":
    unittest.main()
