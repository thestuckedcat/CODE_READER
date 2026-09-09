# 输出说明

测试证明限定 fixture 中两级本地指针和跨函数形参均解析到 `shared_pair.left`，`right` 保持独立字段 ID；锁形参解析到 `shared_gate`；回调字段候选解析到 `leaf`。成功不代表支持任意 C/C++ 别名、回调或线程语义。
