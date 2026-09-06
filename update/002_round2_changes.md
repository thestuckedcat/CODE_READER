# 第 2 轮 v0.3：Clang CFG 与标量参数计算链

日期：2026-09-06。前置 commit：a7d4e5ffb87995d153ac8a3de38e844688f03d30。

本轮交付原生 C++/Clang CFG 提取器、Python 到达定义求解器、跨函数返回依赖摘要、按调用位置隔离的参数/返回查询、独立缓存和 HTML 入口。**已实现的是标量分析子集，不是任意 C/C++ 程序的完整数据流证明。**

首版状态见 [000](000_v0.1_capabilities.md)，第一轮接入/调用链见 [001](001_round1_changes.md)。本文件是第二轮新增产物、支持边界和验证的权威说明；原总体设计保留规划依据。

## 1. 本轮能力与验收矩阵

| ID | 功能 | 状态 / 支持范围 | 验证方法 | 预期结果 | 实际结果 |
|---|---|---|---|---|---|
| R2-01 | C++/Clang 原生提取器、Python 驱动 | 已完成 Linux Clang 18 子集 | scripts/build_native.py 真实编译；原生失败注入 | 输出结构化 CFG；失败不伪造 CFG；基础调用事实可保留 | 通过；Windows 未编译验证 |
| R2-02 | 分支、汇合、循环、跳转 CFG | 部分完成：结构来自真实 Clang CFG；隐式清理/异常值语义未求解 | if、for、while、do、switch、break、continue、goto、early return、短路/三目 | 控制边保留；不可达 return 不进入值图；循环固定点或明确截断 | 测试通过；不声称路径可行性或终止性已证明 |
| R2-03 | 标量定义—使用、覆盖赋值 | 已完成所列子集 | x=input; x=0; consume(x)；分支赋值；复合赋值/自增减 | input 不流入被覆盖后的 consume；保留有条件的多个来源 | 通过 |
| R2-04 | 跨函数参数/返回摘要 | 部分完成：静态唯一直接目标、标量依赖、递归组依赖固定点 | 两层算术返回；同函数两个调用位置；递归 | 返回结果按本 callsite 的实参绑定；递归不无限展开 | 通过；递归值和终止性仍 unknown；指针副作用不求解 |
| R2-05 | 从参数/返回值/中间值请求 | 部分完成：形参名/序号/ID、返回值及 value ID；字段路径待第 3 轮 | CLI flow、void 参数向下展开、HTML 按钮 | 返回来源链/参数去向；调用上下文有独立绑定；查询预算可见 | 通过；不支持输入具体数值后的路径裁剪 |
| R2-06 | CFG/局部求解/摘要增量 | 已完成基础子集，失效仍保守 | 无变化复跑；修改另一 TU 的 leaf；与 fresh 对照 | 复用 AST/CFG/局部解/摘要；leaf 返回变化使 top 摘要失效；unrelated 复用 | 通过；后续别名/规则/Agent 缓存仍待实现 |

第一轮的规则保持：头文件由真实 include 顺序决定；下游停止在 Linux/glibc/未找到实现；上游没有已知调用者时显示最上端。

## 2. 为什么新加一个原生工具

libclang C API 继续负责已实现的函数、类型、对象和调用事实。它的游标表达式列表不是完整 CFG。本轮使用 Clang C++ API 的 `CFG::buildCFG` 导出控制流，不通过正则重建 if/for，也不解析编译器面向人的文字 dump。

新增 `native/extractor.cpp` / `native/CMakeLists.txt`：

- 读取 Python 给出的单 TU 请求：file、directory、规范化 arguments、已识别函数的 file/start/id。
- 使用 FixedCompilationDatabase 和 ClangTool，在同一配置下重新解析该 TU。
- 只导出与已识别业务函数匹配的函数。未匹配的模板/宏等情况由 Python 补为 unsupported，不能静默消失。
- 输出真实 entry/exit、basic blocks、CFGStmt 顺序、successor ordinal、可达性、条件表达式、case/default 标签和隐式 CFG 元素种类。
- 表达式另成表：引用的声明 USR、实参、运算符、初始化、返回、类型及源码位置。不支持的表达式仍有 kind/text/location。
- 任一原生编译错误返回失败；本阶段不导入其半成品。基础 libclang 阶段若成功，调用链可以继续发布，CFG 标记失败。

Python 加上源码哈希，使新值节点的来源可追溯。普通调用链默认不触发这个第二次解析。

## 3. Python 求解方式

### 3.1 每个赋值是独立的值节点

新增 `scripts/atlas/dataflow.py`。环境保存“变量 → 当前可能到达的定义集合”，而不是将同名变量的全部历史赋值连在一起。

```c
int x = input; // 定义 A
x = 0;         // 定义 B，杀死 x 的 A
consume(x);    // 读取 B；input 不再是这个实参的值来源
```

初始参数、常量、读取、计算、赋值、初始化、调用实参、调用结果和返回分别有 value ID。向前查询可看到参数曾赋给 A，但不会错误地由 A 连到最后的 consume。

### 3.2 分支和循环

按 CFG 入口运行工作队列。汇合点合并前驱定义集合；赋值替换目标标量的定义集合。节点数量固定，因此有限集合迭代可以收敛。最终值图在收敛后的 IN 状态上重新生成，避免发布迭代过程中的过期来源。

- Clang 标为不可达的边不会参与求解。
- 每个值节点记录 block，CFG 保留 condition_text、successor ordinal 和 label。普通布尔分支 ordinal 0/1 对应 Clang 的 true/false 顺序；switch 使用其目标标签，不能把所有两分支都当 if。
- `control_sources` 与普通 `sources` 分开。当前返回值的控制来源保守纳入函数内可达谓词，**不等于最小控制依赖集合**。
- 尚无 SAT/SMT 路径可行性求解、整数取值执行、溢出证明和循环终止证明；关系保持 may。
- `--flow-steps` 限制单函数工作队列步数。耗尽时标记 fixed_point_budget_exhausted，不把中间值当作完整结论。

### 3.3 跨函数与调用位置隔离

摘要记录返回可能依赖的形参序号、计算内容指纹、限制和被调摘要指纹。调用结果只连接**这个调用位置自己的实参值节点**。

```c
int a = twice(input);
int b = twice(7);
return b; // 不依赖 input；不能通过共享 twice 的形参把 a/b 串起来
```

静态唯一的直接目标使用摘要；系统函数、未找到实现、间接/虚调用等结果保守依赖候选实参并记录 external_or_unresolved_return。没有实现时不展开系统内部。

递归调用组按强连通分量进行有限参数依赖求解。即使依赖已收敛，仍保留 recursive_value_not_proven；`--summary-steps` 耗尽时明确 partial。

查询产物 `call_expansions` 保留 context、callsite、形参到当前实参的 bindings。前向查询也可进入无返回值的函数，从它的形参继续向下；反向查询从被调函数返回值展开。递归上下文截断并标记，所有上下文共用查询节点预算。

## 4. 增量与 checkpoint

新增阶段分开缓存，开关 CFG 不要求丢掉旧调用链缓存：

| 阶段 | 缓存输入 | 复用 / 失效 |
|---|---|---|
| libclang 事实 | 既有 TU 参数、文件依赖、搜索环境、提取代码 | 与第一轮一致 |
| 原生 CFG | TU、选定函数定位、实际源码/头依赖、原生二进制/驱动/共享库指纹 | 相同输入直接复用 cfg_ir；原生版本变化不复用旧 CFG |
| 到达定义 | 单函数 CFG、调用位置记录、求解器版本、步数预算 | 命中时直接读取局部解，不重跑工作队列 |
| 返回摘要 | 递归组的局部结果、直接目标集合、外部被调计算摘要指纹、求解器/预算 | 被调组先处理；缓存命中直接复用摘要，不先算一遍再比较 |
| 查询/HTML | 发布快照 | 只读发布值图，展开和导出不再次运行 Clang/Agent |

摘要缓存以递归组为单位 checkpoint。循环/摘要预算未收敛的结果不存为可复用成功 checkpoint。缓存对象哈希不符则重算相应阶段。

函数 ID 改为声明身份＋签名＋TU 身份，不再把函数体 token 加入 ID；实现修改不应使整个函数看起来被删除/新建。旧缓存会因提取代码指纹变化重建，旧快照保留其旧 ID。

当前仍可能保守扩大：源文件内容哈希改变会影响该文件内多个函数的证据；返回摘要保留被调组依赖，不保证失效集合理论最小。发现文件变化仍需要清点/核验源码；没有宣称完成全阶段 Git diff 驱动或第 5 轮全部恢复测试。

## 5. 新增中间文件与接口

所有阶段文件继续由 runs/<run>/artifacts.json 定位，内容保存于不可变 objects/；不要假定逻辑文件直接位于分析目录根。

| 逻辑文件 | 作用 |
|---|---|
| native_tool.json | 二进制、编译版本、驱动及可发现的共享库指纹；未请求时 not_requested |
| cfg_ir.jsonl | 按 TU 输出函数 CFG、表达式表、状态；产物 origin=clang_native |
| native_parse_plan.json | 原生 TU 的 parse/reuse/failed 与缓存键 |
| reaching_definitions.json | 单函数局部值图、返回、条件、CFG、收敛与限制 |
| summary_component.json | 一个递归组的摘要和已绑定的调用结果；可独立 checkpoint |
| function_summaries.jsonl | 开 CFG 时为真实返回依赖摘要；关闭时保留旧版基础摘要 |
| value_graph.jsonl | 参数、定义、计算、实参、返回等值节点及来源 |
| dataflow_plan.json | 各函数局部求解/摘要的 solve/reuse，外部被调摘要指纹 |
| graph.json / export bundle 新字段 | value_nodes、return_summaries、cfgs、dataflow_status |

CLI `flow --function ...` 输出 start、direction、values、call_expansions、summaries、cfg、truncated 和能力状态。未请求 CFG 时会要求先运行，不偷偷用旧的路径不敏感图冒充新结果。旧 `--symbol` 对 CFG 参数可路由到新查询；有歧义时必须指定函数。旧快照仍可使用原基础查询。

本次 schema 保留 0.1，增加可选字段；native protocol 独立为 1，工具版本为 0.3.0。旧 HTML/数据不能因此自动获得新分析能力。

## 6. 安装、运行与范围

**源码仓库不包含原生二进制或 LLVM 开发运行时。** 原 v0.1 完整 ZIP 也不含本轮新增的 atlas-semantic。本轮没有重新制作 v0.3 离线发行包，不能声称旧 ZIP 解压即可使用 CFG。

在开发环境准备 C++ 编译器、LLVM/Clang 18 开发头、clang-cpp 共享库及 LLVM CMake 配置。然后：

```bash
python3 scripts/build_native.py --llvm-dir /usr/lib/llvm-18 --build-dir /tmp/atlas-native-build
bash run.sh doctor
bash run.sh run --repo /sdk --out /analysis --interface sdk_entry --dataflow cfg --html /result/view.html
bash run.sh flow --out /analysis --function sdk_entry --parameter input
bash run.sh flow --out /analysis --function sdk_entry
bash run.sh flow --out /analysis --function sdk_entry --value VALUE_ID --direction backward --budget 2000
```

构建脚本优先使用已有包内 CMake。`--output-dir` 可指定开发二进制目录；分析使用 `--native-extractor /path/atlas-semantic`。默认安装到当前平台 runtime/.../native/。开发二进制仍依赖 LLVM/系统共享库，跨机分发需要另行制作运行时包和平台验收。

`--dataflow off` 是默认值，保留第一优先级的轻量调用链体验；`--dataflow cfg` 明确请求增强分析。源代码运行也可用 `python scripts/sdk_atlas.py`，但需依赖已安装在该 Python 环境。

## 7. 验证记录

测试环境：Linux x86_64 / Ubuntu 24.04，GCC 13.3 编译原生工具，Clang C++ 18.1.3，现有包内 libclang 18.1.1 / CPython 3.12.14 / CMake 4.4.3。两个前端版本分别记录，不把它们视为同一二进制；未覆盖的语言特性不保证前端映射一致。

原生构建验证：使用已下载并解压的官方 Ubuntu LLVM/Clang 18 开发包作为 --llvm-dir，实际运行 build_native.py；CMake 配置、C++ 编译、链接、--version 均成功。未依赖正则 CFG 替代品。

测试命令：

```bash
bash run.sh selftest
bash run.sh run --repo tests/flow_fixture --out /tmp/flow-analysis --dataflow cfg --html /tmp/flow.html
NODE_PATH=/path/to/linkedom/node_modules node tests/test_flow_viewer.js /tmp/flow.html
```

- 32 项 Python/CMake/Clang 测试全部通过（46.068 秒，无跳过）：原 18 项＋本轮 14 项。缺原生工具时第二轮测试会显示 skipped，**不能把 skipped 当通过**。
- 覆盖：覆盖赋值、双 callsite、分支、早返回、循环/跳转、跨 TU 返回、三目/短路、不可达分支、指针未知、递归与预算、增量/fresh 对照、void 参数展开、原生失败、CLI 与 HTML 导出。
- 增量断言：不改代码时 libclang parsed=0、summary_iterations=0；改变 leaf 返回而不改签名，top 摘要重算、unrelated 摘要复用；新的标量依赖结果与 fresh 对照一致。不是完整全图/全语法一致性证明。
- HTML 使用 linkedom 执行真实处理器，验证参数计算链、实参继续展开、返回值来源。属于 DOM 行为验证，不等于真实浏览器布局或性能验收。

真实 llama.cpp commit：73a43d1f69345aee8bb186ef4b3172cef892f2e5。接口 llama_time_us，max-tu=3；与第一轮相同的显式阅读配置（CPU/OpenMP/CUDA 等关闭）。查到 llama_time_us → ggml_time_us，2 个业务函数、1 条调用关系。两 TU 的原生 CFG 均解析成功；ggml_time_us 涉及 timespec 字段和指针输出，本轮正确保留 memory/MemberExpr 等限制，整体 partial。该测试不证明真实 SDK 的结构体数据流已完成。代码与工具固定后的复跑：基础事实 parsed=0/reused=2，原生 CFG 两 TU 均 reuse，两个局部解及两个返回摘要均 reuse，摘要求解迭代为 0。

## 8. 尚未完成及后续优先项

1. 字段敏感分析、指针别名、跨函数内存副作用、回调/虚调用完整目标，留第 3 轮。
2. 路径可行性、精确控制依赖、具体数值代入、全部 C/C++ 求值顺序、异常/析构/协程/模板的完整语义；不支持项必须保持限制。
3. Agent 对新数据流问题的自动分组审阅闭环未增加；本轮提供确定性状态/证据，不让模型覆盖 Clang 事实。
4. Linux 注册/事件/ioctl/MMIO 规则仍未开始；不会为了计算链深入 Linux/glibc 实现。
5. Windows 实机、跨机原生运行时封装、全阶段损坏恢复、真实浏览器与大图性能、VSCode 插件仍未完成。

依据：Clang 官方 [LibTooling](https://clang.llvm.org/docs/LibTooling.html)、[Compilation Database](https://clang.llvm.org/docs/JSONCompilationDatabase.html)。原生 API 实现以实际编译通过的 Clang 18 头文件为准。
