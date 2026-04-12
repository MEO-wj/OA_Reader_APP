tools:
  - name: todolist_check
    description: |
      任务步骤检查点。每完成一个步骤后必须调用此工具报告进度。
      如果跳过步骤，必须提供合理理由（至少5个字符），否则将被打回。
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
          description: 跳过步骤时的理由（status=skip 时必填，至少5个字符）
      required: [step, status]
    handler: todolist_handler.check_step
