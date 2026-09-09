# 测试方法

Windows：`runtime/windows-x86_64/venv/Scripts/python.exe scripts/run_feature_test.py virtual-dispatch-analysis`

Linux/WSL：`runtime/linux-x86_64/venv/bin/python scripts/run_feature_test.py virtual-dispatch-analysis`

全量 Windows：`test-platform.ps1`

Viewer：全量平台脚本生成 fixture HTML，并以 DOM 测试展开 dispatch 的候选树。
