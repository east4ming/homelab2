"""pytest 全局配置 — 设置 sys.path 使测试脚本可导入 lib 包."""

import sys
from pathlib import Path

# 将 tests/ 目录加入 sys.path，使 `from lib.common import ...` 可用
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
