from typing import List, Dict, Optional, Any
from playwright.async_api import Page
import re

class FormElement:
    """表单元素类"""
    def __init__(self, form_id: str = "", form_action: str = "", form_method: str = "GET"):
        self.id = form_id
        self.action = form_action
        self.method = form_method
        self.inputs = []  # 表单中的输入元素
        self.is_login_form = False  # 是否是登录表单
        self.selectors = {
            "form": "",
            "submit": ""
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "method": self.method,
            "inputs": self.inputs,
            "is_login_form": self.is_login_form,
            "selectors": self.selectors
        }

class InputElement:
    """输入元素类"""
    def __init__(self, element_id: str = "", element_name: str = "", element_type: str = "text"):
        self.id = element_id
        self.name = element_name
        self.type = element_type
        self.placeholder = ""
        self.value = ""
        self.selector = ""
        self.is_vulnerable = False  # 是否可能存在漏洞
        self.vulnerability_types = []  # 可能存在的漏洞类型
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "placeholder": self.placeholder,
            "value": self.value,
            "selector": self.selector,
            "is_vulnerable": self.is_vulnerable,
            "vulnerability_types": self.vulnerability_types
        }

class LinkElement:
    """链接元素类"""
    def __init__(self, href: str = "", text: str = ""):
        self.href = href
        self.text = text
        self.selector = ""
        self.is_visited = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "href": self.href,
            "text": self.text,
            "selector": self.selector,
            "is_visited": self.is_visited
        }

class SiteAnalyzer:
    """网站结构分析器，用于自动发现和分类网站元素"""
    
    def __init__(self):
        self.forms = []  # 表单集合
        self.inputs = []  # 输入点集合
        self.links = []  # 链接集合
        self.authentication_forms = []  # 认证表单
        self.file_upload_forms = []  # 文件上传表单
        self.api_endpoints = []  # API端点
        self.technologies = {  # 检测到的技术栈
            "frontend": [],
            "backend": [],
            "database": [],
            "framework": []
        }
        self.visited_urls = set()  # 已访问URL集合
        self.base_url = ""  # 基础URL
        
    async def analyze_site(self, page: Page) -> Dict[str, Any]:
        """分析网站结构，识别潜在测试点"""
        # 记录当前URL和基础URL
        current_url = page.url
        self.base_url = self._extract_base_url(current_url)
        self.visited_urls.add(current_url)
        
        # 分析表单和输入元素
        await self._analyze_forms(page)
        
        # 分析链接
        await self._analyze_links(page)
        
        # 识别技术栈
        await self.identify_technology(page)
        
        # 返回分析结果摘要
        return {
            "forms_count": len(self.forms),
            "inputs_count": len(self.inputs),
            "links_count": len(self.links),
            "auth_forms_count": len(self.authentication_forms),
            "file_upload_forms_count": len(self.file_upload_forms),
            "technologies": self.technologies
        }
    
    async def _analyze_forms(self, page: Page) -> None:
        """分析页面中的表单元素"""
        # 获取页面上所有表单
        form_handles = await page.query_selector_all('form')
        
        for form_handle in form_handles:
            # 创建新的表单元素
            form = FormElement()
            
            # 获取表单属性
            form.id = await form_handle.get_attribute('id') or ""
            form.action = await form_handle.get_attribute('action') or ""
            form.method = (await form_handle.get_attribute('method') or "GET").upper()
            
            # 创建表单选择器
            if form.id:
                form.selectors["form"] = f"form#{form.id}"
            else:
                # 如果没有ID，尝试创建一个唯一的选择器
                form_idx = len(self.forms)
                form.selectors["form"] = f"form:nth-of-type({form_idx + 1})"
            
            # 获取表单内的输入元素
            input_handles = await form_handle.query_selector_all('input, textarea, select')
            
            password_input_found = False
            username_input_found = False
            file_input_found = False
            
            for input_handle in input_handles:
                # 创建新的输入元素
                input_elem = InputElement()
                
                # 获取输入元素属性
                input_elem.id = await input_handle.get_attribute('id') or ""
                input_elem.name = await input_handle.get_attribute('name') or ""
                input_elem.type = await input_handle.get_attribute('type') or "text"
                input_elem.placeholder = await input_handle.get_attribute('placeholder') or ""
                input_elem.value = await input_handle.get_attribute('value') or ""
                
                # 创建输入元素选择器
                if input_elem.id:
                    input_elem.selector = f"#{input_elem.id}"
                elif input_elem.name:
                    input_elem.selector = f"[name='{input_elem.name}']"
                else:
                    # 如果没有ID或name，尝试创建一个基于表单的相对选择器
                    input_idx = len(form.inputs)
                    input_elem.selector = f"{form.selectors['form']} input:nth-of-type({input_idx + 1})"
                
                # 检查是否是密码输入框
                if input_elem.type == "password":
                    password_input_found = True
                
                # 检查是否可能是用户名输入框
                if input_elem.type == "text" and any(keyword in (input_elem.name or "").lower() for keyword in ["user", "login", "email", "name", "account"]):
                    username_input_found = True
                
                # 检查是否是文件上传输入框
                if input_elem.type == "file":
                    file_input_found = True
                    form.is_file_upload = True
                
                # 添加输入元素到表单
                form.inputs.append(input_elem.to_dict())
                
                # 同时也添加到全局输入点集合
                self.inputs.append(input_elem)
            
            # 查找表单提交按钮
            submit_button = await form_handle.query_selector('input[type="submit"], button[type="submit"], button:has-text("Submit"), button:has-text("登录"), button:has-text("Login")')
            if submit_button:
                button_id = await submit_button.get_attribute('id') or ""
                if button_id:
                    form.selectors["submit"] = f"#{button_id}"
                else:
                    form.selectors["submit"] = f"{form.selectors['form']} input[type='submit'], {form.selectors['form']} button[type='submit']"
            
            # 检查是否是登录表单
            if password_input_found and username_input_found:
                form.is_login_form = True
                self.authentication_forms.append(form)
            
            # 检查是否是文件上传表单
            if file_input_found:
                self.file_upload_forms.append(form)
            
            # 添加表单到集合
            self.forms.append(form)
    
    async def _analyze_links(self, page: Page) -> None:
        """分析页面中的链接元素"""
        # 获取页面上所有链接
        link_handles = await page.query_selector_all('a[href]')
        
        for link_handle in link_handles:
            # 创建新的链接元素
            link = LinkElement()
            
            # 获取链接属性
            link.href = await link_handle.get_attribute('href') or ""
            link.text = await link_handle.inner_text() or ""
            
            # 创建链接选择器
            link_id = await link_handle.get_attribute('id') or ""
            if link_id:
                link.selector = f"a#{link_id}"
            elif link.text:
                # 使用文本作为选择器
                link.selector = f"a:has-text('{link.text}')"
            else:
                # 如果没有ID或文本，使用href
                link.selector = f"a[href='{link.href}']"
            
            # 只添加有效的内部链接
            if link.href and not link.href.startswith('#') and not link.href.startswith('javascript:'):
                # 转换为绝对URL
                if not link.href.startswith('http'):
                    if link.href.startswith('/'):
                        link.href = f"{self.base_url}{link.href}"
                    else:
                        link.href = f"{self.base_url}/{link.href}"
                
                # 检查是否是同一域名的链接
                if self.base_url in link.href:
                    self.links.append(link)
    
    async def identify_technology(self, page: Page) -> Dict[str, List[str]]:
        """识别网站使用的技术栈"""
        # 从HTML识别前端技术
        html_content = await page.content()
        
        # 检查常见前端框架
        if re.search(r'react|reactjs', html_content, re.IGNORECASE):
            self.technologies["frontend"].append("React")
        if re.search(r'vue|vuejs', html_content, re.IGNORECASE):
            self.technologies["frontend"].append("Vue.js")
        if re.search(r'angular', html_content, re.IGNORECASE):
            self.technologies["frontend"].append("Angular")
        if re.search(r'jquery', html_content, re.IGNORECASE):
            self.technologies["frontend"].append("jQuery")
        if re.search(r'bootstrap', html_content, re.IGNORECASE):
            self.technologies["frontend"].append("Bootstrap")
        
        # 检查后端技术
        server_header = await page.evaluate("""
            () => {
                try {
                    const perfEntries = performance.getEntriesByType('navigation');
                    if (perfEntries && perfEntries.length > 0) {
                        return perfEntries[0].serverTiming;
                    }
                } catch (e) {}
                return null;
            }
        """)
        
        # 从响应头识别服务器类型
        if server_header:
            if 'Apache' in str(server_header):
                self.technologies["backend"].append("Apache")
            if 'nginx' in str(server_header):
                self.technologies["backend"].append("Nginx")
            if 'IIS' in str(server_header):
                self.technologies["backend"].append("IIS")
        
        # 检查网页内容中的线索
        if re.search(r'php|wordpress|laravel|symfony', html_content, re.IGNORECASE):
            self.technologies["backend"].append("PHP")
        if re.search(r'asp\.net|\.aspx|\.asmx', html_content, re.IGNORECASE):
            self.technologies["backend"].append("ASP.NET")
        if re.search(r'node\.js|express|nextjs', html_content, re.IGNORECASE):
            self.technologies["backend"].append("Node.js")
        if re.search(r'django|flask|python', html_content, re.IGNORECASE):
            self.technologies["backend"].append("Python")
        if re.search(r'ruby|rails', html_content, re.IGNORECASE):
            self.technologies["backend"].append("Ruby")
        if re.search(r'java|spring|struts', html_content, re.IGNORECASE):
            self.technologies["backend"].append("Java")
        
        # 检查数据库线索
        if re.search(r'mysql|mariadb', html_content, re.IGNORECASE):
            self.technologies["database"].append("MySQL")
        if re.search(r'postgresql|postgres', html_content, re.IGNORECASE):
            self.technologies["database"].append("PostgreSQL")
        if re.search(r'mongodb', html_content, re.IGNORECASE):
            self.technologies["database"].append("MongoDB")
        if re.search(r'mssql|sqlserver', html_content, re.IGNORECASE):
            self.technologies["database"].append("Microsoft SQL Server")
        if re.search(r'oracle', html_content, re.IGNORECASE):
            self.technologies["database"].append("Oracle")
        
        # 检查框架线索
        if re.search(r'wordpress', html_content, re.IGNORECASE):
            self.technologies["framework"].append("WordPress")
        if re.search(r'drupal', html_content, re.IGNORECASE):
            self.technologies["framework"].append("Drupal")
        if re.search(r'joomla', html_content, re.IGNORECASE):
            self.technologies["framework"].append("Joomla")
        if re.search(r'laravel', html_content, re.IGNORECASE):
            self.technologies["framework"].append("Laravel")
        if re.search(r'django', html_content, re.IGNORECASE):
            self.technologies["framework"].append("Django")
        
        # 移除重复项
        for category in self.technologies:
            self.technologies[category] = list(set(self.technologies[category]))
        
        return self.technologies
    
    def analyze_input_for_vulnerabilities(self) -> List[Dict[str, Any]]:
        """分析输入点可能存在的漏洞"""
        vulnerable_inputs = []
        
        for input_elem in self.inputs:
            # 只检查文本输入和隐藏输入
            if input_elem.type not in ["text", "hidden", "search", "url", "textarea"]:
                continue
            
            # 检查名称中的关键字，判断是否易受SQL注入攻击
            if any(keyword in (input_elem.name or "").lower() for keyword in ["id", "user", "name", "pass", "key", "search", "query"]):
                input_elem.is_vulnerable = True
                input_elem.vulnerability_types.append("sql_injection")
                vulnerable_inputs.append(input_elem.to_dict())
            
            # 检查是否可能存在XSS漏洞
            if any(keyword in (input_elem.name or "").lower() for keyword in ["comment", "message", "content", "description", "text"]):
                input_elem.is_vulnerable = True
                input_elem.vulnerability_types.append("xss")
                if input_elem.to_dict() not in vulnerable_inputs:
                    vulnerable_inputs.append(input_elem.to_dict())
            
            # 检查是否可能存在命令注入
            if any(keyword in (input_elem.name or "").lower() for keyword in ["cmd", "command", "exec", "run", "ping", "query"]):
                input_elem.is_vulnerable = True
                input_elem.vulnerability_types.append("command_injection")
                if input_elem.to_dict() not in vulnerable_inputs:
                    vulnerable_inputs.append(input_elem.to_dict())
        
        return vulnerable_inputs
    
    def get_input_points(self) -> List[Dict[str, Any]]:
        """获取所有输入点"""
        return [input_elem.to_dict() for input_elem in self.inputs]
    
    def get_links(self) -> List[Dict[str, Any]]:
        """获取所有链接"""
        return [link.to_dict() for link in self.links]
    
    def get_forms(self) -> List[Dict[str, Any]]:
        """获取所有表单"""
        return [form.to_dict() for form in self.forms]
    
    def get_auth_forms(self) -> List[Dict[str, Any]]:
        """获取所有认证表单"""
        return [form.to_dict() for form in self.authentication_forms]
    
    def get_file_upload_forms(self) -> List[Dict[str, Any]]:
        """获取所有文件上传表单"""
        return [form.to_dict() for form in self.file_upload_forms]
    
    def _extract_base_url(self, url: str) -> str:
        """从URL中提取基础URL"""
        match = re.match(r'(https?://[^/]+)', url)
        if match:
            return match.group(1)
        return url 