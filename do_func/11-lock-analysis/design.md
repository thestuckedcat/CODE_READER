# 设计

输入是 Clang 已解析函数 AST。提取层识别常见 mutex/spin/read/write lock 调用与 C++ RAII guard，记录 `lock_event`、`lock_region`、`shared_access`；并行性层对同一共享对象的读写冲突对取持锁集合交集。存在共同锁输出 `serialized_by_common_lock/exact`，否则输出 `potentially_parallel_conflict/may`。
