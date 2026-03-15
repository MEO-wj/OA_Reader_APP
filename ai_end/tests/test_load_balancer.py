"""AI 负载均衡器测试。"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_end.services.load_balancer import AILoadBalancer, ModelConfig


class TestModelConfig:
    """ModelConfig 单元测试。"""

    def test_model_config_creation(self):
        """测试模型配置创建。"""
        config = ModelConfig(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
            model="gpt-3.5-turbo",
        )
        assert config.api_key == "sk-test-key"
        assert config.base_url == "https://api.example.com/v1"
        assert config.model == "gpt-3.5-turbo"
        assert config._429_until == 0.0

    def test_is_available_initially_true(self):
        """测试初始状态可用。"""
        config = ModelConfig(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
            model="gpt-3.5-turbo",
        )
        assert config.is_available is True

    def test_mark_429_sets_cooldown(self):
        """测试标记 429 状态。"""
        config = ModelConfig(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
            model="gpt-3.5-turbo",
        )
        before_mark = time.time()
        config.mark_429(cooldown_seconds=60)
        after_mark = time.time()

        assert config._429_until >= before_mark + 60
        assert config._429_until <= after_mark + 60

    def test_is_available_false_during_cooldown(self):
        """测试冷却期间不可用。"""
        config = ModelConfig(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
            model="gpt-3.5-turbo",
        )
        config._429_until = time.time() + 100  # 未来 100 秒

        assert config.is_available is False

    def test_is_available_true_after_cooldown(self):
        """测试冷却后恢复可用。"""
        config = ModelConfig(
            api_key="sk-test-key",
            base_url="https://api.example.com/v1",
            model="gpt-3.5-turbo",
        )
        config._429_until = time.time() - 1  # 过去 1 秒

        assert config.is_available is True


class TestAILoadBalancerInit:
    """AILoadBalancer 初始化测试。"""

    def test_empty_config(self):
        """测试空配置。"""
        balancer = AILoadBalancer([])
        assert balancer.models == []
        assert balancer.current_index == 0

    def test_single_model_config(self):
        """测试单模型配置。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a"]}
        ]
        balancer = AILoadBalancer(models_config)

        assert len(balancer.models) == 1
        assert balancer.models[0].model == "model-a"
        assert balancer.models[0].api_key == "sk-key1"

    def test_multiple_models_from_single_config(self):
        """测试单个配置中的多个模型。"""
        models_config = [
            {
                "api_key": "sk-key1",
                "base_url": "https://api1.com/v1",
                "models": ["model-a", "model-b", "model-c"],
            }
        ]
        balancer = AILoadBalancer(models_config)

        assert len(balancer.models) == 3
        assert [m.model for m in balancer.models] == ["model-a", "model-b", "model-c"]

    def test_multiple_configs(self):
        """测试多个配置组。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a"]},
            {"api_key": "sk-key2", "base_url": "https://api2.com/v1", "models": ["model-b", "model-c"]},
        ]
        balancer = AILoadBalancer(models_config)

        assert len(balancer.models) == 3

    def test_skip_invalid_config(self):
        """测试跳过无效配置。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a"]},
            {"api_key": None, "base_url": "https://api2.com/v1", "models": ["model-b"]},  # 无效
            {"api_key": "sk-key3", "base_url": None, "models": ["model-c"]},  # 无效
            {"api_key": "sk-key4", "base_url": "https://api4.com/v1", "models": []},  # 无效
        ]
        balancer = AILoadBalancer(models_config)

        assert len(balancer.models) == 1
        assert balancer.models[0].model == "model-a"


class TestAILoadBalancerGetNextModel:
    """获取下一个模型测试。"""

    def test_round_robin(self):
        """测试轮询调度。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a", "model-b"]}
        ]
        balancer = AILoadBalancer(models_config)

        # 第一次获取
        model1 = balancer.get_next_model()
        assert model1.model == "model-a"

        # 第二次获取
        model2 = balancer.get_next_model()
        assert model2.model == "model-b"

        # 第三次获取应该回到 model-a
        model3 = balancer.get_next_model()
        assert model3.model == "model-a"

    def test_skip_unavailable_model(self):
        """测试跳过不可用模型。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a", "model-b"]}
        ]
        balancer = AILoadBalancer(models_config)

        # 获取第一个并标记为 429
        model_a = balancer.get_next_model()
        balancer.mark_model_429(model_a, cooldown_seconds=60)

        # 下一个应该跳过 model-a 获取 model-b
        model_b = balancer.get_next_model()
        assert model_b.model == "model-b"

        # 继续轮询 - model-a 仍在冷却中，所以还是 model-b
        model_c = balancer.get_next_model()
        assert model_c.model == "model-b"  # 冷却期间持续返回 model-b

    def test_all_models_unavailable(self):
        """测试所有模型不可用。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a"]},
            {"api_key": "sk-key2", "base_url": "https://api2.com/v1", "models": ["model-b"]},
        ]
        balancer = AILoadBalancer(models_config)

        # 标记所有模型为 429
        balancer.mark_model_429(balancer.get_next_model(), cooldown_seconds=60)
        balancer.mark_model_429(balancer.get_next_model(), cooldown_seconds=60)

        # 所有模型都不可用
        result = balancer.get_next_model()
        assert result is None

    def test_empty_models_returns_none(self):
        """测试空模型列表返回 None。"""
        balancer = AILoadBalancer([])
        result = balancer.get_next_model()
        assert result is None

    def test_single_model_rotation(self):
        """测试单模型轮询。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a"]}
        ]
        balancer = AILoadBalancer(models_config)

        for _ in range(5):
            model = balancer.get_next_model()
            assert model.model == "model-a"


class TestAILoadBalancerMark429:
    """标记 429 状态测试。"""

    def test_mark_specific_model(self):
        """测试标记特定模型。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a", "model-b"]}
        ]
        balancer = AILoadBalancer(models_config)

        model_a = balancer.models[0]
        balancer.mark_model_429(model_a, cooldown_seconds=30)

        assert model_a.is_available is False

    def test_mark_none_model(self):
        """测试标记 None 模型。"""
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a"]}
        ]
        balancer = AILoadBalancer(models_config)

        # 不应抛出异常
        balancer.mark_model_429(None, cooldown_seconds=30)


class TestAILoadBalancerThreadSafety:
    """线程安全测试。"""

    def test_concurrent_access(self):
        """测试并发访问。"""
        import threading

        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["model-a", "model-b"]}
        ]
        balancer = AILoadBalancer(models_config)

        results = []
        errors = []

        def get_model():
            try:
                for _ in range(100):
                    model = balancer.get_next_model()
                    if model:
                        results.append(model.model)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=get_model) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) > 0


class TestAILoadBalancerEdgeCases:
    """边界情况测试。"""

    def test_model_with_special_characters(self):
        """测试包含特殊字符的模型名。"""
        models_config = [
            {"api_key": "sk-key+1", "base_url": "https://api.example.com/v1", "models": ["gpt-3.5-turbo"]}
        ]
        balancer = AILoadBalancer(models_config)

        model = balancer.get_next_model()
        assert model.api_key == "sk-key+1"
        assert model.model == "gpt-3.5-turbo"

    def test_url_without_trailing_slash(self):
        """测试不带尾随斜杠的 URL。"""
        models_config = [
            {"api_key": "sk-key", "base_url": "https://api.example.com/v1", "models": ["model-a"]}
        ]
        balancer = AILoadBalancer(models_config)

        model = balancer.get_next_model()
        assert model.base_url == "https://api.example.com/v1"

    def test_url_with_trailing_slash(self):
        """测试带尾随斜杠的 URL（会被保留）。"""
        models_config = [
            {"api_key": "sk-key", "base_url": "https://api.example.com/v1/", "models": ["model-a"]}
        ]
        balancer = AILoadBalancer(models_config)

        model = balancer.get_next_model()
        # URL 会被原样保留
        assert model.base_url == "https://api.example.com/v1/"
