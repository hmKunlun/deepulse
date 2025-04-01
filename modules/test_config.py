import os
import json
import argparse
from typing import List, Dict, Optional, Any

class TestConfig:
    """测试配置类，支持从命令行参数、配置文件和交互式配置中加载"""
    
    def __init__(self):
        self.target_url = ""  # 目标URL
        self.test_types = []  # 要执行的测试类型
        self.depth = 2  # 爬取深度
        self.auth_config = {}  # 认证配置
        self.exclusions = []  # 排除的URL模式
        self.custom_payloads = {}  # 自定义测试载荷
        self.concurrency = 1  # 并发测试数量
        self.timeout = 30  # 测试超时时间(秒)
        
    @classmethod
    def from_file(cls, config_file: str) -> 'TestConfig':
        """从配置文件加载配置"""
        # 创建默认配置
        config = cls()
        
        # 确保文件存在
        if not os.path.exists(config_file):
            print(f"[错误] 配置文件 {config_file} 不存在")
            return config
            
        # 尝试加载JSON配置
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            # 填充配置
            config.target_url = config_data.get('target_url', config.target_url)
            config.test_types = config_data.get('test_types', config.test_types)
            config.depth = config_data.get('depth', config.depth)
            config.auth_config = config_data.get('auth_config', config.auth_config)
            config.exclusions = config_data.get('exclusions', config.exclusions)
            config.custom_payloads = config_data.get('custom_payloads', config.custom_payloads)
            config.concurrency = config_data.get('concurrency', config.concurrency)
            config.timeout = config_data.get('timeout', config.timeout)
            
            print(f"[成功] 从 {config_file} 加载配置")
            
        except Exception as e:
            print(f"[错误] 加载配置文件 {config_file} 失败: {str(e)}")
            
        return config
        
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'TestConfig':
        """从命令行参数加载配置"""
        config = cls()
        
        # 填充基本配置
        config.target_url = args.url
        config.depth = args.depth
        config.timeout = args.timeout
        
        # 解析测试类型
        if args.tests == 'all':
            config.test_types = ["sql_injection", "xss", "csrf", "file_upload", "command_injection"]
        else:
            # 将逗号分隔的测试类型转换为列表
            test_types = args.tests.split(',')
            # 标准化测试类型名称
            test_mapping = {
                'sql': 'sql_injection',
                'xss': 'xss',
                'csrf': 'csrf',
                'file': 'file_upload',
                'upload': 'file_upload',
                'cmd': 'command_injection',
                'command': 'command_injection'
            }
            # 映射测试类型
            config.test_types = []
            for test in test_types:
                test = test.lower().strip()
                if test in test_mapping:
                    config.test_types.append(test_mapping[test])
                else:
                    config.test_types.append(test)
        
        # 解析认证信息
        if args.auth:
            try:
                # 期望格式为 username:password
                username, password = args.auth.split(':', 1)
                config.auth_config = {
                    'username': username,
                    'password': password
                }
            except Exception:
                print("[警告] 认证信息格式错误，期望 'username:password'")
        
        return config
    
    @classmethod
    def from_interactive(cls) -> 'TestConfig':
        """通过交互式问答获取配置"""
        config = cls()
        
        print("===== 通用Web站点渗透测试配置 =====")
        
        # 获取目标URL
        config.target_url = input("请输入目标URL [http://localhost:3000/]: ")
        if not config.target_url:
            config.target_url = "http://localhost:3000/"
        
        # 获取测试类型
        print("\n可用的测试类型:")
        print("1. SQL注入 (sql)")
        print("2. 跨站脚本 (xss)")
        print("3. 跨站请求伪造 (csrf)")
        print("4. 文件上传漏洞 (file)")
        print("5. 命令注入 (cmd)")
        print("6. 全部测试 (all)")
        test_choice = input("请输入要执行的测试类型编号，多个类型用逗号分隔 [6]: ")
        
        if not test_choice or test_choice == '6' or test_choice.lower() == 'all':
            config.test_types = ["sql_injection", "xss", "csrf", "file_upload", "command_injection"]
        else:
            # 解析测试类型
            choices = test_choice.split(',')
            type_mapping = {
                '1': 'sql_injection',
                '2': 'xss',
                '3': 'csrf',
                '4': 'file_upload',
                '5': 'command_injection'
            }
            config.test_types = [type_mapping.get(c.strip(), 'sql_injection') for c in choices if c.strip() in type_mapping]
        
        # 获取认证信息
        need_auth = input("\n目标网站需要认证吗? (y/n) [n]: ").lower()
        if need_auth in ('y', 'yes'):
            username = input("请输入用户名: ")
            password = input("请输入密码: ")
            if username:
                config.auth_config = {
                    'username': username,
                    'password': password
                }
        
        # 获取爬取深度
        depth_input = input("\n请输入爬取深度 [2]: ")
        if depth_input.isdigit():
            config.depth = int(depth_input)
        
        # 获取超时时间
        timeout_input = input("\n请输入测试超时时间(秒) [30]: ")
        if timeout_input.isdigit():
            config.timeout = int(timeout_input)
        
        # 确认配置
        print("\n=== 配置摘要 ===")
        print(f"目标URL: {config.target_url}")
        print(f"测试类型: {', '.join(config.test_types)}")
        print(f"爬取深度: {config.depth}")
        print(f"超时时间: {config.timeout}秒")
        if config.auth_config:
            print(f"认证: {config.auth_config['username']}:{'*' * len(config.auth_config['password'])}")
        
        confirm = input("\n确认以上配置? (y/n) [y]: ").lower()
        if confirm not in ('n', 'no'):
            print("配置已确认，开始测试...")
        else:
            print("配置已取消，请重新开始...")
            return cls.from_interactive()
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            'target_url': self.target_url,
            'test_types': self.test_types,
            'depth': self.depth,
            'auth_config': self.auth_config,
            'exclusions': self.exclusions,
            'custom_payloads': self.custom_payloads,
            'concurrency': self.concurrency,
            'timeout': self.timeout
        }
    
    def to_file(self, file_path: str) -> bool:
        """保存配置到文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2)
            print(f"[成功] 配置已保存到 {file_path}")
            return True
        except Exception as e:
            print(f"[错误] 保存配置到 {file_path} 失败: {str(e)}")
            return False 