"""TDD: 依赖注入容器单元测试。"""


class TestDIContainer:
    """AppContainer 测试套件。"""

    def test_create_container(self):
        """应可创建容器并读取配置 provider。"""
        from src.di.container import AppContainer

        container = AppContainer()

        assert container.config is not None

    def test_skill_system_singleton(self):
        """技能系统 provider 应保持单例语义。"""
        from src.di.container import AppContainer

        container = AppContainer()

        first = container.skill_system()
        second = container.skill_system()

        assert first is second

