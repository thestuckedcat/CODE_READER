# 第 1 轮 v0.2：工程接入与轻量接口调用链

日期：2026-09-06。前置源码基线：2a6828a20628a94661b350cdb6a171481d0ab492。
首版能力快照：[000_v0.1_capabilities.md](000_v0.1_capabilities.md)。本轮所有新增说明文件均放在 update/；原设计文档和初始计划保留历史基线，README/Skill 链接到本文件获取最新状态。

## 1. 本轮采用的用户边界

- 同名头文件不另行猜测或让用户挑选：以 CMake 求值后生成的编译参数为准，Clang 决定真正包含哪个文件，并保存实际依赖。
- 向下停止于 Linux/glibc/系统库函数，或在本次工作区查询中未找到实现的函数。不要求补齐操作系统和标准库实现。
- 若 Linux/glibc 源码也在工作区，使用 --linux-root / --glibc-root 显式声明边界路径；不因 SDK 自己的函数恰好叫 malloc 而把它当系统库。
- 向上到没有已知调用者的函数即可，该函数是本条链的最上端；不额外猜测唯一 SDK 入口。
- 解析失败、预算耗尽、间接目标未知分别显示，不能把尚未完成的查询标成已经查完但未找到。
- 编译器默认生成的特殊成员函数没有可展开的源码实现，标记 implicit_special_member 后停止；不把构造函数名字当普通业务函数继续扫描全仓。

## 2. 支持功能、完成情况与验收

“已验证”仅指这里列出的场景，不扩张为任意 CMake/C++ 程序都保证解析成功。

| 计划 ID | 本次支持功能 | 是否完成 / 范围 | 验证方法 | 预期结果 | 实际结果 |
|---|---|---|---|---|---|
| R1-01 | 工具、项目配置、源码依赖分层诊断 | 已实现并验证基础层；Windows 主机未验证 | doctor、缺 TOP_DIR、缺业务头回归 | 工具可用不代表项目齐全；配置问题与 TU 解析问题分开保留 | 通过；不会切换为 grep 事实 |
| R1-02 | 上层 add_subdirectory 关系发现、真实 CMake 求值、独立子构建入口 | 已验证直接上层引用及显式子构建 | test_parent_configuration_parameters_and_generated_header / test_independent_externalproject_child | 自动识别直接上层 CMake；记录实际展开关系；独立子构建可单独求值 | 通过；ExternalProject 不自动下载、编译或假定顶层 compdb 覆盖全部 |
| R1-03 | 参数持久化、集中缺项、用户接受的替代配置 | 已实现并验证 | test_explicit_parameters_and_assumptions；上层配置重跑 | TOP_DIR 等明确缺项可见；已答参数复用；假设必须与传入值一致 | 通过；Agent 负责阅读复杂 CMake 和提出有证据的值，不自动编造配置 |
| R1-04 | 跨仓源码/include 路径、同名头顺序、TU 变体、生成头、响应文件 | 已验证 Linux/GCC-style 场景 | 同名 a/config.h、b/config.h 调换顺序；双变体；跨仓头修改；生成 config.h；@flags.rsp | Clang 选择正确字段；变体不混合；跨仓依赖改变重解析对应 TU | 通过；Windows response quoting、MSVC-style 参数仍不支持 |
| R1-05 | 持久候选文件索引、接口/头内 inline 进入、按需 TU 展开 | 已实现并验证 | test_header_inline_discovery_and_budget；轻量/全量对照；llama.cpp | 只解析查询相关候选；无关 TU 不解析；搜索和截断有记录 | fixture 接口仅 2 个相关 TU；header inline 仅 1 个；llama.cpp 指定接口仅 1 个 |
| R1-06 | 首次分歧、最上端、独立 callsite 路径、递归与停止原因 | CLI 与 DOM 行为已验证；真实浏览器布局待后续 | test_lightweight_boundaries_topmost_and_callsite_paths；递归对照；tests/test_viewer.js | 两次调用不丢 callsite；up 返回 top；系统边界和未找到实现可区分 | 通过；不保证函数指针的所有运行时调用者 |
| R1-07 | 配置复用、文件索引复用、TU 缓存与重算原因 | 已验证本轮基础分析层 | 旧版 7 组回归、跨仓头更新、重复调用、include 环境变更 | 无改动不重解析；依赖改变只重算相关 TU；新文件可保守扩大 | 通过；CFG/规则/完整 Agent 缓存属于后续阶段 |

增加了 target 的精确匹配和 CMake File API 所描述的 target 依赖闭包：选择 sdk 不会误选 sdk_extra，但会纳入 target_link_libraries 明确依赖的 dep。只有外部 compdb 且没有 File API 关系时，不虚构 target 依赖；可不使用 --target 或补充正确 CMake 上下文。

## 3. 实现思路与模块变化

### 配置层

新增 scripts/atlas/configuration.py：

1. 发现仓库入口及可证明的父级 add_subdirectory 引用。复杂变量构造的父级关系保留为候选，交给 Agent 阅读并通过 --cmake-root 指定。
2. 按 CMake 入口保存用户参数；已提供值在同一分析目录中继续有效。
3. 执行 CMake 自身求值，使用 JSON trace 记录 include/add_subdirectory/configure_file/ExternalProject 调用，使用 File API 读取配置输入与 target 依赖。
4. 保存配置输入、输出和相关环境指纹。输入/输出/工具/环境和文件集合未变化时复用配置；不是每次从零配置。
5. 独立 ExternalProject 子构建由 --child-cmake-root 明确选定。其上层专有参数或语义不明确时继续生成缺项；不以空函数绕过配置。

CMake 执行仍可能运行项目配置代码或编译探测，分析目录并非沙箱。这个流程不要求完整构建 SDK，也不承诺没有目标编译器时所有 CMake 都能求值。

### 候选定位层

新增 scripts/atlas/search.py：按文件内容缓存 token、定义提示和 include 引用，并构建 TU 候选索引。普通头内 inline 也可被定位。文本提示仅决定哪些 TU 值得交给 Clang；它不产生调用事实。宏 include 无法静态展开时保守扩大候选并记录状态。

每次更新仍需枚举文件/核验内容以发现变化；不会为每个待查函数重复读取全仓并执行 grep。未变文件复用候选索引，实际 Clang 结果继续按 TU 依赖缓存。新文件与负向 include 查找仍采用保守失效，不承诺最小失效集合。

### 语义与边界层

新增 scripts/atlas/boundaries.py；提取器为 callsite 记录声明位置、可见定义位置、边界类别以及 TU/build 身份。业务源/include 根优先保留为业务代码，系统分类不靠函数名字匹配。

函数及类型记录保留 TU 变体。合并目标时优先使用同 TU 定义，再使用同构建上下文；多个仍可能成立的定义保持候选。选定接口存在多个身份时输出 interface_choices.json，由用户使用 --select-function 或 --unit 选择。

修复 merge 对原始 callsite 的原地修改，避免反复求解改变问题输入哈希。Clang 原始事实与派生字段仍分开。

### 图查询与 HTML

trace 返回每条路径的函数 ID 和 callsite 序列，新增 top_functions 与具体终止原因。HTML 增加“首次分歧 / 最上端”入口、可点击候选和停止原因说明。浏览器函数路径选择会折叠相同函数序列；CLI 保留不同调用位置的独立路径。HTML 仍只读取 Python 发布的 export bundle，不自行运行 Clang 或 Agent。

## 4. 本轮中间产物

| 产物 | 内容 / 用途 |
|---|---|
| doctor.json | 工具可用性与配置/源码依赖检查分层 |
| cmake_discovery.json | 选定入口、父级候选、变量使用位置 |
| parameters.json / assumptions.json | 明确用户值、缓存来源、已接受的替代及原因 |
| configuration_questions.json | 缺项列表、证据位置、错误诊断与下一步操作 |
| configure_request/result.json | 求值命令、日志或配置复用状态 |
| *.cmake-trace.jsonl | CMake 自身的展开轨迹；保存在当前 run |
| cmake_relations.json | include/add_subdirectory/configure_file/ExternalProject 的求值记录 |
| generated_files.json | 配置生成记录、构建目录实际生成的头/源码及内容哈希 |
| build_context.json | 编译命令、target、参数、配置和 TU 变体 |
| candidate_index.json / search_queries.json | 候选索引复用数量、查询范围、待确认 TU |
| interface_choices.json | 多个函数或编译变体时的选择 ID |
| invalidation_plan.json | 每个 TU 的复用/重解析，changed_environment/search/code/dependency 等原因 |
| graph.json 的 boundaries / callsite.stop_reason | Linux、glibc、实现未找到、间接未知、失败、预算及默认生成函数边界 |

自有阶段产物仍通过 runs/<run>/artifacts.json 指向不可变内容对象；既有 JSON envelope 与 HTML 主输入不变。本轮添加可选字段，schema 仍为 0.1，工具版本升为 0.2.0。

## 5. 新命令和使用方式

复用首版完整包中的 runtime/。本轮源码仓库仍不提交大体积运行时；也没有声称已重新制作 v0.2 离线 ZIP。

```bash
# 普通接入；接口查询按需扩大
bash run.sh run --repo /sdk --out /analysis --interface sdk_entry --html /result/overview.html

# 上层配置；已回答的参数可在后续同一 out 中省略
bash run.sh run --repo /sdk/component --cmake-root /sdk/superbuild \
  --params /params.json --out /analysis --interface sdk_entry

# Agent 已确认某参数必需时，登记明确缺项
bash run.sh run --repo /sdk --out /analysis --require-param TOP_DIR

# 独立子构建，不自动下载或构建 ExternalProject
bash run.sh run --repo /superbuild --child-cmake-root /dependency/child \
  --params /params.json --out /analysis --interface sdk_entry

# 工作区含系统实现时指定停止根
bash run.sh run --repo /sdk --out /analysis --linux-root /sources/linux \
  --glibc-root /sources/glibc --interface sdk_entry

# 上溯后查询：返回没有已知调用者的最上端函数
bash run.sh run --repo /sdk --out /analysis --interface worker --direction up
bash run.sh trace --out /analysis --function worker --direction up

# 按 choices 中的实际 ID 选择；占位符需换成结果中的值
bash run.sh run --repo /sdk --out /analysis --interface sdk_entry --select-function FUNCTION_ID
```

--params 仍是简单 JSON 对象，例如 `{"TOP_DIR":"/work/sdk"}`。需要说明替代配置时，--assumptions 指向数组，例如：

```json
[{"name":"TOP_DIR","value":"/work/sdk","reason":"用户确认用此源码树作为阅读配置","accepted_by":"user"}]
```

替代值必须与参数文件/已确认参数一致；脚本不会自动把假设提案应用为真实产品配置。

## 6. 实际验证记录

运行环境：Linux x86_64，首版包内 CPython 3.12.14、libclang 18.1.1、CMake 4.4.3、Ninja 1.13.2。测试使用独立临时目录，包含路径空格。Windows 主机测试没有在本轮执行。

### 自动化回归

命令：`bash run.sh selftest`。结果：**18 个测试全部通过**（原 7 个 + 新 11 个）。执行入口改为 tests/run_tests.py 自动发现两组 Python 测试。

| 新测试 | 核心断言 |
|---|---|
| parent_configuration_parameters_and_generated_header | 父 CMake 函数可用；缺 TOP_DIR 后补齐；config.h 实际生成；重跑配置复用 |
| independent_externalproject_child | 顶层无 compdb 时停止说明；显式子构建配置后找到接口 |
| same_named_headers_variants_and_response_file | include 顺序决定字段；响应文件变化生效；两个 TU 变体要求选择 |
| lightweight_boundaries_topmost_and_callsite_paths | 只解析两个相关 TU；puts 在 glibc 停止；未找到实现停止；两个调用位置保留；上端为 top |
| system_source_roots_stop_even_if_implementation_available | 即使 Linux 实现源码存在也不继续展开 |
| cross_repository_header_dependency_and_exact_target | 跨仓声明/定义关联；依赖头改变使两个相关 TU 重解析；sdk 不误选 sdk_extra |
| header_inline_discovery_and_budget | 找到头内 inline；预算耗尽保留待处理 TU |
| explicit_parameters_and_assumptions | 精确缺项；接受的替代与参数一致并落盘 |
| interface_matches_full_reference_and_recursion | 同配置接口子图与全量参考对应边一致；递归终止 |
| business_symbol_name_is_not_system_boundary | 业务自定义 malloc 不因名字被当作 glibc |
| target_dependency_closure | sdk 纳入 File API 明确依赖的 dep，不纳入 unrelated |

原 7 组继续验证重载、类型/静态对象、参数绑定、1/2 单源增量、2/1 共享头增量、审阅版本/证据、失败移除旧事实、负向头依赖与 CPATH 变化。

### HTML DOM 行为

使用 linkedom 0.18.12 执行真实查看器 JavaScript 及事件处理器。通过搜索、函数详情、首次分歧、最上端、间接边界、对象展示断言。Node 语法检查通过。这是 DOM 逻辑验证，不等于实际浏览器布局或大图性能验证。

```bash
# linkedom 仅用于开发验证，用户打开 HTML 无需安装它
npm install --prefix /tmp/atlas-ui-test linkedom@0.18.12
bash run.sh run --repo tests/fixture --out /tmp/atlas-fixture --html /tmp/atlas-view.html
NODE_PATH=/tmp/atlas-ui-test/node_modules node tests/test_viewer.js /tmp/atlas-view.html
```

### llama.cpp 实际查询

仓库 commit：73a43d1f69345aee8bb186ef4b3172cef892f2e5。
接口：llama_model_default_params，max-tu=8，显式阅读配置为 GGML_CUDA/NATIVE/CPU/OPENMP、LLAMA_BUILD_TESTS/EXAMPLES/SERVER/CURL 均 OFF。

- 首次最终实现运行：1 个 TU 解析，1 个接口函数，无业务调用目标边；默认拷贝构造在 implicit_special_member 边界停止，未发生解析失败。
- 重复查询：0 个 TU 重新解析，1 个 TU 复用，run summary 为 succeeded。
- 该结果是指定接口的有界查询，不代表全仓调用链或高级数据流已完成。

## 7. 尚未承诺完成的范围

- 任意 superbuild 自动恢复：复杂入口仍需 Agent 根据诊断选择正确入口、子构建和参数，脚本不代替开发者决定产品配置。
- Windows 实机兼容、Windows response-file quoting、MSVC-style 参数、跨目标工具链的完整兼容矩阵。
- 宏生成函数/宏 include 可能扩大候选；函数指针、虚调用完整目标分析、CFG/别名固定点和 Linux 框架专用生命周期规则仍在后续轮次。
- 没有已知调用者即展示最上端，但不能保证它是运行时唯一入口；未完成预算和解析失败仍显示。
- 系统源码在业务工作区中时，需提供有依据的 Linux/glibc 根，不能仅按目录名或函数名猜测归属。
- 全阶段最细粒度增量、所有崩溃窗口恢复、真实浏览器布局/大图性能与正式 VSCode 插件没有在本轮宣称完成。

CMake 求值依据采用其官方 [File API](https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html) 和 [命令行 trace](https://cmake.org/cmake/help/latest/manual/cmake.1.html)；候选索引是本工具自己的定位策略，不能替代 Clang 的语义事实。
