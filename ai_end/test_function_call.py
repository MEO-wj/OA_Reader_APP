#!/usr/bin/env python3
"""测试 deepseek function calling 支持"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

model = os.getenv("OPENAI_MODEL")
print(f"测试模型: {model}")
print(f"API 地址: {os.getenv('OPENAI_BASE_URL')}\n")

# 简单的 function calling 测试
from tests.prompts_test_constants import TEST_FUNCTION_CALL_USER_PROMPT, TEST_FUNCTION_CALL_TOOL_DESCRIPTION

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": TEST_FUNCTION_CALL_TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

print(f"发送测试请求: {TEST_FUNCTION_CALL_USER_PROMPT}\n")

try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": TEST_FUNCTION_CALL_USER_PROMPT}],
        tools=tools,
        tool_choice="auto"
    )

    print(f"响应 ID: {response.id}")
    print(f"响应模型: {response.model}")

    if response.choices:
        msg = response.choices[0].message
        print(f"\n是否有 tool_calls: {msg.tool_calls is not None}")

        if msg.tool_calls:
            print(f"✅ Function Calling 工作正常！")
            for tc in msg.tool_calls:
                print(f"   - 函数: {tc.function.name}")
                print(f"   - 参数: {tc.function.arguments}")
        else:
            print(f"❌ 没有触发 tool call")
            print(f"   AI 直接回复: {msg.content}")
    else:
        print(f"❌ 响应没有 choices")

except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()
