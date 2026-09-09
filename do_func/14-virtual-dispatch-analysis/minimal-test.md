# 最小测试方案

fixture 定义 Base、DerivedA、final DerivedB，使用 Base 指针调用同签名 virtual work；另定义 final FinalWorker 并调用 virtual run；显式调用 `b->Base::work`；再由纯虚 AbstractWorker 指针调用唯一已知 ConcreteWorker 实现。

通过条件：开放调用候选类型恰含 Base/DerivedA/DerivedB，所有边为 may 且仍允许未知目标；final 接收类型只有一个 exact 候选；限定调用为 direct/static_exact 且只有一个 exact 候选；纯虚调用即使只有一个已知实现也保持 open_world/may。
