"""main.py 行为测试。"""

import re
from unittest.mock import Mock


def test_keyboard_interrupt_prints_usage_before_goodbye(monkeypatch, capsys):
    import main

    fake_config = Mock()
    fake_config.base_url = "https://example.com/v1"
    fake_config.model = "test-model"
    fake_config.skills_dir = "./skills"

    fake_client = Mock()
    fake_client.get_usage_summary.return_value = {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30,
    }

    monkeypatch.setattr(main.Config, "load", lambda: fake_config)
    monkeypatch.setattr(main, "get_chat_client", lambda config: fake_client)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))

    main.main()

    out = capsys.readouterr().out
    clean = re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert "本次运行 Token 使用统计" in clean
    assert "总计: 30" in clean
    assert "再见" in clean
    assert clean.index("本次运行 Token 使用统计") < clean.index("再见")


def test_main_async_uses_di_chat_client_provider(monkeypatch):
    import main

    fake_config = Mock()
    fake_config.base_url = "https://example.com/v1"
    fake_config.model = "test-model"
    fake_config.skills_dir = "./skills"

    fake_client = Mock()

    monkeypatch.setattr(main.Config, "load", lambda: fake_config)
    monkeypatch.setattr(main, "get_chat_client", Mock(return_value=fake_client))
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "quit")

    main.main()

    main.get_chat_client.assert_called_once_with(fake_config)
