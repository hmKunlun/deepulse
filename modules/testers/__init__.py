# testers包初始化
"""
Web漏洞测试模块集合
包含用于检测各种Web安全漏洞的测试类
"""

__version__ = '0.1.0'

# 导入各种测试模块
from .sql_injection import SQLInjectionTester
from .xss import XSSTester
from .command_injection import CommandInjectionTester
from .path_traversal import PathTraversalTester

# 映射表，将漏洞类型字符串映射到对应的测试类
TESTER_MAP = {
    "sql_injection": SQLInjectionTester,
    "xss": XSSTester,
    "command_injection": CommandInjectionTester,
    "path_traversal": PathTraversalTester
} 