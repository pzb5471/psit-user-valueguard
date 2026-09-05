# 让 M1 提供五个小型数据端口

ZIP 导入、案例查询、证据读取、运行保存和人工确认具有不同调用者、权限和失败方式。全部塞进一个不断扩张的 `DataGateway` 会让任何修改都影响 M3 的全部数据依赖，也难以分开测试。

M1 对外提供 `BatchImportGateway`、`CaseQueryGateway`、`EvidenceGateway`、`RunStore` 和 `ReviewStore` 五个 Protocol。它们共同由同一 SQLite 实现，但分别运行合同测试，只返回 Pydantic 对象或受控文件流，不返回 ORM、Session 和绝对路径。

五个端口不是五个业务模块，不引入五套数据库或服务进程。M3 只注入其用例需要的端口，不直接写 SQL。
