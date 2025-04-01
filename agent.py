#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Agent类 - 浏览器自动化代理
用于控制浏览器进行自动化测试，封装Playwright的常用操作
"""

import asyncio
import logging
import re
import os
import time
from typing import Dict, List, Any, Union, Optional, Tuple
from urllib.parse import urlparse, urljoin
import json

from playwright.async_api import Page, ElementHandle, Response, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("agent")

class Agent:
    """
    浏览器自动化代理类
    封装Playwright的常用操作，提供更高级的浏览器控制接口
    """
    
    def __init__(self, page: Page):
        """
        初始化Agent
        
        Args:
            page: Playwright页面对象
        """
        self.page = page
        self.current_url = ""
        self.history = []
        self.form_fields = []
        self.links = []
        self.action_log = []
        self.screenshots = []
        
        # 设置默认超时
        self.default_timeout = 30000  # 30秒
        self.page.set_default_timeout(self.default_timeout)
        
        # 设置页面错误监听
        self.page.on("pageerror", self._on_page_error)
        self.page.on("console", self._on_console_message)
        
        # 记录HTTP请求和响应
        self.http_history = []
        self.page.on("response", self._on_response)
    
    async def goto(self, url: str, wait_for_load: bool = True) -> bool:
        """
        导航到指定URL
        
        Args:
            url: 目标URL
            wait_for_load: 是否等待页面加载完成
            
        Returns:
            bool: 是否成功导航
        """
        try:
            self._log_action(f"导航到: {url}")
            response = await self.page.goto(url, wait_until="networkidle" if wait_for_load else "domcontentloaded")
            self.current_url = self.page.url
            self.history.append(self.current_url)
            
            if wait_for_load:
                # 等待页面完全加载
                await self.page.wait_for_load_state("networkidle")
                # 分析页面上的表单和链接
                await self._analyze_page()
            
            return response is not None and response.ok
        except Exception as e:
            self._log_action(f"导航错误: {str(e)}")
            return False
    
    async def click(self, selector: str, wait_for_navigation: bool = False) -> bool:
        """
        点击元素
        
        Args:
            selector: 元素选择器
            wait_for_navigation: 是否等待导航完成
            
        Returns:
            bool: 是否成功点击
        """
        try:
            self._log_action(f"点击: {selector}")
            
            # 确保元素可见
            await self.page.wait_for_selector(selector, state="visible")
            
            if wait_for_navigation:
                # 等待导航
                async with self.page.expect_navigation():
                    await self.page.click(selector)
                
                # 更新状态
                self.current_url = self.page.url
                self.history.append(self.current_url)
                await self._analyze_page()
            else:
                # 直接点击
                await self.page.click(selector)
            
            return True
        except Exception as e:
            self._log_action(f"点击错误: {str(e)}")
            return False
    
    async def type_text(self, selector: str, text: str, delay: int = 50) -> bool:
        """
        在输入框中输入文本
        
        Args:
            selector: 元素选择器
            text: 要输入的文本
            delay: 输入延迟(毫秒)
            
        Returns:
            bool: 是否成功输入
        """
        try:
            self._log_action(f"输入文本: {selector} => {text}")
            
            # 确保元素可见并聚焦
            await self.page.wait_for_selector(selector, state="visible")
            await self.page.focus(selector)
            
            # 清空已有内容
            await self.page.fill(selector, "")
            
            # 输入新文本
            await self.page.type(selector, text, delay=delay)
            
            return True
        except Exception as e:
            self._log_action(f"输入文本错误: {str(e)}")
            return False
    
    async def fill_form(self, form_data: Dict[str, str], submit: bool = True, submit_selector: str = "input[type=submit]") -> bool:
        """
        填充表单
        
        Args:
            form_data: 表单数据映射 {选择器: 值}
            submit: 是否自动提交表单
            submit_selector: 提交按钮选择器
            
        Returns:
            bool: 是否成功填充并提交
        """
        try:
            self._log_action(f"填充表单: {form_data}")
            
            # 填充每个字段
            for selector, value in form_data.items():
                await self.type_text(selector, value)
            
            # 提交表单
            if submit:
                self._log_action(f"提交表单: {submit_selector}")
                return await self.click(submit_selector, wait_for_navigation=True)
            
            return True
        except Exception as e:
            self._log_action(f"填充表单错误: {str(e)}")
            return False
    
    async def get_text(self, selector: str) -> Optional[str]:
        """
        获取元素文本内容
        
        Args:
            selector: 元素选择器
            
        Returns:
            str: 元素文本内容，如果无法获取则返回None
        """
        try:
            element = await self.page.wait_for_selector(selector, state="visible")
            return await element.text_content()
        except Exception as e:
            self._log_action(f"获取文本错误: {str(e)}")
            return None
    
    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        """
        获取元素属性
        
        Args:
            selector: 元素选择器
            attr: 属性名
            
        Returns:
            str: 属性值，如果无法获取则返回None
        """
        try:
            element = await self.page.wait_for_selector(selector)
            return await element.get_attribute(attr)
        except Exception as e:
            self._log_action(f"获取属性错误: {str(e)}")
            return None
    
    async def wait_for_selector(self, selector: str, timeout: int = None, state: str = "visible") -> bool:
        """
        等待元素出现
        
        Args:
            selector: 元素选择器
            timeout: 超时时间(毫秒)
            state: 元素状态，可选值："attached", "detached", "visible", "hidden"
            
        Returns:
            bool: 是否成功等待到元素
        """
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception:
            return False
    
    async def wait_for_navigation(self, timeout: int = None, wait_until: str = "networkidle") -> bool:
        """
        等待页面导航完成
        
        Args:
            timeout: 超时时间(毫秒)
            wait_until: 等待条件，可选值："load", "domcontentloaded", "networkidle"
            
        Returns:
            bool: 是否成功等待导航完成
        """
        try:
            await self.page.wait_for_navigation(timeout=timeout, wait_until=wait_until)
            self.current_url = self.page.url
            self.history.append(self.current_url)
            return True
        except Exception:
            return False
    
    async def take_screenshot(self, path: str = None) -> str:
        """
        截取屏幕截图
        
        Args:
            path: 保存路径，如果为None则自动生成
            
        Returns:
            str: 截图保存路径
        """
        try:
            if path is None:
                os.makedirs("screenshots", exist_ok=True)
                timestamp = int(time.time())
                path = f"screenshots/screenshot_{timestamp}.png"
            
            await self.page.screenshot(path=path, full_page=True)
            self.screenshots.append(path)
            self._log_action(f"截图: {path}")
            return path
        except Exception as e:
            self._log_action(f"截图错误: {str(e)}")
            return ""
    
    async def execute_script(self, script: str, arg: Any = None) -> Any:
        """
        执行JavaScript脚本
        
        Args:
            script: 脚本内容
            arg: 传递给脚本的参数
            
        Returns:
            Any: 脚本执行结果
        """
        try:
            self._log_action(f"执行脚本: {script[:50]}{'...' if len(script) > 50 else ''}")
            return await self.page.evaluate(script, arg)
        except Exception as e:
            self._log_action(f"执行脚本错误: {str(e)}")
            return None
    
    async def get_cookies(self) -> List[Dict]:
        """
        获取当前页面的cookies
        
        Returns:
            List[Dict]: cookies列表
        """
        try:
            return await self.page.context.cookies()
        except Exception as e:
            self._log_action(f"获取cookies错误: {str(e)}")
            return []
    
    async def get_local_storage(self) -> Dict:
        """
        获取localStorage内容
        
        Returns:
            Dict: localStorage内容
        """
        try:
            return await self.page.evaluate("() => Object.assign({}, localStorage)")
        except Exception as e:
            self._log_action(f"获取localStorage错误: {str(e)}")
            return {}
    
    async def get_form_fields(self) -> List[Dict]:
        """
        获取页面上的所有表单字段
        
        Returns:
            List[Dict]: 表单字段列表
        """
        return self.form_fields
    
    async def get_links(self) -> List[Dict]:
        """
        获取页面上的所有链接
        
        Returns:
            List[Dict]: 链接列表
        """
        return self.links
    
    async def _analyze_page(self):
        """分析页面内容，提取表单和链接"""
        try:
            # 提取表单字段
            self.form_fields = await self.page.evaluate('''
                () => {
                    const fields = [];
                    const inputs = document.querySelectorAll('input, textarea, select');
                    
                    inputs.forEach(input => {
                        fields.push({
                            type: input.type || input.tagName.toLowerCase(),
                            name: input.name,
                            id: input.id,
                            selector: input.id ? `#${input.id}` : 
                                   input.name ? `[name="${input.name}"]` : null,
                            value: input.value,
                            required: input.required,
                            disabled: input.disabled
                        });
                    });
                    
                    return fields;
                }
            ''')
            
            # 提取链接
            self.links = await self.page.evaluate('''
                () => {
                    const links = [];
                    const anchors = document.querySelectorAll('a');
                    
                    anchors.forEach(a => {
                        links.push({
                            text: a.textContent.trim(),
                            href: a.href,
                            id: a.id,
                            selector: a.id ? `#${a.id}` : `a[href="${a.getAttribute('href')}"]`
                        });
                    });
                    
                    return links;
                }
            ''')
        except Exception as e:
            self._log_action(f"分析页面错误: {str(e)}")
    
    def _log_action(self, message: str):
        """记录代理动作"""
        logger.info(message)
        self.action_log.append({
            "timestamp": time.time(),
            "action": message,
            "url": self.current_url
        })
    
    def _on_page_error(self, error):
        """页面错误处理"""
        self._log_action(f"页面错误: {error}")
    
    def _on_console_message(self, msg):
        """控制台消息处理"""
        if msg.type == "error":
            self._log_action(f"控制台错误: {msg.text}")
    
    async def _on_response(self, response: Response):
        """HTTP响应处理"""
        try:
            # 记录响应信息
            url = response.url
            status = response.status
            
            # 尝试获取响应内容
            content_type = response.headers.get("content-type", "")
            
            # 只记录文本和JSON类型的响应内容
            body = None
            if any(ct in content_type.lower() for ct in ["text/", "json", "javascript"]):
                try:
                    body = await response.text()
                except:
                    body = None
            
            # 记录到HTTP历史
            self.http_history.append({
                "timestamp": time.time(),
                "url": url,
                "status": status,
                "content_type": content_type,
                "body": body
            })
        except Exception:
            pass  # 忽略错误
    
    def get_action_log(self) -> List[Dict]:
        """获取操作日志"""
        return self.action_log
    
    async def detect_redirect(self, url: str) -> Tuple[bool, str]:
        """
        检测URL是否会重定向
        
        Args:
            url: 要检测的URL
            
        Returns:
            Tuple[bool, str]: (是否重定向, 最终URL)
        """
        try:
            response = await self.page.goto(url, wait_until="domcontentloaded")
            final_url = self.page.url
            return final_url != url, final_url
        except Exception as e:
            self._log_action(f"检测重定向错误: {str(e)}")
            return False, url
    
    async def find_elements(self, selector: str) -> List[ElementHandle]:
        """
        查找匹配选择器的所有元素
        
        Args:
            selector: 元素选择器
            
        Returns:
            List[ElementHandle]: 元素句柄列表
        """
        try:
            return await self.page.query_selector_all(selector)
        except Exception as e:
            self._log_action(f"查找元素错误: {str(e)}")
            return []
    
    async def close(self):
        """关闭浏览器页面"""
        try:
            await self.page.close()
        except Exception:
            pass 