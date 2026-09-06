# 宿主 Agent 审阅协议

输入为 review_request envelope。每个任务针对一个间接/虚调用问题；后续可按共同原因批量调度。打开 request 引用的源码，查目标槽位写入/注册、可见作用域和生效条件。记录实际阅读的文件 SHA-256 和半开字节区间。没有证据时返回 unresolved，不编造目标。

输出严格匹配 `schemas/review_result.schema.json`。复制 request 的 task_id、snapshot_id、input_hash、issue_ids。relation_proposals 的 target 必须是当前 graph 中已存在的 function ID，callsite 必须是该问题调用点。read_set 每项包含 id、file、hash、start、end。所有建议都保留 agent/may/unknown_target_possible=true；resolved 仅表示审阅者结论。

correction_proposals 是结构化配置建议，包含字段、建议值和原因；Python 输出 configuration_patch，但不会执行建议中的代码，也不会修改业务源码。改配置后必须重解析。review-import 对旧快照、错误输入 hash、越界证据、错误端点或缺失证据返回非零，保留原快照。

search_set 记录实际搜索；不用搜索时为空。查询结果不替代 read_set 源码证据。模型运行由宿主提供；脚本不接收 API key、不发送源码到网络。
