from typing import Dict, List, Any, Optional
from playwright.async_api import Page
import asyncio
import re

from .base_tester import BaseTester

class CommandInjectionTester(BaseTester):
    """命令注入漏洞测试模块"""
    
    def __init__(self, agent):
        super().__init__(agent)
        self.name = "command_injection"
        self.description = "命令注入漏洞测试"
        self.payloads = {
            "basic": [
                "ls",
                "pwd",
                "id",
                "whoami",
                "echo test"
            ],
            "concatenated": [
                "test;ls",
                "test|ls",
                "test||ls",
                "test&&ls",
                "test`ls`",
                "test$(ls)",
                "test;pwd;",
                ";ls;pwd;"
            ],
            "blind": [
                "`sleep 5`",
                "$(sleep 5)",
                ";sleep 5;",
                "| sleep 5",
                "& sleep 5 &",
                "&& sleep 5 &&",
                "|| sleep 5"
            ],
            "special_chars": [
                "|",
                ";",
                "&",
                "$(",
                "`",
                "||",
                "&&"
            ],
            "windows": [
                "dir",
                "type %WINDIR%\\win.ini",
                "echo %USERNAME%",
                "test&dir",
                "test|dir",
                "test||dir",
                "test&&dir"
            ]
        }
        self.detection_strings = {
            "unix": [
                "root:", 
                "bin:", 
                "/usr/bin", 
                "/home/",
                "uid=",
                "gid=",
                "/var/",
                "total ",
                "drwx",
                "-rwx"
            ],
            "windows": [
                "Volume in drive",
                "Directory of",
                "Volume Serial Number",
                "<dir>",
                "for 16-bit app support",
                "MSDOS",
                "WINDOWS"
            ]
        }
        self.time_based_threshold = 4.5  # 秒，判断时间延迟的阈值
        
    async def test(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """执行命令注入测试"""
        self.test_results["status"] = "running"
        
        page = self.agent.page
        if not page:
            self.test_results["status"] = "error"
            self.record_test_result({
                "step": "init",
                "status": "error",
                "message": "浏览器页面未初始化"
            })
            return self.get_test_results()
        
        # 记录开始测试
        self.record_test_result({
            "step": "start",
            "status": "info",
            "message": f"开始命令注入测试，目标URL: {page.url}"
        })
        
        # 收集输入点
        input_points = await self.collect_input_points(page)
        
        if not input_points:
            self.record_test_result({
                "step": "input_collection",
                "status": "warning",
                "message": "未发现任何输入点"
            })
            self.test_results["status"] = "no_input_points"
            return self.get_test_results()
        
        self.record_test_result({
            "step": "input_collection",
            "status": "success",
            "message": f"发现 {len(input_points)} 个可能的输入点"
        })
        
        # 检测操作系统类型
        os_type = await self._detect_os_type(page)
        
        self.record_test_result({
            "step": "os_detection",
            "status": "info",
            "message": f"目标系统疑似: {os_type}"
        })
        
        # 选择合适的测试载荷
        test_payloads = self._select_payloads(os_type)
        
        # 测试每个输入点
        vulnerable_inputs = []
        
        for idx, input_point in enumerate(input_points):
            # 跳过不适合命令注入的输入类型
            if input_point["type"] in ["checkbox", "radio", "file", "button", "image", "submit", "hidden"]:
                continue
                
            # 进行命令注入测试
            is_vulnerable, payload = await self._test_input_point(page, input_point, idx, test_payloads, os_type)
            
            if is_vulnerable:
                vulnerable_inputs.append(input_point)
                
                # 记录漏洞
                self.record_vulnerability({
                    "input_point": input_point,
                    "vulnerability": "command_injection",
                    "payload": payload,
                    "os_type": os_type,
                    "details": f"该输入点存在命令注入漏洞"
                })
        
        # 更新测试状态
        if vulnerable_inputs:
            self.test_results["status"] = "vulnerable"
            self.record_test_result({
                "step": "summary",
                "status": "warning",
                "message": f"发现 {len(vulnerable_inputs)} 个存在命令注入漏洞的输入点"
            })
        else:
            self.test_results["status"] = "secure"
            self.record_test_result({
                "step": "summary",
                "status": "success",
                "message": "未发现命令注入漏洞"
            })
        
        return self.get_test_results()
    
    async def _detect_os_type(self, page: Page) -> str:
        """尝试检测目标系统的操作系统类型"""
        # 默认假设为Unix系统
        return "unix"
    
    def _select_payloads(self, os_type: str) -> Dict[str, List[str]]:
        """根据操作系统类型选择适当的测试载荷"""
        result = {
            "basic": self.payloads["basic"],
            "concatenated": self.payloads["concatenated"],
            "blind": self.payloads["blind"],
            "special_chars": self.payloads["special_chars"]
        }
        
        if os_type == "windows":
            # 替换基本命令和连接命令为Windows特定命令
            result["basic"] = self.payloads["windows"][:5]
            result["concatenated"] = self.payloads["windows"][5:]
        
        return result
    
    async def _test_input_point(self, page: Page, input_point: Dict[str, Any], idx: int, 
                               test_payloads: Dict[str, List[str]], os_type: str) -> tuple[bool, str]:
        """测试特定输入点是否存在命令注入漏洞"""
        selector = input_point["selector"]
        is_vulnerable = False
        vulnerable_payload = ""
        
        self.record_test_result({
            "step": f"testing_input_{idx}",
            "status": "info",
            "message": f"正在测试输入点: {input_point.get('name', '') or input_point.get('id', '') or selector}"
        })
        
        # 保存原始页面内容用于比较
        original_content = await self.get_page_text(page)
        
        # 1. 先测试特殊字符是否被过滤
        for char in test_payloads["special_chars"]:
            # 发送单个特殊字符
            await self._input_and_submit(page, selector, char)
            await asyncio.sleep(1)  # 等待页面响应
            
            # 检查是否触发了错误
            error_content = await self.get_page_text(page)
            
            # 检查是否存在命令执行错误提示
            if self._check_for_error_messages(error_content):
                self.record_test_result({
                    "step": f"testing_input_{idx}_special_chars",
                    "status": "info",
                    "message": f"特殊字符 '{char}' 可能触发了错误"
                })
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
        
        # 2. 测试基本命令
        for payload in test_payloads["basic"]:
            # 发送基本命令
            await self._input_and_submit(page, selector, payload)
            await asyncio.sleep(1)  # 等待页面响应
            
            # 获取响应内容
            response_content = await self.get_page_text(page)
            
            # 检查是否有命令执行的迹象
            if self._check_for_command_output(response_content, os_type, original_content):
                is_vulnerable = True
                vulnerable_payload = payload
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_basic",
                    "status": "warning",
                    "message": f"可能存在命令注入漏洞，载荷: '{payload}'"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["command_injection"]
                input_point["payload"] = payload
                
                # 返回到原始页面
                await page.go_back()
                await asyncio.sleep(1)
                
                return is_vulnerable, vulnerable_payload
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
        
        # 3. 测试连接命令
        for payload in test_payloads["concatenated"]:
            # 发送连接命令
            await self._input_and_submit(page, selector, payload)
            await asyncio.sleep(1)  # 等待页面响应
            
            # 获取响应内容
            response_content = await self.get_page_text(page)
            
            # 检查是否有命令执行的迹象
            if self._check_for_command_output(response_content, os_type, original_content):
                is_vulnerable = True
                vulnerable_payload = payload
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_concatenated",
                    "status": "warning",
                    "message": f"存在命令注入漏洞，载荷: '{payload}'"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["command_injection"]
                input_point["payload"] = payload
                
                # 返回到原始页面
                await page.go_back()
                await asyncio.sleep(1)
                
                return is_vulnerable, vulnerable_payload
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
        
        # 4. 测试盲注命令
        for payload in test_payloads["blind"]:
            # 记录开始时间
            start_time = await page.evaluate("() => performance.now()")
            
            # 发送延时命令
            await self._input_and_submit(page, selector, payload)
            
            # 等待一小段时间
            await asyncio.sleep(1)
            
            # 记录结束时间
            end_time = await page.evaluate("() => performance.now()")
            
            # 计算响应时间（毫秒转换为秒）
            response_time = (end_time - start_time) / 1000
            
            # 检查是否存在明显延迟
            if response_time > self.time_based_threshold:
                is_vulnerable = True
                vulnerable_payload = payload
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_blind",
                    "status": "warning",
                    "message": f"存在盲命令注入漏洞，载荷: '{payload}', 响应时间: {response_time:.2f}秒"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["command_injection_blind"]
                input_point["payload"] = payload
                
                # 返回到原始页面
                await page.go_back()
                await asyncio.sleep(1)
                
                return is_vulnerable, vulnerable_payload
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
        
        return is_vulnerable, vulnerable_payload
    
    def _check_for_command_output(self, content: str, os_type: str, original_content: str) -> bool:
        """检查页面内容中是否包含命令执行的输出"""
        # 确保内容与原始内容不同
        if content == original_content:
            return False
        
        # 根据操作系统类型选择检测字符串
        detection_strings = self.detection_strings["unix"]
        if os_type == "windows":
            detection_strings = self.detection_strings["windows"]
        
        # 检查是否包含任何特征字符串
        for string in detection_strings:
            if string in content:
                return True
        
        return False
    
    def _check_for_error_messages(self, content: str) -> bool:
        """检查页面内容中是否包含命令执行错误的提示"""
        error_patterns = [
            r"command not found",
            r"syntax error",
            r"unexpected token",
            r"unrecognized command",
            r"is not recognized as",
            r"<b>Warning</b>",
            r"<b>Error</b>",
            r"Fatal error",
            r"system error",
            r"sh:",
            r"bash:",
            r"cmd:",
            r"Exception",
            r"not found in PATH",
            r"\d+: No such file or directory"
        ]
        
        for pattern in error_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    async def _input_and_submit(self, page: Page, selector: str, value: str) -> None:
        """输入内容并提交表单"""
        try:
            # 清除原有内容
            await page.fill(selector, "")
            # 输入新内容
            await page.fill(selector, value)
            
            # 查找可能的提交按钮
            form = await page.query_selector(f"{selector} >> xpath=ancestor::form")
            
            if form:
                # 如果输入在表单中，查找表单的提交按钮
                submit_button = await form.query_selector('input[type="submit"], button[type="submit"], button:has-text("Submit"), button')
                if submit_button:
                    await submit_button.click()
                    return
            
            # 如果没有找到提交按钮，尝试按回车键
            await page.press(selector, "Enter")
            
        except Exception as e:
            # 忽略错误，表单提交可能会导致页面跳转
            pass
    
    async def verify_vulnerability(self, page: Page, input_selector: str, payload: str) -> Dict[str, Any]:
        """验证特定输入点是否存在命令注入漏洞"""
        result = {
            "vulnerable": False,
            "details": "",
            "payload": payload
        }
        
        # 保存原始内容
        original_content = await self.get_page_text(page)
        
        try:
            # 判断载荷类型
            if any(sleep_cmd in payload for sleep_cmd in ["sleep", "timeout"]):
                # 处理盲注类型
                start_time = await page.evaluate("() => performance.now()")
                
                # 注入载荷
                await self._input_and_submit(page, input_selector, payload)
                
                # 等待一小段时间
                await asyncio.sleep(1)
                
                # 获取结束时间
                end_time = await page.evaluate("() => performance.now()")
                
                # 计算响应时间（毫秒转换为秒）
                response_time = (end_time - start_time) / 1000
                
                if response_time > self.time_based_threshold:
                    result["vulnerable"] = True
                    result["details"] = f"验证成功，延时载荷执行，响应时间: {response_time:.2f}秒"
            else:
                # 处理普通命令注入
                await self._input_and_submit(page, input_selector, payload)
                
                # 等待页面响应
                await asyncio.sleep(1)
                
                # 获取响应内容
                injected_content = await self.get_page_text(page)
                
                # 自动检测操作系统类型
                os_type = "unix"
                if any(win_str in injected_content for win_str in self.detection_strings["windows"]):
                    os_type = "windows"
                
                # 检查是否有命令执行的迹象
                if self._check_for_command_output(injected_content, os_type, original_content):
                    result["vulnerable"] = True
                    result["details"] = f"验证成功，命令执行的输出被检测到"
        finally:
            # 返回到原始页面
            try:
                await page.go_back()
                await asyncio.sleep(1)
            except:
                pass
        
        return result 