# 操作与恢复

所有命令都以 Linux `bash /path/sdk-code-atlas/run.sh` 或 Windows `& .../run.ps1` 为前缀。路径含空格时引号包围。

1. `doctor --out /analysis` 检查依赖。无法载入 libclang 时停止，不改成 grep 分析。
2. 有真实编译数据库：`run --repo /repo --out /analysis --compdb /build/compile_commands.json --root /dependency --interface sdk_entry --html /result/overview.html`。多个 compdb 和 root 可重复。
3. 只有 CMake：`run --repo /repo --cmake-root /superbuild --params /params.json --out /analysis --html /result/overview.html`。参数文件示例：`{"TOP_DIR":"/work/sdk","BUILD_TESTING":"OFF"}`。脚本配置到分析目录，不修改源仓。
4. CMake 失败：读最新 run 的 configure.stderr.log、configuration_questions 产物与 CMake 源码。向用户说明缺失值和影响，补齐 params 后原命令重跑。外部生成头必须实际生成；不以 .o/.so 代替。
5. 审阅：读取 run/reviews 下请求；按 review.md 返回文件；`review-import --out /analysis --result /review.json`。配置改动只产出待应用提案，随后显式更正 params/CMake，再 run。
6. `trace --out /analysis --function sdk_entry --direction up` 返回从接口反向的路径与首次分歧选择。重载/同名时复制候选 ID 重试。
7. `flow --out /analysis --symbol <parameter-id>` 查看参数前向 may 数据关系。ID 可在 HTML 函数详情或 graph.json 查找。
8. 更新 commit 后使用相同 out 执行 run。检查 parsed/reused 与 invalidation_plan。仅改 HTML：`export --out /analysis --html /result/overview.html`。
9. `validate --out /analysis` 校验当前快照文件哈希。运行中断后原命令重跑；已提交 TU 可复用。锁由 OS 释放，不手工删除锁文件。

## llama.cpp

验证固定 commit 见包内 TEST_REPORT.md。示例选用 CPU-only 配置是阅读配置，不声称对应你的产品编译配置。

```text
run --repo /llama.cpp --out /llama-analysis --params /path/to/llama-params.json --interface llama_model_default_params --max-tu 12 --html /output/llama.html
```

params 示例：`{"GGML_CUDA":"OFF","GGML_NATIVE":"OFF","GGML_CPU":"OFF","GGML_OPENMP":"OFF","LLAMA_BUILD_TESTS":"OFF","LLAMA_BUILD_EXAMPLES":"OFF","LLAMA_BUILD_SERVER":"OFF","LLAMA_CURL":"OFF"}`。实际 CMake 版本可能不使用部分选项；以 configure 日志为准。

## 预算与边界

`--max-tu` 默认 128，`--tu-timeout` 默认 120 秒；超出保留 coverage frontier。每 TU 在独立进程提取，原生崩溃/超时不会导入半截 AST。`--clang-arg=-I/path` / `--clang-arg=--sysroot=/path` 可显式追加上下文；必须向用户说明所用值。自动 scope 扩大用文本定位候选，最后关系仍由 Clang 判断。
