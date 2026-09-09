# 测试方法

Windows：`runtime/windows-x86_64/venv/Scripts/python.exe scripts/run_feature_test.py advanced-alias-concurrency`

Linux/WSL：`runtime/linux-x86_64/venv/bin/python scripts/run_feature_test.py advanced-alias-concurrency`

全量 Windows：`test-platform.ps1`

文档契约：设置 `PYTHONPATH=scripts` 后运行 `scripts/check_docs.py`。
