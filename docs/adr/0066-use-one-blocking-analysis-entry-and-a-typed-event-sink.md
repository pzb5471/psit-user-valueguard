# 使用一个阻塞分析入口和类型化事件出口

M3 需要编排案例，M2 需要独立控制三个 Agent 和 GLM 调用，同时阶段结果、模型尝试和失败必须及时持久化。如果 M2 直接写数据库会跨越模块边界，只在最后返回结果又会丢失中间记录。

M2 公开同步阻塞的 `AnalysisEngine.analyze_case(AnalysisRequest, AnalysisEventSink) -> AnalysisOutcome`。M2 在阶段开始、模型尝试结束、阶段校验通过、阶段失败和全部完成时发出类型化事件；M3 接收事件并通过 M1 保存。M3 在本机后台线程池运行该入口。

M2 不持有 DataGateway、Session 或数据库连接，不自行启动任务队列和独立进程。证据不足以完整成功合同表达，不误判为技术失败。
