# 设计

提取层只记录编译器事实：类型稳定 ID、基类 ID、类型 final 标志，以及方法的所属类型、virtual/pure/final 标志；虚调用点同时携带被引用声明的参数类型，因此纯虚方法不需要伪造函数定义。应用层 `virtual_dispatch` 构建派生闭包并以方法名和参数类型匹配覆盖候选，图层再按当前 TU/build 选择定义变体。

普通非 final 基类调用输出所有已知候选但标记 `open_world/may` 和 `unknown_target_possible=true`；语言级 final 方法或类型使实现集合封闭，唯一候选可标 `exact`；`Base::method` 显式限定调用在提取时直接标为静态调用。
