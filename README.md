# CODE_READER · SDK Code Atlas 0.1

C/C++ Linux SDK 阅读工具的第一版 Skill 原型：CMake 求值 → Clang 语义提取 → Python 图分析与增量缓存 → 宿主 Agent 审阅 → 离线 HTML。

## 从哪里开始

- 开发计划与验收矩阵：[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)
- Skill 入口：[SKILL.md](SKILL.md)
- 当前可用能力及限制：[references/capabilities.md](references/capabilities.md)
- 操作说明：[references/workflow.md](references/workflow.md)
- 总体设计 v3.1：[references/design-v3.1.md](references/design-v3.1.md)
- 中间文件映射：[references/artifacts.md](references/artifacts.md)
- 测试报告：[TEST_REPORT.md](TEST_REPORT.md)
- 示例：下载 [examples/fixture-overview.html](examples/fixture-overview.html) 后用浏览器打开。

## 仓库与离线压缩包

本仓库保存 Skill、Python 源码、查看器、文档和测试，不提交第三方运行时二进制。

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

Windows 完整包使用 `run.ps1`。Windows 分支尚未在 Windows 主机实测；推荐在代码所在 Linux 云主机执行分析。

## 仅从源码运行

需要 Python 3.12、项目编译环境及目标头文件。建议在独立 Python 虚拟环境中安装：

```bash
python -m pip install -r requirements.txt
python scripts/sdk_atlas.py doctor
python scripts/sdk_atlas.py run --repo /path/to/sdk --out /path/to/cache \
  --compdb /path/to/build/compile_commands.json \
  --clang-arg=-resource-dir=/path/to/llvm/lib/clang/18 \
  --interface sdk_entry --html /path/to/output/overview.html
```

`-resource-dir` 指向兼容 Clang 的内建头文件根目录（其下有 include/），不是业务 include 目录。pip 的 libclang 动态库不代替这一组头文件。使用完整包 runtime 时脚本自动设置此路径。

只有 CMake 时省略 `--compdb`，通过 `--params params.json` 提供 TOP_DIR 等明确参数；脚本在分析目录配置 CMake。CMake 配置可能需要实际编译器进行探测。跨仓使用重复的 `--root`，独立子构建使用重复的 `--compdb`。

## 验证与限制

7 组真实 Clang/CMake 回归测试通过；llama.cpp 固定版本完成有预算的接口分析。调用目标保留 exact/may 和源码证据，解析失败的 TU 不沿用旧事实。

当前使用 libclang Python bindings，不是专用 C++ LibTooling 提取器。完整 CFG、别名固定点、内核专用生命周期规则尚未实现，字段流为部分实现。模型审阅由宿主 Agent 提供；脚本不内置模型或上传源码。
