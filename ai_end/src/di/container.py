"""应用级依赖注入容器。"""

from dependency_injector import containers, providers

from src.chat.history_manager import HistoryManager
from src.chat.memory_manager import MemoryManager
from src.core.api_queue import APIQueue
from src.core.skill_adapter import SkillAdapter, SkillBackend
from src.db.memory import MemoryDB


class AppContainer(containers.DeclarativeContainer):
    """统一管理核心依赖。"""

    config = providers.Configuration()

    skill_system = providers.Singleton(
        SkillAdapter.create,
        backend=SkillBackend.FILESYSTEM,
        skills_dir="./skills",
    )
    skill_system_factory = providers.Factory(
        SkillAdapter.create,
    )
    api_queue = providers.Singleton(APIQueue)
    memory_db = providers.Singleton(MemoryDB)
    memory_manager_factory = providers.Factory(
        MemoryManager,
        config=config,
        api_queue=api_queue,
        memory_db=memory_db,
    )
    history_manager_factory = providers.Factory(
        HistoryManager,
        config=config,
        api_queue=api_queue,
        memory_db=memory_db,
    )
