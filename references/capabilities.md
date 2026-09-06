# 0.1 实现范围与设计差异

本压缩包包含可运行 Skill、确定性 Python 脚本、Clang C API 解析、离线查看器及测试。它是第一版验证原型，不是 v3.1 全部高级语义能力的交付声明。

| 能力 | 状态 |
|---|---|
| CMake 自己求值、显式 TOP_DIR 等参数、多个 compdb / 源码根 | 已实现；独立 ExternalProject 子构建仍可能需要 Agent 指定正确入口并单独配置 |
| Clang 函数/类型/字段/静态对象/直接调用 | 已实现，解析失败 TU 不导入事实 |
| 任意函数名进入、按直接依赖扩大 TU、向上候选定位 | 已实现；基于编译数据库和词法候选定位，scope 内查全，不保证所有间接调用者 |
| 重载区分、递归停止、调用路径首次分歧 | 已实现；CLI trace 返回分歧 ID，HTML 逐层分支选择 |
| 参数实参绑定、局部赋值/计算表达式、返回表达式 | 部分实现；路径不敏感 may 图，不是 SSA/完整可执行数据流 |
| 静态/全局对象、字段布局、源码引用与写入位置 | 已实现基础记录；字段写入基对象可能保守扩大 |
| 注册/注销、ko 初始化、ioctl 对接、寄存器语义规则 | 尚未实现专用规则；源码调用和赋值仍提取，不冒充完整生命周期 |
| 完整 CFG、别名固定点、跨函数返回值计算、约束可行性 | 未实现；function_ir 输出 cursor operations 并明确 cfg_status=unsupported |
| Subagent 审阅交接、schema/证据验证、候选独立导入 | 已实现；模型由宿主 Agent 调用，脚本不自带模型服务 |
| commit / 脏文件依赖缓存、TU checkpoint、写者锁、原子发布 | 已实现；新文件采用保守失效，不只沿已有调用图 |
| 自然语言功能简介 | 优先源码文档注释，缺失显示待审阅；不凭函数名编造功能 |
| 黑盒函数、调用树、类型/对象框、证据、参数流、离线 HTML | 已实现原型界面，未实现正式 VSCode 扩展 |

## Clang 实现选择

本版通过官方 Clang C API 的 Python bindings（libclang 18.1.1）进行确定性语义提取，**没有另编译专用 C++ LibTooling 可执行程序**。这样可以把动态库随包分发。libclang 无法提供本设计要求的全部内部 CFG/高级 C++ 信息，因此相关能力明确标记未实现。后续专用 C++ 提取器可替换 extract.py，而不改变已发布 HTML 输入边界。

参考：[Clang 接口选择](https://clang.llvm.org/docs/Tooling.html)、[编译数据库](https://clang.llvm.org/docs/JSONCompilationDatabase.html)、[CMake 导出条件](https://cmake.org/cmake/help/latest/variable/CMAKE_EXPORT_COMPILE_COMMANDS.html)。

## 平台与运行前提

发行包包含 Windows x64 和 Linux glibc x64 的 Python、libclang、CMake、Ninja 及 Python 依赖。无需 pip 安装即可运行 launcher。Windows 分支尚未在 Windows 主机执行验证；Linux ARM64、musl、32 位系统不在本版打包范围。

包内运行时不等于目标 SDK：业务源码/生成头、系统头、目标 sysroot/编译器仍须由项目环境提供。CMake 配置若需要编译探测，需可用项目编译器。只提供编译数据库时可绕过配置，但不能绕过真正缺失的声明和 ABI 环境。MSVC-style cl/clang-cl 参数及 response files 当前明确拒绝，不静默丢弃。

参数 JSON 的内容视为用户显式配置；它不自动证明真实产品配置。对语义替代先说明影响并获得用户回答，再写入配置。未来可扩充 assumptions 协议；本版不会自动应用模型配置补丁。
