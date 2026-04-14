tools:
  - name: todolist_check
    description: |
      任务步骤检查点。每完成一个步骤后必须调用此工具报告进度。
      如果跳过步骤，必须提供合理理由（至少5个字符），否则将被打回。
      标记 done 时，系统会校验当轮是否调用了该步骤的必需工具，未调用将被打回。
    parameters:
      type: object
      properties:
        step:
          type: integer
          enum: [1, 2, 3]
          description: 当前步骤编号
        status:
          type: string
          enum: [done, skip, start]
          description: "done=完成, skip=跳过(需提供reason), start=开始执行"
        reason:
          type: string
          description: status=skip 时必填（至少5个字符），status=done 时可选（用于调试日志）
        called_tools:
          type: array
          items:
            type: string
          description: "系统自动注入，当轮已调用的工具名列表。LLM 无需手动填写。"
      required: [step, status]
    handler: todolist_handler.check_step
