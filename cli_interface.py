import os
import sys
import time
import asyncio
from typing import Dict, List, Optional
import colorama
from colorama import Fore, Back, Style
from modules.test_config import TestConfig

# 初始化colorama
colorama.init()

class DeePulse:
    """
    DeePulse命令行界面
    提供交互式菜单和用户输入功能
    """
    
    def __init__(self):
        """初始化DeePulse命令行界面"""
        self.config = TestConfig()
        self.running = True
        self.test_started = False
        self.last_result = None
        
        # 版本信息
        self.version = "1.0.0"
        
        # 用户自定义提示词设置
        self.user_prompt_enabled = False
        self.user_prompt_frequency = 3
        
        # 菜单选项
        self.main_menu_options = {
            "1": self.start_test,
            "2": self.configure_test,
            "3": self.load_config,
            "4": self.save_config,
            "5": self.view_results,
            "6": self.about,
            "7": self.configure_user_prompt,
            "0": self.exit
        }
        
    def display_banner(self):
        """显示应用程序横幅"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(Fore.CYAN + Style.BRIGHT + """
    ██████╗ ███████╗███████╗██████╗ ██╗   ██╗██╗     ███████╗███████╗
    ██╔══██╗██╔════╝██╔════╝██╔══██╗██║   ██║██║     ██╔════╝██╔════╝
    ██║  ██║█████╗  █████╗  ██████╔╝██║   ██║██║     ███████╗█████╗  
    ██║  ██║██╔══╝  ██╔══╝  ██╔═══╝ ██║   ██║██║     ╚════██║██╔══╝  
    ██████╔╝███████╗███████╗██║     ╚██████╔╝███████╗███████║███████╗
    ╚═════╝ ╚══════╝╚══════╝╚═╝      ╚═════╝ ╚══════╝╚══════╝╚══════╝
                                                                 v""" + self.version + """
    """ + Style.RESET_ALL)
        print(Fore.WHITE + Style.BRIGHT + "    AI网站安全测试工具" + Style.RESET_ALL)
        print(Fore.YELLOW + "    支持SQL注入、XSS、CSRF、文件上传、命令注入等多种漏洞测试\n" + Style.RESET_ALL)
        
    def display_main_menu(self):
        """显示主菜单"""
        print(Fore.GREEN + "\n=== 主菜单 ===" + Style.RESET_ALL)
        print(Fore.WHITE + "1. 开始漏洞测试")
        print("2. 配置测试参数")
        print("3. 加载配置文件")
        print("4. 保存当前配置")
        print("5. 查看测试结果")
        print("6. 关于DeePulse")
        print("7. 配置用户提示词功能")
        print(Fore.RED + "0. 退出程序" + Style.RESET_ALL)
        
    def run(self):
        """运行DeePulse命令行界面"""
        while self.running:
            self.display_banner()
            self.display_main_menu()
            
            # 显示当前配置状态摘要
            self._display_config_summary()
            
            choice = input(Fore.CYAN + "\n请选择操作 [0-7]: " + Style.RESET_ALL)
            
            action = self.main_menu_options.get(choice)
            if action:
                action()
            else:
                print(Fore.RED + "无效选择，请重试！" + Style.RESET_ALL)
                time.sleep(1.5)
                
    def _display_config_summary(self):
        """显示当前配置摘要"""
        print(Fore.YELLOW + "\n--- 当前配置摘要 ---" + Style.RESET_ALL)
        print(f"目标URL: {self.config.target_url or '未设置'}")
        
        if self.config.test_types:
            test_types_map = {
                "sql_injection": "SQL注入", 
                "xss": "跨站脚本", 
                "csrf": "跨站请求伪造",
                "file_upload": "文件上传", 
                "command_injection": "命令注入"
            }
            test_types = [test_types_map.get(t, t) for t in self.config.test_types]
            print(f"测试类型: {', '.join(test_types)}")
        else:
            print("测试类型: 全部")
            
        print(f"爬取深度: {self.config.depth}")
        
        if self.config.auth_config:
            print(f"认证: {self.config.auth_config.get('username', '')}:{self.config.auth_config.get('password', '').replace('*', '*')}")
        else:
            print("认证: 未配置")
        
        # 显示用户提示词设置
        prompt_status = "启用" if self.user_prompt_enabled else "禁用"
        print(f"用户提示词功能: {prompt_status}, 频率: 每{self.user_prompt_frequency}轮迭代")
        
    def start_test(self):
        """开始漏洞测试"""
        from main import run_automated_test
        
        if not self.config.target_url:
            print(Fore.RED + "\n错误: 未设置目标URL！请先配置测试参数。" + Style.RESET_ALL)
            time.sleep(2)
            return
            
        self.display_banner()
        print(Fore.GREEN + "\n=== 开始漏洞测试 ===" + Style.RESET_ALL)
        print(f"目标URL: {self.config.target_url}")
        
        if self.config.test_types:
            test_types_map = {
                "sql_injection": "SQL注入", 
                "xss": "跨站脚本", 
                "csrf": "跨站请求伪造",
                "file_upload": "文件上传", 
                "command_injection": "命令注入"
            }
            test_types = [test_types_map.get(t, t) for t in self.config.test_types]
            print(f"测试类型: {', '.join(test_types)}")
        else:
            print("测试类型: 全部")
            
        # 显示用户提示词功能状态
        if self.user_prompt_enabled:
            print(Fore.CYAN + f"用户提示词功能: 已启用，每{self.user_prompt_frequency}轮迭代询问一次" + Style.RESET_ALL)
        else:
            print(Fore.CYAN + "用户提示词功能: 已禁用" + Style.RESET_ALL)
            
        confirm = input(Fore.YELLOW + "\n确认开始测试? (y/n): " + Style.RESET_ALL).lower()
        
        if confirm in ('y', 'yes'):
            print(Fore.CYAN + "\n正在初始化测试环境..." + Style.RESET_ALL)
            try:
                self.test_started = True
                # 运行测试，传递当前配置和用户提示词设置
                asyncio.run(run_automated_test(
                    self.config,
                    user_prompt_enabled=self.user_prompt_enabled,
                    user_prompt_frequency=self.user_prompt_frequency
                ))
                print(Fore.GREEN + "\n测试完成！" + Style.RESET_ALL)
            except Exception as e:
                print(Fore.RED + f"\n测试过程中发生错误: {str(e)}" + Style.RESET_ALL)
                import traceback
                traceback.print_exc()
            finally:
                self.test_started = False
                input(Fore.YELLOW + "\n按Enter键返回主菜单..." + Style.RESET_ALL)
        
    def configure_test(self):
        """配置测试参数"""
        self.display_banner()
        print(Fore.GREEN + "\n=== 配置测试参数 ===" + Style.RESET_ALL)
        
        # 目标URL
        url = input(Fore.CYAN + f"请输入目标URL [{self.config.target_url or 'http://localhost:3000/'}]: " + Style.RESET_ALL)
        if url:
            self.config.target_url = url
        elif not self.config.target_url:
            self.config.target_url = "http://localhost:3000/"
            
        # 测试类型
        print(Fore.CYAN + "\n可用的测试类型:" + Style.RESET_ALL)
        print("1. SQL注入 (sql)")
        print("2. 跨站脚本 (xss)")
        print("3. 跨站请求伪造 (csrf)")
        print("4. 文件上传漏洞 (file)")
        print("5. 命令注入 (cmd)")
        print("6. 全部测试 (all)")
        
        # 当前选择的测试类型
        current_types = self.config.test_types or ["全部"]
        type_mapping = {
            "sql_injection": "1",
            "xss": "2",
            "csrf": "3",
            "file_upload": "4",
            "command_injection": "5"
        }
        current_choices = [type_mapping.get(t, "6") for t in self.config.test_types] if self.config.test_types else ["6"]
        
        test_choice = input(Fore.CYAN + f"请输入测试类型编号，多个用逗号分隔 [{','.join(current_choices)}]: " + Style.RESET_ALL)
        
        if test_choice:
            if test_choice == '6' or test_choice.lower() == 'all':
                self.config.test_types = ["sql_injection", "xss", "csrf", "file_upload", "command_injection"]
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
                self.config.test_types = [type_mapping.get(c.strip(), 'sql_injection') for c in choices if c.strip() in type_mapping]
                
        # 认证信息
        need_auth = input(Fore.CYAN + "\n目标网站需要认证吗? (y/n) [" + ("y" if self.config.auth_config else "n") + "]: " + Style.RESET_ALL).lower()
        if need_auth in ('y', 'yes') or (not need_auth and self.config.auth_config):
            username = input(Fore.CYAN + f"请输入用户名 [{self.config.auth_config.get('username', '')}]: " + Style.RESET_ALL)
            password = input(Fore.CYAN + f"请输入密码 [{self.config.auth_config.get('password', '')}]: " + Style.RESET_ALL)
            
            if username or self.config.auth_config.get('username'):
                self.config.auth_config = {
                    'username': username or self.config.auth_config.get('username', ''),
                    'password': password or self.config.auth_config.get('password', '')
                }
        elif need_auth in ('n', 'no'):
            self.config.auth_config = {}
            
        # 爬取深度
        depth_input = input(Fore.CYAN + f"\n请输入爬取深度 [{self.config.depth}]: " + Style.RESET_ALL)
        if depth_input.isdigit():
            self.config.depth = int(depth_input)
            
        # 超时时间
        timeout_input = input(Fore.CYAN + f"\n请输入测试超时时间(秒) [{self.config.timeout}]: " + Style.RESET_ALL)
        if timeout_input.isdigit():
            self.config.timeout = int(timeout_input)
            
        print(Fore.GREEN + "\n配置已更新!" + Style.RESET_ALL)
        time.sleep(1)
        
    def load_config(self):
        """加载配置文件"""
        self.display_banner()
        print(Fore.GREEN + "\n=== 加载配置文件 ===" + Style.RESET_ALL)
        
        config_file = input(Fore.CYAN + "请输入配置文件路径: " + Style.RESET_ALL)
        
        if not config_file:
            print(Fore.RED + "操作已取消" + Style.RESET_ALL)
            time.sleep(1)
            return
            
        if not os.path.exists(config_file):
            print(Fore.RED + f"错误: 文件 '{config_file}' 不存在!" + Style.RESET_ALL)
            time.sleep(2)
            return
            
        try:
            self.config = TestConfig.from_file(config_file)
            print(Fore.GREEN + f"\n成功加载配置文件: {config_file}" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"\n加载配置文件时出错: {str(e)}" + Style.RESET_ALL)
            
        time.sleep(2)
        
    def save_config(self):
        """保存当前配置"""
        self.display_banner()
        print(Fore.GREEN + "\n=== 保存当前配置 ===" + Style.RESET_ALL)
        
        if not self.config.target_url:
            print(Fore.RED + "\n错误: 当前配置不完整，请先配置测试参数。" + Style.RESET_ALL)
            time.sleep(2)
            return
            
        config_file = input(Fore.CYAN + "请输入保存文件路径 [config.json]: " + Style.RESET_ALL)
        
        if not config_file:
            config_file = "config.json"
            
        try:
            success = self.config.to_file(config_file)
            if success:
                print(Fore.GREEN + f"\n配置已成功保存到: {config_file}" + Style.RESET_ALL)
            else:
                print(Fore.RED + "\n保存配置失败" + Style.RESET_ALL)
        except Exception as e:
            print(Fore.RED + f"\n保存配置时出错: {str(e)}" + Style.RESET_ALL)
            
        time.sleep(2)
        
    def view_results(self):
        """查看测试结果"""
        self.display_banner()
        print(Fore.GREEN + "\n=== 测试结果 ===" + Style.RESET_ALL)
        
        if self.last_result:
            print(self.last_result)
        else:
            print(Fore.YELLOW + "暂无测试结果。请先运行测试。" + Style.RESET_ALL)
            
        input(Fore.CYAN + "\n按Enter键返回主菜单..." + Style.RESET_ALL)
        
    def about(self):
        """显示关于信息"""
        self.display_banner()
        print(Fore.GREEN + "\n=== 关于DeePulse ===" + Style.RESET_ALL)
        print(Fore.WHITE + """
DeePulse是一款功能强大的Web应用程序安全测试工具，AI全自动测试站点。
是的，计划是这样，可惜目前只是一个半成品，欢迎各位推送版本更新，如果要二开希望可以标注原项目地方，非常感谢！

开发团队: kunlun
版本: """ + self.version + """
        """ + Style.RESET_ALL)
        
        input(Fore.CYAN + "\n按Enter键返回主菜单..." + Style.RESET_ALL)
        
    def configure_user_prompt(self):
        """配置用户提示词功能"""
        self.display_banner()
        print(Fore.GREEN + "\n=== 配置用户提示词功能 ===" + Style.RESET_ALL)
        
        # 当前设置
        current_status = "启用" if self.user_prompt_enabled else "禁用"
        print(Fore.CYAN + f"当前状态: {current_status}" + Style.RESET_ALL)
        print(Fore.CYAN + f"当前频率: 每{self.user_prompt_frequency}轮迭代" + Style.RESET_ALL)
        
        # 配置是否启用
        print(Fore.YELLOW + "\n用户提示词功能允许您在测试过程中自定义提示词，指导AI的行为。" + Style.RESET_ALL)
        choice = input(Fore.CYAN + f"是否启用用户提示词功能? (y/n) [{current_status=='启用' and 'y' or 'n'}]: " + Style.RESET_ALL).lower()
        
        if choice:
            self.user_prompt_enabled = choice in ('y', 'yes')
        
        # 如果启用，配置频率
        if self.user_prompt_enabled:
            frequency = input(Fore.CYAN + f"每多少轮迭代询问一次用户输入? [当前: {self.user_prompt_frequency}]: " + Style.RESET_ALL)
            if frequency and frequency.isdigit() and int(frequency) > 0:
                self.user_prompt_frequency = int(frequency)
                
        print(Fore.GREEN + "\n用户提示词功能配置已更新!" + Style.RESET_ALL)
        time.sleep(1.5)
        
    def exit(self):
        """退出程序"""
        self.display_banner()
        print(Fore.YELLOW + "\n确定要退出DeePulse吗?" + Style.RESET_ALL)
        confirm = input(Fore.CYAN + "确认 (y/n): " + Style.RESET_ALL).lower()
        
        if confirm in ('y', 'yes'):
            print(Fore.GREEN + "\n感谢使用DeePulse! 再见!" + Style.RESET_ALL)
            self.running = False
            sys.exit(0)

# 当直接执行此文件时
if __name__ == "__main__":
    try:
        cli = DeePulse()
        cli.run()
    except KeyboardInterrupt:
        print(Fore.RED + "\n\n程序被中断" + Style.RESET_ALL)
        sys.exit(0)
    except Exception as e:
        print(Fore.RED + f"\n发生错误: {str(e)}" + Style.RESET_ALL)
        import traceback
        traceback.print_exc()
        sys.exit(1) 