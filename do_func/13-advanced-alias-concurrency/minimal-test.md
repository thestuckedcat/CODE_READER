# 最小测试方案

fixture 包含四个可独立断言的场景：条件分支令 `selected` 指向 `nested_a` 或 `nested_b` 后写 `selected->pair.left`；同一回调字段先设为 `leaf` 再清零；`wrapper_acquire`/`wrapper_release` 分别封装共享锁；调用方在两个包装调用间写 `shared_counter`。

通过条件：字段路径为 `pair.left`、对象集合含两个对象且 certainty 为 may；回调事件顺序为 set/clear 且最终状态 cleared；调用方产生 acquire/release 投影事件，写访问持有 `shared_gate`；`aliases` CLI 返回同一多目标字段事实。
