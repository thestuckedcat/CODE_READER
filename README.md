# CODE_READER · SDK Code Atlas 0.5

C/C++ Linux SDK 阅读工具的第一版 Skill 原型：CMake 求值 → Clang 语义提取 → Python 图分析与增量缓存 → 宿主 Agent 审阅 → 离线 HTML。

当前源码为 v0.5：在 v0.4 分层与隔离运行时基础上，新增锁事件、词法临界区、共享状态访问及保守并行冲突分析；文档反合检查扩展到全部 Markdown 文档。旧 v0.1 离线包仍可用于历史基础调用链，但不包含后续能力。

## 从哪里开始

- 开发计划与验收矩阵：[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)
- 分层架构与依赖规则：[ARCHITECTURE.md](ARCHITECTURE.md)
- 可复现功能目录：[do_func/README.md](do_func/README.md)
- Workflow/checkpoint 待确认方案：[references/workflow-checkpoints.md](references/workflow-checkpoints.md)
- 首版能力快照：[update/000_v0.1_capabilities.md](update/000_v0.1_capabilities.md)
- 第一轮工程接入：[update/001_round1_changes.md](update/001_round1_changes.md)
- 本轮 CFG/参数计算链及验证：[update/002_round2_changes.md](update/002_round2_changes.md)
- v0.4 分层重构与工程修复：[update/003_refactor_changes.md](update/003_refactor_changes.md)
- v0.5 锁与共享状态分析：[do_func/11-lock-analysis/README.md](do_func/11-lock-analysis/README.md)
- Skill 入口：[SKILL.md](SKILL.md)
- 当前可用能力及限制：[references/capabilities.md](references/capabilities.md)
- 操作说明：[references/workflow.md](references/workflow.md)
- 总体设计 v3.1：[references/design-v3.1.md](references/design-v3.1.md)
- 中间文件映射：[references/artifacts.md](references/artifacts.md)
- 测试报告：[TEST_REPORT.md](TEST_REPORT.md)
- 示例：下载 [examples/fixture-overview.html](examples/fixture-overview.html) 后用浏览器打开。

## 隔离环境与运行

本仓库保存 Skill、Python/C++ 源码、查看器、文档和测试，不提交第三方运行时二进制。依赖安装严格位于本 Skill 的 `runtime/<platform>/`：

这里的“依赖”指 Skill 管理的 Python、CMake、Ninja、libclang 和 DOM 测试依赖；目标 SDK 的编译器、系统头文件和 sysroot 属于分析输入，安装器不会修改或伪造它们。

```powershell
.\setup.ps1
.\run.ps1 doctor
.\test-platform.ps1
```

```bash
./setup.sh
./run.sh doctor
./test-platform.sh
```

测试源码和发布包解耦，开发测试不再强制要求旧离线 ZIP。`--wheelhouse <目录>` 可离线安装 Python 依赖；完全离线安装还需预置对应平台的 `runtime/<platform>/node`。

## 历史离线压缩包

已经交付的完整包 `sdk-code-atlas-0.1.0.zip` 包含 Windows/Linux x64 Python、libclang、CMake、Ninja 和 Clang 内建头文件。它不是本仓库自动生成的 GitHub Source code ZIP，也尚未上传为 GitHub Release 附件。

完整包大小：185644032 bytes。
SHA-256：`56765d17f0705d79a932915c8556272fce979b2912d37ae5af0ccf5cdffad8d9`。

已有完整包时，可将其中的 `runtime/` 放到本仓库根目录；运行时逐文件校验清单在完整包内。Git 忽略 runtime 和发行压缩包，`scripts/package_release.py` 在打包时生成 runtime-manifest.json。

```bash
bash run.sh doctor
bash run.sh run --repo /path/to/sdk --out /path/to/cache \
  --interface sdk_entry --html /path/to/output/overview.html
bash run.sh selftest
```

Windows 和 Linux 均使用平台隔离运行时；分析 Linux SDK 时仍应在具有对应目标头文件与工具链的 Linux 主机执行。

## 分析命令

```bash
./run.sh run --repo /path/to/sdk --out /path/to/cache \
  --compdb /path/to/build/compile_commands.json \
  --interface sdk_entry --html /path/to/output/overview.html
```

分析完成后可单独查询锁或共享变量：

```bash
./run.sh locks --out /path/to/cache --object shared_counter
```

`-resource-dir` 指向兼容 Clang 的内建头文件根目录（其下有 include/），不是业务 include 目录。pip 的 libclang 动态库不代替这一组头文件。使用完整包 runtime 时脚本自动设置此路径。

只有 CMake 时省略 `--compdb`，通过 `--params params.json` 提供 TOP_DIR 等明确参数；脚本在分析目录配置 CMake。CMake 配置可能需要实际编译器进行探测。跨仓使用重复的 `--root`，独立子构建使用重复的 `--compdb`。

## 验证与限制

功能级测试及本轮实际平台结果见 [TEST_REPORT.md](TEST_REPORT.md)。调用目标保留 exact/may 和源码证据，解析失败的 TU 不沿用旧事实。

基础语义使用 libclang Python bindings；可选的 `atlas-semantic` 使用 Clang C++ API 提取 CFG。锁分析只证明源码位置上的共同词法锁；它不证明线程同时运行或完整 happens-before。字段敏感别名、指针副作用、条件变量、内核专用生命周期规则和正式 VS Code 扩展仍未实现。模型审阅由宿主 Agent 提供；脚本不内置模型或上传源码。
