from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from playwright.async_api import Page

class BaseTester(ABC):
    """漏洞测试基类"""
    
    def __init__(self, agent):
        self.agent = agent
        self.name = "base_tester"
        self.description = "基础测试模块"
        self.found_vulnerabilities = []
        self.test_results = {
            "status": "not_started",
            "details": [],
            "vulnerable_points": []
        }
    
    @abstractmethod
    async def test(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """执行测试，返回测试结果"""
        pass
    
    @abstractmethod
    async def verify_vulnerability(self, page: Page, input_selector: str, payload: str) -> Dict[str, Any]:
        """验证特定输入点是否存在漏洞"""
        pass
    
    async def collect_input_points(self, page: Page) -> List[Dict[str, Any]]:
        """收集可能的输入点"""
        # 如果有站点分析器，使用它收集输入点
        if hasattr(self.agent, 'site_analyzer') and self.agent.site_analyzer:
            await self.agent.site_analyzer.analyze_site(page)
            return self.agent.site_analyzer.get_input_points()
        
        # 否则使用基本方法识别输入点
        return await self._basic_input_detection(page)
    
    async def _basic_input_detection(self, page: Page) -> List[Dict[str, Any]]:
        """基本的输入点检测方法"""
        inputs = []
        
        # 检测输入框
        input_elements = await page.query_selector_all('input:not([type="hidden"]):not([type="submit"])')
        
        for i, input_el in enumerate(input_elements):
            input_type = await input_el.get_attribute('type') or 'text'
            input_name = await input_el.get_attribute('name') or ''
            input_id = await input_el.get_attribute('id') or ''
            
            # 创建选择器
            selector = f"#{input_id}" if input_id else f"[name='{input_name}']" if input_name else f"input:nth-of-type({i+1})"
            
            inputs.append({
                "id": input_id,
                "name": input_name,
                "type": input_type,
                "selector": selector,
                "is_vulnerable": False,
                "vulnerability_types": []
            })
        
        # 检测文本区域
        textarea_elements = await page.query_selector_all('textarea')
        
        for i, textarea_el in enumerate(textarea_elements):
            textarea_name = await textarea_el.get_attribute('name') or ''
            textarea_id = await textarea_el.get_attribute('id') or ''
            
            # 创建选择器
            selector = f"#{textarea_id}" if textarea_id else f"[name='{textarea_name}']" if textarea_name else f"textarea:nth-of-type({i+1})"
            
            inputs.append({
                "id": textarea_id,
                "name": textarea_name,
                "type": "textarea",
                "selector": selector,
                "is_vulnerable": False,
                "vulnerability_types": []
            })
        
        return inputs
    
    async def collect_forms(self, page: Page) -> List[Dict[str, Any]]:
        """收集表单"""
        # 如果有站点分析器，使用它收集表单
        if hasattr(self.agent, 'site_analyzer') and self.agent.site_analyzer:
            await self.agent.site_analyzer.analyze_site(page)
            return self.agent.site_analyzer.get_forms()
        
        # 否则使用基本方法识别表单
        return await self._basic_form_detection(page)
    
    async def _basic_form_detection(self, page: Page) -> List[Dict[str, Any]]:
        """基本的表单检测方法"""
        forms = []
        
        form_elements = await page.query_selector_all('form')
        
        for i, form_el in enumerate(form_elements):
            form_id = await form_el.get_attribute('id') or ''
            form_action = await form_el.get_attribute('action') or ''
            form_method = await form_el.get_attribute('method') or 'GET'
            
            # 创建表单选择器
            form_selector = f"form#{form_id}" if form_id else f"form:nth-of-type({i+1})"
            
            # 获取表单中的输入元素
            input_elements = await form_el.query_selector_all('input, textarea, select')
            
            inputs = []
            for j, input_el in enumerate(input_elements):
                input_type = await input_el.get_attribute('type') or 'text'
                input_name = await input_el.get_attribute('name') or ''
                input_id = await input_el.get_attribute('id') or ''
                
                # 创建输入选择器
                input_selector = f"#{input_id}" if input_id else f"[name='{input_name}']" if input_name else f"{form_selector} input:nth-of-type({j+1})"
                
                inputs.append({
                    "id": input_id,
                    "name": input_name,
                    "type": input_type,
                    "selector": input_selector
                })
            
            # 查找提交按钮
            submit_button = await form_el.query_selector('input[type="submit"], button[type="submit"]')
            submit_selector = ""
            if submit_button:
                submit_id = await submit_button.get_attribute('id') or ''
                submit_selector = f"#{submit_id}" if submit_id else f"{form_selector} input[type='submit'], {form_selector} button[type='submit']"
            
            forms.append({
                "id": form_id,
                "action": form_action,
                "method": form_method,
                "inputs": inputs,
                "selectors": {
                    "form": form_selector,
                    "submit": submit_selector
                }
            })
        
        return forms
    
    async def get_page_text(self, page: Page) -> str:
        """获取页面文本内容"""
        return await page.evaluate("""
            () => {
                return document.body.innerText;
            }
        """)
    
    def record_vulnerability(self, details: Dict[str, Any]) -> None:
        """记录发现的漏洞"""
        self.found_vulnerabilities.append(details)
        self.test_results["vulnerable_points"].append(details)
        self.test_results["status"] = "vulnerable"
        
    def record_test_result(self, details: Dict[str, Any]) -> None:
        """记录测试结果"""
        self.test_results["details"].append(details)
    
    def get_test_results(self) -> Dict[str, Any]:
        """获取测试结果摘要"""
        summary = {
            "name": self.name,
            "description": self.description,
            "status": self.test_results["status"],
            "vulnerabilities_found": len(self.found_vulnerabilities),
            "details": self.test_results["details"][:5],  # 只返回前5个详细信息
            "vulnerable_points": self.test_results["vulnerable_points"]
        }
        
        return summary 