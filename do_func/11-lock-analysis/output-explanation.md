# 输出说明

测试证明 fixture 中能查询 `shared_gate`、识别四个加解锁事件、把锁内读写关联到共同锁，并把 `unlocked_write` 与写访问组合标为 `potential_race`。该结果不证明线程实际同时运行，也不覆盖条件变量或跨函数锁所有权转移。
