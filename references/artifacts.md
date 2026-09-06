# 原型文件映射

`runs/<run>/artifacts.json` 是阶段产物定位入口：logical_name + scope_key 指向 `objects/<hash前2位>/<hash>.json[l]`。所有自有数据以 schema_version/record_kind/record_id/payload/provenance envelope 保存。不同 TU 不会相互覆盖。

实际实现：request、doctor、workspace_manifest、inventory、parameters、assumptions、cmake_discovery、configure_request/result、configuration_questions（失败时）、compile_commands、cmake_reply、build_context、parse_plan、每 TU facts/function_ir/diagnostics/dependencies/receipt、compiler_facts、derived_relations、function_summaries、issues、coverage、review_plan/request/result、validation_report、configuration_patch（需要时）、agent_supplements、change_set、invalidation_plan、checkpoint、snapshot_validation、run_summary。

直接可读文件：

- `runs/<run>/configure.stdout.log` / stderr.log。
- `runs/<run>/jobs/<tu>/input.json` / output.json / stderr.log：隔离提取器交接文件，调试用途。
- `runs/<run>/reviews/*.request.json`：宿主 Agent 可直接读取。
- `snapshots/<id>/analysis_manifest.json` 和 `graph.json`：不可变发布快照。
- `current.json`：当前指针；`index.sqlite`：缓存、快照和元数据；`writer.lock`：进程间锁。
- HTML 相邻 `<name>.export_bundle.json` / export_validation.json：可独立检查的导出数据。

与完整设计差异：本版不单独生成 symbol_map（使用 Clang USR/定义内容派生身份）、annotations task 文件、完整 dependency facets 索引、分片图和 events.jsonl；未实现的高级协议不会产生空文件假装完成。function_summaries 是 partial 摘要，不包含 CFG 固定点。新增源码文件导致保守 TU 失效；已有文件变动按真实 include 依赖处理。再次分析不会直接采用旧 Agent 候选来冒充当前事实。
