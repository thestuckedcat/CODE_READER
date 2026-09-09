# 可复现功能目录

目录按功能首次纳入验收的顺序使用两位序号。每个功能必须包含简介、设计边界、最小测试、测试方法、原始输出、输出说明和追加式测试日志；日志中的成功只覆盖对应 fixture，不外推到任意 SDK。

| 序号 | 功能 | 入口 |
|---|---|---|
| 01 | 隔离环境 | [01-environment](01-environment/README.md) |
| 02 | 工程配置 | [02-configuration](02-configuration/README.md) |
| 03 | Clang 语义提取 | [03-semantic-extraction](03-semantic-extraction/README.md) |
| 04 | 调用图 | [04-call-graph](04-call-graph/README.md) |
| 05 | 增量缓存 | [05-incremental-cache](05-incremental-cache/README.md) |
| 06 | 审阅校验 | [06-review-validation](06-review-validation/README.md) |
| 07 | 离线 Viewer | [07-offline-viewer](07-offline-viewer/README.md) |
| 08 | Native CFG | [08-native-cfg](08-native-cfg/README.md) |
| 09 | 标量数据流 | [09-scalar-dataflow](09-scalar-dataflow/README.md) |
| 10 | 打包 | [10-packaging](10-packaging/README.md) |
| 11 | 锁与共享状态并行性 | [11-lock-analysis](11-lock-analysis/README.md) |
| 12 | 字段别名、锁所有权与回调候选 | [12-field-alias-analysis](12-field-alias-analysis/README.md) |

使用隔离运行时执行单项测试：

```text
runtime/<platform>/venv/.../python scripts/run_feature_test.py <feature-name>
```

功能目录变更记录见 [CHANGELOG](CHANGELOG.md)。
