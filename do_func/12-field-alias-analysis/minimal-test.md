# 最小测试方案

fixture 包含本地两级指针拷贝写 `shared_pair.left`、跨函数指针形参写同一字段、直接读取 `shared_pair.right`、共享锁经实参传播到锁形参，以及 `settings.submit` 经参数注册到 `leaf`。断言字段 ID 不混淆、单目标为 exact、锁摘要解析到 `shared_gate`、回调候选唯一。
