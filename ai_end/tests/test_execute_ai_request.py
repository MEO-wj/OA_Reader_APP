from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_end import app as app_module
from ai_end.services.load_balancer import ModelConfig


class ExecuteAIRequestModelSelectionTests(unittest.TestCase):
    def test_should_pass_selected_model_to_cached_agent(self) -> None:
        selected_model = ModelConfig(
            api_key="sk-test-key-1234567890",
            base_url="https://api.example.com/v1",
            model="test-model",
        )
        fake_load_balancer = Mock()
        fake_load_balancer.models = [selected_model]
        fake_load_balancer.get_next_model.return_value = selected_model

        fake_agent = Mock()
        fake_agent.invoke.return_value = {"messages": [AIMessage(content="ok")]}

        with patch.object(app_module, "_get_load_balancer", return_value=fake_load_balancer):
            with patch.object(app_module, "_load_short_memory", return_value=[]):
                with patch.object(app_module, "_get_cached_agent", return_value=fake_agent) as cached_agent_mock:
                    result = app_module._execute_ai_request(
                        question="hello",
                        top_k_hint=3,
                        display_name=None,
                        user_id="",
                    )

        self.assertEqual(result["answer"], "ok")
        cached_agent_mock.assert_called_once_with(selected_model)


if __name__ == "__main__":
    unittest.main()
