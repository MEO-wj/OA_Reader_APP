# clear_memory 智能会话复用设计

## 背景

当前 `clear_memory` 无条件创建新会话，导致用户连续清空时产生大量空会话。需要引入"当天最新会话"的判断逻辑，复用空会话而非反复创建。

## 需求

```
clear_memory(user_id):
  1. 查询当天最新会话 (含 messages)
  2. 若会话存在 且 messages 非空 → 创建新会话
  3. 若会话存在 且 messages 为空 → 复用该 conversation_id
  4. 若无当天会话 → 创建新会话
  5. 返回 {"cleared": True, "conversation_id": "..."}
```

## 方案：MemoryDB 新增查询方法

### MemoryDB.get_latest_session_with_messages

JOIN `conversation_sessions` 和 `conversations` 表，查询当天最新会话及其消息状态：

```sql
SELECT cs.user_id, cs.conversation_id, cs.title, cs.created_at, cs.updated_at,
       COALESCE(c.messages, '[]'::jsonb) AS messages
FROM conversation_sessions cs
LEFT JOIN conversations c
  ON c.user_id = cs.user_id AND c.conversation_id = cs.conversation_id
WHERE cs.user_id = $1 AND cs.created_at >= $2 AND cs.created_at < $3
ORDER BY cs.created_at DESC
LIMIT 1
```

### clear_memory 三路判断

- 会话存在 + messages 非空 → `uuid.uuid4().hex[:8]` 新会话
- 会话存在 + messages 为空 → 复用该 `conversation_id`
- 无当天会话 → `uuid.uuid4().hex[:8]` 新会话

## 影响范围

| 文件 | 变更 |
|------|------|
| `src/db/memory.py` | 新增 `get_latest_session_with_messages` |
| `src/api/compat_service.py` | 重写 `clear_memory` 方法 |
| `tests/unit/test_compat_service.py` | 新增/更新测试用例 |

## 不影响的部分

- `_resolve_session`（用于 `ask`）行为不变
- `get_latest_session_in_utc_range` 保持原样
- `/ask` 接口不受影响

## 测试用例

| 场景 | 预期行为 |
|------|----------|
| 当天会话存在，messages 非空 | 创建新会话 |
| 当天会话存在，messages 为空 | 复用该会话，不创建新的 |
| 当天无会话 | 创建新会话 |
| 无 user_id | 抛出 ValueError |
