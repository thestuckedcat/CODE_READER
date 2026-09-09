# CODE_READER · SDK Code Atlas 0.8

C/C++ Linux SDK 阅读工具的第一版 Skill 原型：CMake 求值 → Clang 语义提取 → Python 图分析与增量缓存 → 宿主 Agent 审阅 → 离线 HTML。

当前源码 v0.8：在高级别名与并发分析基础上新增证据化 C++ 类继承关系和虚调用候选闭包，区分开放世界候选、`final` 封闭集合和显式限定静态调用；文档反合检查覆盖全部 Markdown。旧 v0.1 离线包不包含这些后续能力。

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
- v0.6 字段别名与回调候选：[do_func/12-field-alias-analysis/README.md](do_func/12-field-alias-analysis/README.md)
- v0.7 高级别名与并发分析：[do_func/13-advanced-alias-concurrency/README.md](do_func/13-advanced-alias-concurrency/README.md)
- v0.8 虚调用与继承候选：[do_func/14-virtual-dispatch-analysis/README.md](do_func/14-virtual-dispatch-analysis/README.md)
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
./run.sh aliases --out /path/to/cache --object shared_pair
```

`-resource-dir` 指向兼容 Clang 的内建头文件根目录（其下有 include/），不是业务 include 目录。pip 的 libclang 动态库不代替这一组头文件。使用完整包 runtime 时脚本自动设置此路径。

只有 CMake 时省略 `--compdb`，通过 `--params params.json` 提供 TOP_DIR 等明确参数；脚本在分析目录配置 CMake。CMake 配置可能需要实际编译器进行探测。跨仓使用重复的 `--root`，独立子构建使用重复的 `--compdb`。

## 验证与限制

功能级测试及本轮实际平台结果见 [TEST_REPORT.md](TEST_REPORT.md)。调用目标保留 exact/may 和源码证据，解析失败的 TU 不沿用旧事实。

基础语义使用 libclang Python bindings；可选的 `atlas-semantic` 使用 Clang C++ API 提取 CFG。虚派发只枚举已解析继承图中的签名匹配方法；非 `final` 类型始终保留开放世界未知候选。锁分析只证明源码位置上的共同锁，包括无分支简单包装函数的调用点投影；字段别名覆盖有限传播、保守多目标集合和嵌套成员路径。跨函数回调生命周期、线程重叠、完整 happens-before、任意指针副作用、条件变量、内核专用规则和正式 VS Code 扩展仍未实现。
