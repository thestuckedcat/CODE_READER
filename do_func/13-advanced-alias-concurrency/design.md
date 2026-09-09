# 设计

提取层将最外层成员表达式递归拆成 `field_path`，避免把 `selected->pair.left` 截断为单层。有限别名闭包允许一个指针聚合多个对象，字段事实保留全部 `object_ids` 并降级为 `may`。

回调赋值事件记录 action、表达式、guard、证据和候选；应用层按同一 owner/object/field 的源码偏移排序，计算 configured、cleared 或 may_multiple 状态，并用 `supersedes_event_id` 表达覆盖。

锁包装函数先归一化其锁对象，再提取无未配对歧义的净 acquire/release；精确调用点产生带 `propagated_from` 的合成事件。调用方配对后的范围用于标注其中共享访问持有的锁，随后重新计算冲突关系。
