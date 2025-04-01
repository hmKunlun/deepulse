#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
浏览器控制模块
用于封装对浏览器的自动化操作
"""

import asyncio
import os
import sys
import time
import base64
import re
import logging
from typing import Optional, List, Dict, Any, Union, Tuple

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from rich.console import Console
from modules.test_framework import TestFramework

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BrowserAgent")

console = Console()

# 添加这个新类用于记录历史状态
class BrowserStateTracker:
    """跟踪浏览器状态历史，便于错误恢复"""
    
    def __init__(self, max_history: int = 10, auto_recovery: bool = True):
        self.url_history = []
        self.state_history = []  # 存储更丰富的状态信息
        self.last_stable_url = None
        self.max_history = max_history
        self.has_error = False
        self.error_details = None
        self.auto_recovery = auto_recovery  # 是否启用自动恢复
        self.consecutive_errors = 0  # 连续错误计数
    
    def record_url(self, url: str, is_stable: bool = True, page_title: str = ""):
        """记录URL和页面状态，保持历史记录在最大长度内"""
        if not url or url == "about:blank":
            return
            
        state_info = {
            "url": url,
            "title": page_title,
            "timestamp": time.time(),
            "is_stable": is_stable
        }
        
        self.url_history.append(url)
        self.state_history.append(state_info)
        
        if len(self.url_history) > self.max_history:
            self.url_history.pop(0)
            self.state_history.pop(0)
            
        if is_stable:
            self.last_stable_url = url
            self.has_error = False
            self.error_details = None
            self.consecutive_errors = 0
    
    def mark_error(self, url: str, error_details: str):
        """标记当前URL发生错误"""
        self.has_error = True
        self.error_details = error_details
        self.consecutive_errors += 1
        
        # 将当前URL记录为不稳定状态
        self.record_url(url, is_stable=False)
    
    def get_recovery_url(self) -> str:
        """获取恢复URL，优先使用最后一个稳定URL"""
        if self.last_stable_url:
            return self.last_stable_url
            
        # 如果没有明确的稳定URL，尝试找到最近的可能稳定的URL
        for state in reversed(self.state_history[:-1]):  # 跳过当前状态
            if state.get("is_stable", False):
                return state["url"]
                
        # 如果没有找到稳定URL，返回历史中较早的URL
        if len(self.url_history) > 1:
            return self.url_history[-2]  # 返回倒数第二个URL
        elif self.url_history:
            return self.url_history[0]
        return None
        
    def should_auto_recover(self) -> bool:
        """决定是否应该自动恢复"""
        # 连续错误次数过多时自动恢复
        if self.consecutive_errors >= 2:
            return True
        
        # 出现错误且启用了自动恢复
        return self.has_error and self.auto_recovery
        
    def clear(self):
        """清除历史记录"""
        self.url_history = []
        self.state_history = []
        self.last_stable_url = None
        self.has_error = False
        self.error_details = None
        self.consecutive_errors = 0
        
    def get_suggestion(self) -> str:
        """根据当前状态提供建议"""
        if self.has_error and self.last_stable_url:
            if self.consecutive_errors >= 2:
                return f"检测到连续多次错误。强烈建议使用BACK命令返回到上一个稳定页面，或使用GOTO {self.last_stable_url}直接返回到最后一个稳定状态。"
            else:
                return f"检测到错误。建议使用BACK命令返回到上一个稳定页面，或使用GOTO {self.last_stable_url}直接返回到最后一个稳定状态。"
        return ""

class Agent:
    """使用LLM和浏览器进行自动化测试的代理"""

    def __init__(
        self,
        task: str,
        api_key: str = None,
        model: str = "Pro/deepseek-ai/DeepSeek-V3",
        use_vision: bool = True,
        debug: bool = False,
        auto_run: bool = True,  # 新增参数，控制是否自动执行预设命令
        auto_recovery: bool = True,  # 控制是否自动进行错误恢复
        error_recovery_level: int = 3,  # 触发自动恢复的错误级别阈值
        site_analyzer = None,  # 站点分析器
        guidance_enabled: bool = True,  # 是否启用测试指导功能
        user_prompt_enabled: bool = False,  # 是否启用用户自定义提示词
        user_prompt_frequency: int = 3,  # 用户提示词输入频率（迭代次数）
    ):
        self.task = task
        self.model = model
        self.use_vision = use_vision
        self.debug = debug
        self.auto_run = auto_run  # 存储参数
        
        # 添加错误恢复相关配置
        self.auto_recovery = auto_recovery
        self.error_recovery_level = error_recovery_level
        
        # 添加站点分析器
        self.site_analyzer = site_analyzer
        
        # 设置API密钥
        if api_key:
            os.environ["SILICONFLOW_API_KEY"] = api_key
        
        # 初始化LLM接口
        from modules.llm_interface import LLMInterface
        self.llm = LLMInterface(
            api_key=api_key,
            model=model,
            timeout=60
        )
        
        self.messages: List[Dict[str, str]] = []
        self.page: Optional[Page] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
        # 添加状态跟踪器
        self.state_tracker = BrowserStateTracker(auto_recovery=auto_recovery)
        
        # 添加测试框架
        self.guidance_enabled = guidance_enabled
        self.test_framework = TestFramework() if guidance_enabled else None
        
        self.system_prompt = """你是一个专业的网络安全测试专家，你需要使用中文回复并执行以下任务。
请注意：你必须直接通过命令来控制浏览器，而不是等待用户的进一步指示。请立即开始执行任务！

请使用以下格式发送命令，每行一个命令，不要添加任何前缀（如"AI:"）：
GOTO [url]
SCREENSHOT
TYPE [selector] [text]

你可以使用以下命令来控制浏览器：
- GOTO [url] - 导航到指定URL
- CLICK [selector] - 点击匹配选择器的元素
- TYPE [selector] [text] - 在选择器匹配的元素中输入文本
- ENTER - 按下回车键
- SCREENSHOT - 拍摄屏幕截图，然后你就能看到当前页面
- SCROLLDOWN [pixels] - 向下滚动指定像素数量
- SCROLLUP [pixels] - 向上滚动指定像素数量
- WAIT [milliseconds] - 等待指定的毫秒数
- THINK [analysis] - 进行思考，分析当前情况，并计划下一步行动
- BACK - 返回上一页
- REFRESH - 刷新当前页面

命令示例（请严格遵循这种格式）：
GOTO https://example.com
SCREENSHOT
CLICK #login-button
TYPE #username admin
TYPE #password password
CLICK #submit-button
WAIT 2000
SCREENSHOT

安全测试流程指南：
1. 分析每个步骤的结果，特别是错误页面、空白页面等异常情况
2. 判断每个步骤是否成功，如果失败则分析原因
3. 在每个重要步骤后使用SCREENSHOT查看结果
4. 根据每个测试的实际结果来决定下一步操作
5. 如果遇到错误，考虑返回到上一个稳定状态
6. 适当调整测试策略，而不是机械地执行预设命令

错误恢复机制说明：
1. 系统会自动检测页面错误（SQL错误、HTTP错误、空白页面等）
2. 对于严重错误，系统会自动回退到最近的稳定页面
3. 如果发生连续错误，系统也会自动回退
4. 即使系统自动恢复，你也应该根据错误信息调整后续测试策略
5. 如果你发现系统没有自动恢复，可以手动使用BACK命令或GOTO命令返回到稳定状态

重要提示：
1. 请每次回复时必须包含至少一个有效命令！
2. 所有解释和分析请使用中文！
3. 请直接发送命令，不要添加"AI:"或其他前缀！
4. 一步一步地解决问题，使用SCREENSHOT命令来检查当前状态
5. 如果你需要提供安全测试相关的语句，请明确指出并解释它们的作用
6. 在获得页面内容后，立即进行实际的安全测试，而不是继续导航
"""

        # 用户自定义提示词设置
        self.user_prompt_enabled = user_prompt_enabled
        self.user_prompt_frequency = user_prompt_frequency
        self.user_custom_prompts = []  # 存储用户提供的自定义提示词

    async def run(self):
        """运行代理以完成任务"""
        console.print(f"[bold green]任务: {self.task}[/bold green]")
        
        # 初始化消息列表，根据auto_run参数决定初始提示
        if self.auto_run:
            initial_prompt = f"""任务: {self.task}

请立即开始执行安全测试，遵循以下步骤：
1. 首先使用GOTO命令访问目标网站
2. 然后使用SCREENSHOT命令查看页面内容
3. 进行实际的安全测试操作，如点击元素、输入测试数据等

请直接发送命令，不要添加任何前缀（如'AI:'）！
现在请开始执行第一步：使用GOTO命令访问目标网站。"""
        else:
            initial_prompt = f"""任务: {self.task}

请自主分析每个步骤的执行结果，并决定下一步行动。你的职责是：
1. 分析我提供的测试结果和截图
2. 判断每个命令执行是否成功
3. 发现潜在问题和漏洞
4. 根据实际情况调整测试策略
5. 决定下一步最合适的命令

请注意观察异常情况，如错误页面、空白页面、SQL错误等，它们可能包含重要信息。
特别是在进行SQL注入测试时，请注意结果的差异，以确定注入是否成功和列数等信息。

请开始第一步：使用GOTO命令访问目标网站。"""
        
        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": initial_prompt},
        ]
        
        # 添加测试框架初始指导消息
        if self.test_framework:
            guidance = self.test_framework.get_initial_guidance()
            self.messages.append({"role": "system", "content": guidance})
        
        # 添加最大重试次数
        max_browser_retries = 3
        retry_count = 0
        
        while retry_count < max_browser_retries:
            try:
                async with async_playwright() as p:
                    # 使用更多浏览器选项提高稳定性
                    launch_options = {
                        "headless": False,
                        "timeout": 60000,  # 增加启动超时时间到60秒
                        "args": [
                            "--disable-web-security",  # 禁用某些安全限制以便测试
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-accelerated-2d-canvas",
                            "--no-first-run",
                            "--no-zygote",
                            "--disable-gpu"
                        ]
                    }
                    
                    # 尝试启动浏览器
                    console.print("[cyan]正在启动浏览器...[/cyan]")
                    self.browser = await p.chromium.launch(**launch_options)
                    self.context = await self.browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        ignore_https_errors=True  # 忽略HTTPS错误，对于某些测试站点可能有用
                    )
                    self.page = await self.context.new_page()
                    
                    console.print("[green]浏览器启动成功！[/green]")
                    
                    # 主循环
                    max_iterations = 15
                    for i in range(max_iterations):
                        console.print(f"[bold blue]迭代 {i+1}/{max_iterations}[/bold blue]")
                        
                        # 检查是否需要获取用户自定义提示词
                        if self.user_prompt_enabled and i > 0 and i % self.user_prompt_frequency == 0:
                            console.print("[bold magenta]====== 用户提示词输入 ======[/bold magenta]")
                            console.print("[yellow]当前测试进度: 迭代 {}/{}[/yellow]".format(i, max_iterations))
                            console.print("[yellow]当前URL: {}[/yellow]".format(self.page.url if self.page else "未知"))
                            
                            # 输出最近的测试状态摘要
                            history_summary = self.generate_simple_history_summary()
                            if history_summary:
                                console.print("[cyan]最近测试状态:[/cyan]\n{}".format(history_summary))
                            
                            # 获取用户输入
                            user_prompt = input("[bold green]请输入您的自定义提示词（直接按回车跳过）：[/bold green]\n")
                            
                            if user_prompt.strip():
                                # 记录用户提示词
                                self.user_custom_prompts.append(user_prompt)
                                # 将用户提示词添加到消息列表
                                self.messages.append({"role": "system", "content": f"用户自定义指示: {user_prompt}"})
                                console.print("[green]已添加用户自定义提示词[/green]")
                        
                        # 获取LLM的回应
                        console.print("[cyan]正在等待LLM响应...[/cyan]")
                        response = await self._get_llm_response()
                        console.print(f"[bold yellow]LLM响应:[/bold yellow]\n{response}")
                        
                        # 解析和执行命令
                        commands = self._parse_commands(response)
                        if not commands:
                            console.print("[bold red]未找到有效命令！[/bold red]")
                            console.print("正在尝试引导模型提供正确的命令格式...")
                            
                            # 添加引导消息
                            guidance_message = """我没有看到任何有效的浏览器命令。请使用以下格式提供命令，每行一个：
GOTO [url] - 例如：GOTO http://example.com
SCREENSHOT - 拍摄当前页面截图
CLICK [selector] - 例如：CLICK #login-button
TYPE [selector] [text] - 例如：TYPE #username admin
THINK [analysis] - 分析当前情况并计划下一步

请直接发送命令，不要添加"AI:"或其他前缀。请立即执行："""
                            
                            self.messages.append({"role": "user", "content": guidance_message})
                            continue  # 继续下一次迭代而不是退出
                        
                        # 执行所有命令
                        should_continue = await self._execute_commands(commands)
                        if not should_continue:
                            break
                    
                    # 成功完成所有迭代，关闭浏览器
                    await self.browser.close()
                    console.print("[bold green]任务完成![/bold green]")
                    return  # 成功完成，退出函数
                    
            except Exception as e:
                retry_count += 1
                console.print(f"[bold red]浏览器发生错误: {str(e)}[/bold red]")
                
                if retry_count < max_browser_retries:
                    console.print(f"[yellow]正在重试 ({retry_count}/{max_browser_retries})...[/yellow]")
                    # 在重试前短暂等待
                    await asyncio.sleep(2)
                else:
                    console.print("[bold red]达到最大重试次数，无法启动浏览器。终止任务。[/bold red]")
                    # 告知LLM浏览器出现问题
                    self.messages.append({
                        "role": "user", 
                        "content": f"""浏览器启动失败，无法进行测试。可能的原因：
1. 系统资源不足
2. 浏览器配置问题
3. 网络连接问题

请提供一个不依赖浏览器的安全测试建议总结和相关安全测试方法。"""
                    })
                    
                    # 即使没有浏览器，也尝试获取LLM的回应
                    console.print("[cyan]正在请求LLM提供建议...[/cyan]")
                    response = await self._get_llm_response()
                    console.print(f"[bold yellow]LLM建议:[/bold yellow]\n{response}")
                    return

    def generate_simple_history_summary(self):
        """生成简化的历史摘要"""
        if len(self.messages) <= 3:  # 初始状态，无需历史摘要
            return ""
            
        summary = ["=== 历史摘要 ==="]
        
        # 1. 已访问的页面（最多5个）
        visited_urls = self.state_tracker.url_history[-5:] if hasattr(self.state_tracker, 'url_history') else []
        if visited_urls:
            summary.append("已访问页面:")
            for url in visited_urls:
                if url and url != "about:blank":
                    summary.append(f"- {url}")
        
        # 2. 已执行的命令（最近10条）
        executed_commands = []
        for msg in self.messages:
            if msg.get("role") == "user" and "命令执行结果" in msg.get("content", ""):
                # 从内容中提取命令
                lines = msg.get("content", "").split("\n")
                for line in lines:
                    if "- 成功" in line or "- 点击" in line or "- 输入" in line:  # 提取成功执行的命令
                        executed_commands.append(line.strip())
        
        if executed_commands:
            summary.append("\n已执行的命令:")
            for cmd in executed_commands[-10:]:  # 最近10条命令
                summary.append(f"- {cmd}")
        
        # 3. 已发现的漏洞或错误（如有）
        errors = []
        for msg in self.messages:
            if msg.get("role") == "user" and "检测到错误" in msg.get("content", ""):
                error_lines = [line for line in msg.get("content", "").split("\n") if "检测到错误" in line]
                errors.extend(error_lines)
        
        if errors:
            summary.append("\n遇到的错误:")
            for error in errors[-5:]:  # 最近5个错误
                summary.append(f"- {error}")
        
        return "\n".join(summary)
    
    async def get_current_page_content(self):
        """获取当前页面内容，包含完整HTML代码"""
        if not self.page:
            return "无页面内容"
        
        try:
            # 1. 基本页面信息
            page_title = await self.page.title() if self.page else "无标题"
            content = [
                f"=== 当前页面 ===",
                f"URL: {self.page.url}",
                f"标题: {page_title}"
            ]
            
            # 2. 获取页面元素统计
            input_count, button_count, form_count, link_count, dropdown_count = await self._get_element_counts()
            content.append(f"页面元素: 输入框({input_count}), 按钮({button_count}), 表单({form_count}), 链接({link_count}), 下拉菜单({dropdown_count})")
            
            # 3. 表单内容提取（核心元素）
            form_info = await self._get_form_elements_details()
            if form_info:
                content.append("\n可用表单元素:")
                content.append(form_info)
            
            # 4. 页面文本内容
            text_content = await self._get_page_text_content()
            if text_content:
                content.append("\n页面文本内容:")
                content.append(text_content)
            
            # 5. 页面HTML，保持完整内容不压缩
            html = await self.page.content()
            
            content.append("\n页面HTML代码:")
            content.append(f"```html\n{html}\n```")
            
            return "\n".join(content)
        except Exception as e:
            return f"获取页面内容出错: {str(e)}"
    
    def trim_messages_to_fit(self, messages, max_tokens=60000):
        """将消息长度控制在token限制内，保留完整HTML内容"""
        try:
            # 简单估算 - 每个字符约占0.25个token
            total_chars = sum(len(str(m.get("content", ""))) for m in messages)
            estimated_tokens = int(total_chars * 0.25)
            
            # 如果估计token数小于限制，无需处理
            if estimated_tokens <= max_tokens:
                return messages
                
            console.print(f"[yellow]消息长度超出限制。估计token数: {estimated_tokens}, 限制: {max_tokens}[/yellow]")
            console.print(f"[yellow]按用户要求保留完整HTML内容，只裁剪历史消息[/yellow]")
            
            # 保留系统消息和最近的用户消息，但不截断HTML内容
            # 找出最新的包含HTML的消息
            html_message_idx = -1
            for i in range(len(messages)-1, -1, -1):
                if "```html" in str(messages[i].get("content", "")):
                    html_message_idx = i
                    break
            
            if html_message_idx >= 0:
                # 保留系统消息
                system_messages = [m for m in messages if m.get("role") == "system"]
                # 保留包含HTML的消息
                html_message = messages[html_message_idx]
                # 保留最近的一条助手消息和一条用户消息（如果存在）
                recent_messages = []
                user_found = False
                assistant_found = False
                
                for i in range(len(messages)-1, -1, -1):
                    if i == html_message_idx:
                        continue  # 跳过HTML消息，因为我们已经单独保存了
                    
                    if messages[i].get("role") == "user" and not user_found:
                        recent_messages.append(messages[i])
                        user_found = True
                    elif messages[i].get("role") == "assistant" and not assistant_found:
                        recent_messages.append(messages[i])
                        assistant_found = True
                        
                    if user_found and assistant_found:
                        break
                
                # 按正确顺序组合消息
                result = system_messages + recent_messages[::-1] + [html_message]
                
                # 重新估算token数
                new_total_chars = sum(len(str(m.get("content", ""))) for m in result)
                new_estimated_tokens = int(new_total_chars * 0.25)
                console.print(f"[green]调整后消息数: {len(result)}, 估计token数: {new_estimated_tokens}[/green]")
                
                return result
            
            # 如果没有找到HTML消息，保留系统消息和最近的几条对话
            return messages[-3:]  # 保留最后3条消息
        except Exception as e:
            console.print(f"[bold red]裁剪消息时出错: {str(e)}[/bold red]")
            # 发生错误时，返回原始消息
            return messages

    async def _get_llm_response(self) -> str:
        """
        获取LLM响应，优化消息管理以避免超出token限制
        """
        # 添加测试框架指导（如果启用）
        if self.test_framework:
            guidance = self.test_framework.process_command("")
            if guidance:
                self.messages.append({"role": "system", "content": guidance})
        
        # 1. 准备消息
        # 系统提示
        final_messages = [{"role": "system", "content": self.system_prompt}]
        
        # 添加简化历史摘要
        history_summary = self.generate_simple_history_summary()
        if history_summary:
            final_messages.append({"role": "system", "content": history_summary})
        
        # 添加原始任务（始终保留）
        if len(self.messages) > 1:
            final_messages.append(self.messages[1])  # 原始任务通常是第二条消息
        
        # 添加用户最近的自定义提示词（如果有）
        if self.user_prompt_enabled and self.user_custom_prompts:
            # 只添加最近的一条用户提示词
            final_messages.append({"role": "system", "content": f"用户自定义指示: {self.user_custom_prompts[-1]}"})
        
        # 添加当前页面内容
        current_page = await self.get_current_page_content()
        final_messages.append({"role": "user", "content": current_page})
        
        # 添加最近一次命令执行结果（如果有）
        for msg in reversed(self.messages):
            if msg.get("role") == "user" and "命令执行结果" in str(msg.get("content", "")):
                final_messages.append(msg)
                break
        
        # 2. 简单裁剪以适应模型限制
        trimmed_messages = self.trim_messages_to_fit(final_messages)
        
        # 3. 获取响应
        response = await self.llm.get_chat_response(trimmed_messages)
        return response

    def _parse_commands(self, text: str) -> List[str]:
        """从LLM响应中解析命令"""
        commands = []
        command_prefixes = ["GOTO", "CLICK", "TYPE", "ENTER", "SCREENSHOT", "SCROLLDOWN", "SCROLLUP", "WAIT", "THINK", "BACK", "REFRESH"]
        
        # 预处理文本，清除可能的前缀
        # 删除行开头的"AI:"前缀
        cleaned_text = re.sub(r'(?m)^AI:\s*', '', text)
        # 删除其他可能的角色前缀
        cleaned_text = re.sub(r'(?m)^(人类|系统):\s*', '', cleaned_text)
        
        # 提取所有行并检查每一行
        for line in cleaned_text.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            # 检查每个命令前缀
            for prefix in command_prefixes:
                # 使用正则表达式进行更宽松的匹配
                match = re.match(rf'^{prefix}\b(.*)$', line, re.IGNORECASE)
                if match:
                    # 保持命令部分大写，参数部分保持原样
                    args = match.group(1).strip()
                    normalized_cmd = f"{prefix.upper()} {args}" if args else prefix.upper()
                    commands.append(normalized_cmd)
                    break  # 找到命令后跳出内部循环
        
        # 输出解析结果
        if commands:
            console.print(f"[green]解析到 {len(commands)} 个命令[/green]")
        else:
            console.print("[red]没有解析到有效命令[/red]")
            console.print("原始响应分析:")
            
            # 尝试找出问题所在
            lines = text.split('\n')
            if len(lines) < 3:
                console.print("[red]  响应过短，可能不包含命令[/red]")
            
            for i, line in enumerate(lines[:10]):  # 只分析前10行
                line = line.strip()
                if any(cmd.lower() in line.lower() for cmd in command_prefixes):
                    console.print(f"[yellow]  行 {i+1} 包含命令关键词但格式不正确: {line}[/yellow]")
                elif line and len(line) > 5:  # 忽略空行和太短的行
                    console.print(f"[grey]  行 {i+1}: {line}[/grey]")
        
        return commands

    async def _execute_commands(self, commands: List[str]) -> bool:
        """执行命令列表并返回是否应继续执行"""

        # 记录命令执行结果
        command_results = []
        
        # 添加历史状态追踪，用于错误恢复
        last_url = self.page.url if self.page else ""
        error_detected = False
        recovery_executed = False
        sql_error_detected = False
        
        for cmd in commands:
            try:
                if cmd.startswith("GOTO "):
                    url = cmd[len("GOTO "):].strip()
                    console.print(f"[cyan]正在导航到: {url}[/cyan]")
                    
                    # 导航到新URL前记录当前URL
                    if self.page and self.page.url and self.page.url != "about:blank":
                        self.state_tracker.record_url(self.page.url)
                    
                    try:
                        await self.page.goto(url, timeout=60000)
                        console.print(f"[green]成功导航到: {url}[/green]")
                        command_results.append(f"成功导航到: {url}")
                        
                        # 等待页面加载稳定
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=5000)
                        except Exception:
                            pass  # 忽略超时
                        
                        # 获取页面内容用于AI判断
                        page_content = await self._get_page_content()
                        screenshot = await self._take_screenshot() if self.use_vision else None
                        
                        # 首先使用AI判断页面状态
                        is_normal, reason = await self._ask_llm_about_page_state(page_content, screenshot)
                        
                        # 如果AI能确定页面状态
                        if is_normal is not None:
                            if not is_normal:
                                # AI认为页面不正常
                                error_detected = True
                                error_message = f"AI检测到页面异常: {reason}"
                                error_level = 3  # 默认为严重错误
                                
                                console.print(f"[bold red]{error_message}[/bold red]")
                                
                                # 处理错误并可能自动恢复
                                recovery_executed = await self._handle_error_with_recovery(error_message, error_level, command_results)
                                
                                if recovery_executed:
                                    console.print("[green]已执行自动恢复[/green]")
                                    # 如果已执行恢复，跳过剩余命令
                                    break
                            else:
                                # AI认为页面正常
                                console.print(f"[green]AI检测页面状态正常: {reason}[/green]")
                                # 记录为稳定状态
                                page_title = await self.page.title()
                                self.state_tracker.record_url(url, is_stable=True, page_title=page_title)
                        else:
                            # AI无法确定，使用传统规则检测
                            console.print("[yellow]AI无法确定页面状态，使用传统规则检测[/yellow]")
                            has_error, error_message, error_level = await self._detect_page_error()
                            
                            if has_error:
                                error_detected = True
                                console.print(f"[bold red]导航后检测到页面错误: {error_message}[/bold red]")
                                
                                # 处理错误并可能自动恢复
                                recovery_executed = await self._handle_error_with_recovery(error_message, error_level, command_results)
                                
                                if recovery_executed:
                                    console.print("[green]已执行自动恢复[/green]")
                                    # 如果已执行恢复，跳过剩余命令
                                    break
                            else:
                                # 记录新URL作为稳定状态
                                page_title = await self.page.title()
                                self.state_tracker.record_url(url, is_stable=True, page_title=page_title)
                        
                        # 分析页面元素
                        input_count = await self.page.locator('input').count()
                        button_count = await self.page.locator('button').count()
                        form_count = await self.page.locator('form').count()
                        link_count = await self.page.locator('a').count()
                        
                        console.print(f"[green]页面元素分析: 输入框: {input_count}, 按钮: {button_count}, 表单: {form_count}, 链接: {link_count}[/green]")
                        
                        # 在执行命令后更新测试框架状态
                        if self.test_framework:
                            guidance = self.test_framework.process_command(cmd)
                            if guidance:
                                self.messages.append({"role": "system", "content": guidance})
                        
                    except Exception as e:
                        console.print(f"[red]导航失败: {str(e)}[/red]")
                        command_results.append(f"导航失败: {str(e)}")
                        
                        # 记录错误状态
                        if self.page and self.page.url:
                            self.state_tracker.mark_error(self.page.url, f"导航失败: {str(e)}")
                        
                        # 添加更多错误信息帮助理解
                        recovery_message = f"""
导航到 {url} 失败。可能原因:
1. URL不可访问或网络问题
2. 页面加载超时
3. 浏览器问题

请尝试:
- 检查URL是否正确
- 使用REFRESH命令
- 检查网络连接
"""
                        command_results.append(recovery_message)
                        
                        # 添加恢复建议
                        recovery_url = self.state_tracker.get_recovery_url()
                        if recovery_url:
                            command_results.append(f"建议返回到稳定页面: GOTO {recovery_url}")

                elif cmd.startswith("CLICK "):
                    selector = cmd[len("CLICK "):].strip()
                    console.print(f"[cyan]点击: {selector}[/cyan]")
                    
                    try:
                        # 增加超时，某些网站加载较慢
                        await self.page.click(selector, timeout=45000)
                        console.print(f"[green]成功点击元素: {selector}[/green]")
                        command_results.append(f"成功点击元素: {selector}")
                        
                        # 等待页面加载稳定
                        try:
                            await self.page.wait_for_load_state("networkidle", timeout=5000)
                        except Exception:
                            pass  # 忽略超时
                        
                        # 获取页面内容用于AI判断
                        page_content = await self._get_page_content()
                        screenshot = await self._take_screenshot() if self.use_vision else None
                        
                        # 首先使用AI判断页面状态
                        is_normal, reason = await self._ask_llm_about_page_state(page_content, screenshot)
                        
                        # 如果AI能确定页面状态
                        if is_normal is not None:
                            if not is_normal:
                                # AI认为页面不正常
                                error_detected = True
                                error_message = f"AI检测到页面异常: {reason}"
                                error_level = 3  # 默认为严重错误
                                
                                console.print(f"[bold red]{error_message}[/bold red]")
                                
                                # 处理错误并可能自动恢复
                                recovery_executed = await self._handle_error_with_recovery(error_message, error_level, command_results)
                                
                                if recovery_executed:
                                    console.print("[green]已执行自动恢复[/green]")
                                    # 如果已执行恢复，跳过剩余命令
                                    break
                            else:
                                # AI认为页面正常
                                console.print(f"[green]AI检测页面状态正常: {reason}[/green]")
                                # 记录为稳定状态
                                if self.page and self.page.url and self.page.url != "about:blank":
                                    page_title = await self.page.title()
                                    self.state_tracker.record_url(self.page.url, is_stable=True, page_title=page_title)
                        else:
                            # AI无法确定，使用传统规则检测
                            console.print("[yellow]AI无法确定页面状态，使用传统规则检测[/yellow]")
                            has_error, error_message, error_level = await self._detect_page_error()
                            
                            if has_error:
                                error_detected = True
                                console.print(f"[bold red]点击后检测到页面错误: {error_message}[/bold red]")
                                
                                # 处理错误并可能自动恢复
                                recovery_executed = await self._handle_error_with_recovery(error_message, error_level, command_results)
                                
                                if recovery_executed:
                                    console.print("[green]已执行自动恢复[/green]")
                                    # 如果已执行恢复，跳过剩余命令
                                    break
                            else:
                                # 如果没有错误，记录为稳定状态
                                if self.page and self.page.url and self.page.url != "about:blank":
                                    page_title = await self.page.title()
                                    self.state_tracker.record_url(self.page.url, is_stable=True, page_title=page_title)
                        
                    except Exception as e:
                        console.print(f"[red]点击失败: {str(e)}[/red]")
                        command_results.append(f"点击失败: {str(e)}")
                        
                        # 尝试更宽松的选择器
                        try:
                            # 构建更通用的选择器
                            fallback_selectors = []
                            
                            # 如果包含ID，尝试按ID选择
                            if "#" in selector:
                                id_part = selector.split("#")[1].split(" ")[0].split(":")[0].split("[")[0]
                                fallback_selectors.append(f"#{id_part}")
                            
                            # 如果是button元素，尝试文本内容选择
                            if "button" in selector.lower():
                                # 提取可能的文本
                                text_match = re.search(r'text="([^"]*)"', selector)
                                if text_match:
                                    text = text_match.group(1)
                                    fallback_selectors.append(f"button:has-text(\"{text}\")")
                                    fallback_selectors.append(f"input[type=\"submit\"][value=\"{text}\"]")
                            
                            # 尝试不同类型的输入元素
                            if "input" in selector.lower():
                                fallback_selectors.append("input[type=\"submit\"]")
                                fallback_selectors.append("button[type=\"submit\"]")
                            
                            # 对于链接尝试文本匹配
                            if "a" in selector.lower():
                                # 提取可能的文本
                                text_match = re.search(r'text="([^"]*)"', selector)
                                if text_match:
                                    text = text_match.group(1)
                                    fallback_selectors.append(f"a:has-text(\"{text}\")")
                            
                            # 尝试备用选择器
                            success = False
                            for fallback_selector in fallback_selectors:
                                try:
                                    console.print(f"[yellow]尝试备用选择器: {fallback_selector}[/yellow]")
                                    await self.page.click(fallback_selector, timeout=5000)
                                    console.print(f"[green]成功使用备用选择器点击: {fallback_selector}[/green]")
                                    command_results.append(f"使用备用选择器 {fallback_selector} 成功点击")
                                    success = True
                                    break
                                except Exception:
                                    continue
                            
                            if not success:
                                # 查找页面上所有可点击元素作为建议
                                clickable_elements = []
                                for element_type in ["button", "a", "input[type=\"submit\"]", "input[type=\"button\"]"]:
                                    count = await self.page.locator(element_type).count()
                                    for i in range(count):
                                        try:
                                            element = self.page.locator(element_type).nth(i)
                                            text = await element.text()
                                            if text.strip():
                                                clickable_elements.append(f"{element_type}:has-text(\"{text}\")")
                                        except:
                                            pass
                                
                                # 限制建议数量
                                if len(clickable_elements) > 5:
                                    clickable_elements = clickable_elements[:5]
                                
                                suggestions = "\n".join([f"- {elem}" for elem in clickable_elements])
                                
                                # 构建详细的恢复信息
                                recovery_message = f"""
无法点击元素: {selector}。可能原因:
1. 选择器不正确
2. 元素不存在
3. 元素不可见或被其他元素覆盖
4. 元素尚未加载

可能的可点击元素:
{suggestions}

建议:
- 使用SCREENSHOT命令查看当前页面
- 尝试等待元素加载 (WAIT 命令)
- 使用更精确的选择器
"""
                                command_results.append(recovery_message)
                        except Exception as fallback_error:
                            command_results.append(f"备用选择器也失败: {str(fallback_error)}")
                
                elif cmd.startswith("SELECT "):
                    # 解析SELECT命令，格式为SELECT selector value
                    parts = cmd[len("SELECT "):].strip().split(" ", 1)
                    if len(parts) == 2:
                        selector, value = parts
                        console.print(f"[cyan]在 {selector} 中选择值: {value}[/cyan]")
                        
                        try:
                            # 1. 先尝试直接选择下拉选项
                            option_selector = f"{selector} option[value='{value}']"
                            try:
                                # 尝试点击正确的选项
                                await self.page.click(option_selector, timeout=5000)
                                console.print(f"[green]成功选择选项: {value}[/green]")
                                command_results.append(f"成功选择选项: {value}")
                            except Exception:
                                # 2. 尝试使用selectOption方法
                                await self.page.select_option(selector, value=value)
                                console.print(f"[green]成功使用select_option选择值: {value}[/green]")
                                command_results.append(f"成功设置选择值: {value}")
                        except Exception as e:
                            console.print(f"[red]选择值失败: {str(e)}[/red]")
                            command_results.append(f"选择值失败: {str(e)}")
                            
                            # 3. 尝试使用JavaScript直接设置值
                            try:
                                js_result = await self.page.evaluate(f"""
                                    (selector, value) => {{
                                        const el = document.querySelector(selector);
                                        if (el) {{
                                            el.value = value;
                                            // 触发change事件
                                            const event = new Event('change', {{ bubbles: true }});
                                            el.dispatchEvent(event);
                                            return true;
                                        }}
                                        return false;
                                    }}
                                """, selector, value)
                                
                                if js_result:
                                    console.print(f"[green]成功使用JavaScript设置选择值: {value}[/green]")
                                    command_results.append(f"成功使用JavaScript设置选择值: {value}")
                                else:
                                    recovery_message = f"""
无法在 {selector} 中选择值 {value}。可能原因:
1. 选择器不正确
2. 元素不是select元素
3. 指定的值在选项中不存在

建议:
- 使用SCREENSHOT命令确认页面结构
- 检查选择器和值是否正确
- 尝试使用CLICK命令直接点击选项
"""
                                    command_results.append(recovery_message)
                            except Exception as js_error:
                                console.print(f"[red]JavaScript设置值也失败: {str(js_error)}[/red]")
                                command_results.append(f"尝试所有方法设置值都失败")
                    else:
                        console.print("[red]SELECT命令格式错误，正确格式为: SELECT selector value[/red]")
                        command_results.append("SELECT命令格式错误，正确格式为: SELECT selector value")
                
                elif cmd.startswith("TYPE "):
                    parts = cmd[len("TYPE "):].strip().split(" ", 1)
                    if len(parts) == 2:
                        selector, text = parts
                        console.print(f"[cyan]在 {selector} 中输入: {text}[/cyan]")
                        
                        # 仅识别可能的SQL注入测试，但不作为错误条件处理
                        is_sql_injection = False
                        sql_patterns = ["'", "\"", "OR", "AND", "UNION", "SELECT", "--", "#", "1=1", "1=2"]
                        if any(pattern.lower() in text.lower() for pattern in sql_patterns if len(pattern) > 1) or (("'" in text or "\"" in text) and any(p.lower() in text.lower() for p in ["or", "and", "union", "select"])):
                            is_sql_injection = True
                            console.print(f"[yellow]可能的SQL注入测试命令：{text}[/yellow]")
                            
                            # 检查SQL语法，尝试修复常见问题
                            if "--" in text and not re.search(r'--\s', text):
                                fixed_text = text.replace("--", "-- ")
                                console.print(f"[yellow]修正SQL注入语法: {text} -> {fixed_text}[/yellow]")
                                text = fixed_text
                            
                            # MySQL中SPACE()函数之后需要括号
                            if "SPACE" in text and not "SPACE(" in text:
                                fixed_text = text.replace("SPACE", "SPACE()")
                                console.print(f"[yellow]修正SQL函数语法: {text} -> {fixed_text}[/yellow]")
                                text = fixed_text
                        
                        try:
                            # 先清除已有内容
                            await self.page.fill(selector, "")
                            # 然后输入新内容
                            await self.page.fill(selector, text)
                            console.print(f"[green]成功在 {selector} 中输入文本[/green]")
                            
                            if is_sql_injection:
                                command_results.append(f"成功输入SQL注入测试: {text}")
                            else:
                                command_results.append(f"成功在 {selector} 中输入文本: {text}")
                        except Exception as e:
                            console.print(f"[red]输入文本失败: {str(e)}[/red]")
                            command_results.append(f"输入文本失败: {str(e)}")
                            
                            # 尝试备用方法
                            try:
                                # 尝试使用type方法
                                await self.page.type(selector, text)
                                console.print(f"[green]成功使用备用方法在 {selector} 中输入文本[/green]")
                                
                                if is_sql_injection:
                                    command_results.append(f"成功使用备用方法输入SQL注入测试: {text}")
                                else:
                                    command_results.append(f"成功使用备用方法输入文本")
                            except Exception as e2:
                                command_results.append(f"备用输入方法也失败: {str(e2)}")
                                
                                # 提供详细的错误恢复建议
                                recovery_message = f"""
无法在 {selector} 中输入文本。可能原因:
1. 选择器不正确
2. 元素不存在
3. 元素不是可输入类型
4. 元素被禁用或只读

建议:
- 检查选择器是否正确
- 使用SCREENSHOT命令查看页面
- 确保元素已加载 (尝试WAIT命令)
"""
                                command_results.append(recovery_message)
                    else:
                        console.print("[red]TYPE命令格式错误，正确格式为: TYPE selector text[/red]")
                        command_results.append("TYPE命令格式错误，正确格式为: TYPE selector text")
                
                elif cmd == "ENTER":
                    console.print("[cyan]按下回车键[/cyan]")
                    await self.page.keyboard.press("Enter")
                    console.print("[green]成功按下回车键[/green]")
                    command_results.append("成功按下回车键")
                
                elif cmd.startswith("SCROLLDOWN "):
                    pixels = cmd[len("SCROLLDOWN "):].strip()
                    console.print(f"[cyan]向下滚动 {pixels} 像素[/cyan]")
                    await self.page.mouse.wheel(0, int(pixels))
                    console.print(f"[green]成功向下滚动 {pixels} 像素[/green]")
                    command_results.append(f"成功向下滚动 {pixels} 像素")
                
                elif cmd.startswith("SCROLLUP "):
                    pixels = cmd[len("SCROLLUP "):].strip()
                    console.print(f"[cyan]向上滚动 {pixels} 像素[/cyan]")
                    await self.page.mouse.wheel(0, -int(pixels))
                    console.print(f"[green]成功向上滚动 {pixels} 像素[/green]")
                    command_results.append(f"成功向上滚动 {pixels} 像素")
                
                elif cmd.startswith("WAIT "):
                    ms = cmd[len("WAIT "):].strip()
                    console.print(f"[cyan]等待 {ms} 毫秒[/cyan]")
                    await asyncio.sleep(int(ms) / 1000)
                    console.print(f"[green]等待 {ms} 毫秒完成[/green]")
                    command_results.append(f"等待 {ms} 毫秒")
                
                elif cmd.startswith("THINK "):
                    thoughts = cmd[len("THINK "):].strip()
                    console.print(f"[cyan]思考: {thoughts}[/cyan]")
                    command_results.append(f"思考: {thoughts}")
                
                elif cmd == "BACK":
                    console.print("[cyan]返回上一页[/cyan]")
                    
                    # 记录当前URL
                    if self.page and self.page.url:
                        current_url = self.page.url
                    
                    try:
                        await self.page.go_back()
                        console.print("[green]成功返回上一页[/green]")
                        command_results.append("成功返回上一页")
                        
                        # 清除错误状态，返回操作通常是恢复步骤
                        if self.state_tracker.has_error:
                            console.print("[yellow]已从错误状态恢复[/yellow]")
                            self.state_tracker.has_error = False
                            
                    except Exception as e:
                        console.print(f"[red]返回失败: {str(e)}[/red]")
                        command_results.append(f"返回失败: {str(e)}")
                        
                        # 提供恢复建议
                        recovery_url = self.state_tracker.get_recovery_url()
                        if recovery_url:
                            command_results.append(f"建议使用GOTO命令直接返回到稳定页面: GOTO {recovery_url}")

                elif cmd == "REFRESH":
                    console.print("[cyan]刷新页面[/cyan]")
                    await self.page.reload()
                    console.print("[green]成功刷新页面[/green]")
                    command_results.append("成功刷新页面")
                
                elif cmd == "SCREENSHOT":
                    console.print("[cyan]拍摄屏幕截图...[/cyan]")
                    
                    # 获取页面源代码
                    page_html = await self.page.content()
                    
                    # 分析当前页面状态
                    current_url = self.page.url if self.page else ""
                    page_title = await self.page.title() if self.page else ""
                    
                    # 获取页面状态细节
                    input_count, button_count, form_count, link_count, dropdown_count = await self._get_element_counts()
                    
                    # 获取表单元素详情
                    form_elements = await self._get_form_elements_details()
                    
                    # 获取页面文本内容
                    page_text = await self._get_page_text_content()
                    
                    # 获取当前页面的完整HTML代码（使用模型的大上下文窗口）
                    console.print("[cyan]获取页面HTML代码...[/cyan]")
                    page_html_formatted = f"```html\n{page_html}\n```" if page_html else "HTML代码获取失败"
                    
                    # 构建页面分析消息
                    page_analysis = f"""当前页面内容概要:
页面标题: {page_title}
当前URL: {current_url}
页面元素: 输入框({input_count}), 按钮({button_count}), 表单({form_count}), 链接({link_count}), 下拉菜单({dropdown_count})

可用表单元素:
{form_elements}

页面文本内容:
{page_text}

页面HTML代码:
{page_html_formatted}

请分析页面内容，判断当前状态，并决定下一步操作："""
                    
                    # 记录发送到LLM的信息长度
                    html_length = len(page_html_formatted) if page_html_formatted else 0
                    total_msg_length = len(page_analysis)
                    console.print(f"[cyan]发送页面分析到LLM，总长度: {total_msg_length}字符，HTML长度: {html_length}字符[/cyan]")
                    
                    # 添加页面状态消息
                    self.messages.append({"role": "user", "content": page_analysis})
                    
                    # 记录日志
                    logger.info(f"发送页面分析到LLM，总长度: {total_msg_length}字符，其中HTML代码长度: {html_length}字符")
                    logger.debug(f"页面分析内容(截断):\n{page_analysis[:500]}...")
                    
                    # 执行截图
                    if self.page:
                        try:
                            screenshot_path = f"screenshots/screenshot_{int(time.time())}.png"
                            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                            await self.page.screenshot(path=screenshot_path)
                            console.print(f"[green]截图已保存: {screenshot_path}[/green]")
                        except Exception as e:
                            console.print(f"[red]截图失败: {str(e)}[/red]")
                        
                    # 分析页面元素
                    console.print(f"[green]页面元素分析: 输入框: {input_count}, 按钮: {button_count}, 表单: {form_count}, 链接: {link_count}[/green]")
                    
                    # 检测页面错误
                    has_error, error_message, error_level = await self._detect_page_error()
                    
                    if has_error:
                        error_detected = True
                        console.print(f"[bold red]截图时检测到页面错误: {error_message}[/bold red]")
                        
                        # 检查是否是SQL错误
                        if "SQL" in error_message:
                            sql_error_detected = True
                        
                        # 将错误信息添加到命令结果
                        command_results.append(f"检测到错误: {error_message}")
                        
                        # 在这里不自动恢复，因为SCREENSHOT命令通常用于分析当前状态
                        # 但是提供恢复建议
                        recovery_suggestion = self.state_tracker.get_suggestion()
                        if recovery_suggestion:
                            command_results.append(recovery_suggestion)
                            
                        # 记录错误状态
                        if self.page and self.page.url:
                            self.state_tracker.mark_error(self.page.url, error_message)
                    else:
                        # 没有检测到错误，记录为稳定页面
                        if self.page and self.page.url and self.page.url != "about:blank":
                            page_title = await self.page.title()
                            self.state_tracker.record_url(self.page.url, is_stable=True, page_title=page_title)
                    
                    if self.use_vision:
                        # 添加错误警告信息
                        error_warning = ""
                        if error_detected:
                            error_warning = f"\n\n⚠️ 警告: 检测到页面错误！{error_message}"
                            recovery_suggestion = self.state_tracker.get_suggestion()
                            if recovery_suggestion:
                                error_warning += f"\n{recovery_suggestion}"
                                
                        # 现有代码
                        self.messages.append({
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": f"这是当前页面的截图。请分析页面内容，判断当前状态，并决定下一步操作：{error_warning}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot}"}}
                            ]
                        })
                        command_results.append("截图已完成。页面截图已提供给AI进行分析。")
                    else:
                        # 添加错误警告信息
                        error_warning = ""
                        if error_detected:
                            error_warning = f"\n\n⚠️ 警告: 检测到页面错误！{error_message}"
                            recovery_suggestion = self.state_tracker.get_suggestion()
                            if recovery_suggestion:
                                error_warning += f"\n{recovery_suggestion}"
                        
                        # 获取页面内容
                        page_content = await self._get_page_content()
                        self.messages.append({
                            "role": "user",
                            "content": f"当前页面内容概要:\n{page_content}{error_warning}\n\n请分析页面内容，判断当前状态，并决定下一步操作："
                        })
                        command_results.append("截图已完成。页面文本内容已提供给AI进行分析。")
                
                else:
                    console.print(f"[bold red]未知命令: {cmd}[/bold red]")
                    command_results.append(f"未知命令: {cmd}")
            
            except Exception as e:
                console.print(f"[bold red]执行命令 '{cmd}' 时发生错误: {str(e)}[/bold red]")
                command_results.append(f"执行命令 '{cmd}' 时发生错误: {str(e)}")
                # 继续执行其他命令，而不是立即返回
        
        # 如果不是screenshot命令，则将命令执行结果添加到消息中
        if not any(cmd.startswith("SCREENSHOT") for cmd in commands):
            # 将所有命令执行结果添加到消息中，以便AI可以分析
            results_text = ""
            for result in command_results:
                results_text += f"- {result}\n"
            
            # 添加错误警告
            error_warning = ""
            if error_detected:
                error_warning = "\n⚠️ 警告: 检测到页面错误！建议谨慎操作。"
                if sql_error_detected:
                    error_warning += "SQL错误通常表明注入测试触发了数据库异常。"
                recovery_suggestion = self.state_tracker.get_suggestion()
                if recovery_suggestion:
                    error_warning += f"\n{recovery_suggestion}"
            
            self.messages.append({
                "role": "user",
                "content": f"""命令执行结果:

{results_text}{error_warning}

请分析以上执行结果，判断当前状态，并决定下一步操作:"""
            })
        
        return True  # 默认继续执行
        
    def _analyze_sql_error(self, page_content: str) -> str:
        """分析SQL错误信息并提供建议"""
        if "You have an error in your SQL syntax" in page_content:
            if "near ''" in page_content or "near '''" in page_content:
                return "SQL语法错误，单引号闭合存在问题。尝试使用#代替--作为注释，或使用不同的闭合方式。"
            elif "near '--'" in page_content:
                return "SQL语法错误，注释符有问题。在MySQL中--后需要有空格，尝试使用#作为注释。"
        
        if "order by" in page_content.lower() and ("error" in page_content.lower() or "syntax" in page_content.lower()):
            return "ORDER BY语句语法有误。尝试不同的闭合方式，如1' ORDER BY 1#或1\" ORDER BY 1#"
        
        if "union select" in page_content.lower() and ("error" in page_content.lower() or "syntax" in page_content.lower()):
            return "UNION SELECT语句语法有误。确保列数匹配，并尝试不同的闭合方式。"
        
        return "检测到SQL错误，但无法确定具体原因。建议返回并尝试不同的注入语法。"

    async def _take_screenshot(self) -> str:
        """获取屏幕截图并返回base64编码的字符串"""
        try:
            # 使用控制台输出而不是logger
            # 检查页面是否已成功加载
            if not self.page.url or self.page.url == "about:blank":
                console.print("[bold red]无法获取截图，页面未成功加载[/bold red]")
                return ""
                
            screenshot = await self.page.screenshot()
            
            # 将二进制数据转为base64编码的字符串
            screenshot_base64 = base64.b64encode(screenshot).decode('ascii')
            console.print("[green]成功获取截图[/green]")
            return screenshot_base64
            
        except Exception as e:
            console.print(f"[bold red]截图失败: {str(e)}[/bold red]")
            return ""

    async def _get_page_content(self) -> str:
        """获取页面内容的文本摘要，特别优化SQL注入测试场景"""
        try:
            # 检查页面是否已成功加载
            if not self.page.url or self.page.url == "about:blank":
                console.print("[bold red]无法获取页面内容，页面未成功加载[/bold red]")
                return "页面未加载"
                
            # 获取页面标题和URL
            page_title = await self.page.title()
            current_url = self.page.url
            
            # 提取页面文本内容
            text_content = await self.page.evaluate("""
            () => {
                // 获取可见文本
                function getVisibleText(node) {
                    let text = '';
                    if (node.nodeType === Node.TEXT_NODE) {
                        text += node.textContent;
                    } else if (node.nodeType === Node.ELEMENT_NODE && 
                              window.getComputedStyle(node).display !== 'none' && 
                              window.getComputedStyle(node).visibility !== 'hidden') {
                        for (let child of node.childNodes) {
                            text += getVisibleText(child);
                        }
                    }
                    return text.trim();
                }
                
                // 获取页面的主要内容区域
                const mainContent = document.body || document.documentElement;
                let text = getVisibleText(mainContent);
                
                // 限制长度
                if (text.length > 2000) {
                    text = text.substring(0, 2000) + '...（内容已截断）';
                }
                
                return text;
            }
            """)
            
            # 获取页面上的主要元素
            element_counts = await self.page.evaluate("""
            () => {
                return {
                    inputs: document.querySelectorAll('input').length,
                    buttons: document.querySelectorAll('button').length,
                    forms: document.querySelectorAll('form').length,
                    links: document.querySelectorAll('a').length,
                    selects: document.querySelectorAll('select').length
                }
            }
            """)
            
            # 提取主要表单元素信息
            form_elements = []
            
            # 分析输入框
            if element_counts['inputs'] > 0:
                input_info = await self.page.evaluate("""
                () => {
                    return Array.from(document.querySelectorAll('input')).slice(0, 5).map(input => {
                        return {
                            type: input.type || 'text',
                            name: input.name || '未命名',
                            id: input.id || '无ID',
                            placeholder: input.placeholder || '无占位符',
                            value: input.value || ''
                        };
                    });
                }
                """)
                
                for i, input_el in enumerate(input_info):
                    form_elements.append(f"输入框 {i+1}: 类型={input_el['type']}, 名称={input_el['name']}, ID={input_el['id']}, 值={input_el['value']}")
            
            # 分析下拉菜单 - 对安全级别设置很重要
            select_elements = []
            if element_counts.get('selects', 0) > 0:
                select_info = await self.page.evaluate("""
                () => {
                    return Array.from(document.querySelectorAll('select')).map(select => {
                        let options = Array.from(select.options).map(opt => {
                            return {text: opt.text, value: opt.value, selected: opt.selected};
                        });
                        return {
                            name: select.name || '未命名',
                            id: select.id || '无ID',
                            options: options
                        };
                    });
                }
                """)
                
                for i, sel in enumerate(select_info):
                    options_str = ", ".join([f"{o['text']}({o['value']}){' [已选中]' if o['selected'] else ''}" for o in sel['options']])
                    select_elements.append(f"下拉菜单 {i+1}: 名称={sel['name']}, ID={sel['id']}, 选项=[{options_str}]")
            
            # 检查页面是否包含SQL错误信息
            sql_error_info = ""
            error_keywords = ["error", "syntax", "mysql", "sql", "database", "query"]
            if any(keyword in text_content.lower() for keyword in error_keywords):
                sql_error_info = "\n[SQL错误检测]\n"
                # 提取可能的错误消息
                error_lines = []
                for line in text_content.split('\n'):
                    if any(keyword in line.lower() for keyword in error_keywords):
                        error_lines.append(line.strip())
                
                if error_lines:
                    sql_error_info += "检测到可能的SQL错误:\n" + "\n".join(error_lines[:3])
                    
                    # 提供错误分析
                    if "syntax" in " ".join(error_lines).lower():
                        sql_error_info += "\n疑似SQL语法错误 - 建议检查闭合符号和注释方式。"
                    if "union" in " ".join(error_lines).lower():
                        sql_error_info += "\n疑似UNION语句错误 - 确认列数是否匹配。"
            
            # 提取当前DVWA安全级别 (如果存在)
            security_level = ""
            if "Security level" in text_content or "security level" in text_content.lower():
                security_info = await self.page.evaluate("""
                () => {
                    // 寻找安全级别信息
                    const secLevelText = Array.from(document.querySelectorAll('*')).find(el => 
                        el.textContent.includes('Security level') || 
                        el.textContent.includes('security level'))?.textContent || '';
                    return secLevelText;
                }
                """)
                
                if security_info:
                    security_level = f"\n[安全级别]\n{security_info.strip()}"
            
            # 构建页面内容摘要
            summary = [
                f"页面标题: {page_title}",
                f"当前URL: {current_url}",
                f"页面元素: 输入框({element_counts['inputs']}), 按钮({element_counts['buttons']}), 表单({element_counts['forms']}), 链接({element_counts['links']}), 下拉菜单({element_counts.get('selects', 0)})"
            ]
            
            if security_level:
                summary.append(security_level)
                
            if sql_error_info:
                summary.append(sql_error_info)
            
            if form_elements:
                summary.append("\n可用表单元素:")
                summary.extend(form_elements)
                
            if select_elements:
                summary.append("\n可用下拉菜单:")
                summary.extend(select_elements)
                
            if text_content:
                summary.append("\n页面文本内容:")
                summary.append(text_content)
                
            return "\n".join(summary)
            
        except Exception as e:
            console.print(f"[bold red]获取页面内容失败: {str(e)}[/bold red]")
            return f"获取页面内容失败: {str(e)}"

    async def _detect_page_error(self) -> tuple[bool, str, int]:
        """检测页面是否存在错误，返回(是否有错误, 错误描述, 错误级别)
        错误级别: 0=无错误, 1=轻微错误, 2=中等错误, 3=严重错误
        """
        # 检查HTTP状态码
        try:
            response = await self.page.evaluate("""() => { 
                const entries = window.performance.getEntries();
                if (entries && entries.length > 0) {
                    return { 
                        status: entries[0].responseStatus || 0,
                        url: document.location.href
                    };
                }
                return { status: 0, url: document.location.href };
            }""")
            status_code = response.get('status', 0)
            if status_code >= 400:
                return True, f"HTTP错误: 状态码 {status_code}", 3
        except Exception:
            pass
            
        # 检查页面内容中的错误指示
        page_content = await self._get_page_content()
        
        # 检查SQL错误 - 改进逻辑，要求错误出现在错误上下文中
        # 定义更严格的SQL错误模式，必须同时满足多个条件
        sql_error_contexts = [
            "You have an error in your SQL syntax",
            "error in your SQL syntax",
            "mysql_fetch_array()",
            "Warning: mysql_",
            "SQL syntax.*near",
            "MySQL Error",
            "MariaDB server version for the right syntax",
            "Oracle.*error",
            "PostgreSQL.*ERROR",
            "SQLITE_ERROR",
            "Microsoft SQL.*error",
            "ODBC SQL Server Driver",
            "Database error",
            "Microsoft OLE DB Provider for ODBC Drivers error",
            "Unknown column '[^']+' in 'field list'",
            "Table '[^']+' doesn't exist"
        ]
        
        # 检查是否存在SQL错误特征 - 必须匹配至少一个明确的错误模式
        sql_error_match = False
        matched_pattern = ""
        for pattern in sql_error_contexts:
            if re.search(pattern, page_content, re.IGNORECASE):
                sql_error_match = True
                matched_pattern = pattern
                break
                
        # 如果找到明确的SQL错误模式
        if sql_error_match:
            error_analysis = self._analyze_sql_error(page_content)
            return True, f"SQL错误: {error_analysis}", 3
        
        # 检查常见网页错误
        error_phrases = [
            "404 Not Found", "403 Forbidden", "500 Internal Server Error",
            "Access Denied", "权限不足", "无权访问", "页面不存在",
            "服务器错误", "服务暂时不可用", "Bad Request", "Gateway Timeout"
        ]
        for phrase in error_phrases:
            if phrase in page_content:
                return True, f"网页错误: {phrase}", 3
        
        # 检查页面内容是否为空
        try:
            text_content = await self.page.evaluate("""() => {
                return document.body && document.body.innerText ? document.body.innerText.trim() : "";
            }""")
            if not text_content:
                return True, "页面内容为空", 2
        except Exception:
            pass
        
        # 检查JavaScript错误
        try:
            js_errors = await self.page.evaluate("""() => {
                if (window.jsErrors && window.jsErrors.length > 0) {
                    return window.jsErrors;
                }
                return [];
            }""")
            if js_errors and len(js_errors) > 0:
                return True, f"JavaScript错误: {js_errors[0]}", 1
        except Exception:
            pass
            
        return False, "", 0

    async def _ask_llm_about_page_state(self, page_content: str, screenshot_base64: str = None) -> tuple[bool, str]:
        """请求LLM判断页面状态是否正常，返回(是否正常, 原因/建议)"""
        try:
            console.print("[cyan]请求LLM判断页面状态...[/cyan]")
            
            import requests
            import json
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            url = "https://api.siliconflow.cn/v1/chat/completions"
            
            # 确保API密钥存在
            api_key = os.getenv('SILICONFLOW_API_KEY')
            if not api_key:
                console.print("[bold red]错误: 未设置SILICONFLOW_API_KEY环境变量[/bold red]")
                return False, "无法使用LLM判断页面状态，请使用规则判断"
            
            # 准备向模型发送的消息，询问页面状态
            system_message = """你是一个专业的网络安全测试专家，精通Web安全测试和各类漏洞分析。
你的任务是判断提供的页面内容是否表示一个正常的网页，还是包含错误信息。

请特别注意以下规则：
1. 登录页面、主页、正常的功能页面应该被视为【正常状态】
2. 含有SQL语法错误、数据库错误等明确错误信息的页面应该被视为错误状态
3. 要区分正常的安全测试内容与实际的错误信息
4. 404错误、403禁止访问等HTTP错误应视为错误状态
5. 空白页面、缺少关键内容的页面也可能是错误状态

返回格式必须是：状态:正常 或 状态:错误，后跟分析原因。"""

            # 尝试提取页面标题并添加到上下文中
            page_title = ""
            try:
                if self.page:
                    page_title = await self.page.title()
            except:
                pass
            
            title_context = f"页面标题: {page_title}\n\n" if page_title else ""
            
            # 显示分析上下文
            console.print(f"[yellow]页面标题: {page_title}[/yellow]")
            
            # 准备问题
            if screenshot_base64:
                # 使用图像
                user_message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"请分析以下页面内容并判断它是否是一个正常页面还是错误页面：\n\n{title_context}{page_content[:1000]}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_base64}"}}
                    ]
                }
                console.print("[yellow]请求包含文本和图像内容[/yellow]")
            else:
                # 仅使用文本
                user_message = {
                    "role": "user",
                    "content": f"请分析以下页面内容并判断它是否是一个正常页面还是错误页面：\n\n{title_context}{page_content[:2000]}"
                }
                console.print("[yellow]请求仅包含文本内容[/yellow]")
                
                # 显示摘要信息
                content_preview = page_content[:100] + "..." if len(page_content) > 100 else page_content
                console.print(f"[grey]页面内容摘要: {content_preview}[/grey]")
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_message},
                    user_message
                ],
                "stream": False,
                "max_tokens": 256,
                "temperature": 0.1,  # 降低温度使输出更确定性
                "top_p": 0.7,
                "top_k": 50
            }
            
            console.print(f"[cyan]使用模型: {self.model}进行页面状态判断[/cyan]")
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 使用线程池执行HTTP请求，避免阻塞异步环境
            console.print(f"[cyan]发送请求中...[/cyan]")
            request_start_time = time.time()
            
            with ThreadPoolExecutor() as executor:
                response_future = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    lambda: requests.post(url, json=payload, headers=headers)
                )
            
            request_time = time.time() - request_start_time
            console.print(f"[green]请求完成，耗时: {request_time:.2f}秒[/green]")
            
            # 检查响应状态
            if response_future.status_code != 200:
                console.print(f"[bold red]AI判断页面状态请求失败: 状态码 {response_future.status_code}[/bold red]")
                console.print(f"[red]错误响应: {response_future.text[:200]}[/red]")
                return False, "API请求失败，使用规则判断"
            
            # 解析响应
            try:
                response_json = response_future.json()
                if 'choices' not in response_json or len(response_json['choices']) == 0:
                    console.print("[bold red]API响应格式错误，缺少choices字段[/bold red]")
                    return False, "API响应格式错误，使用规则判断"
                
                ai_response = response_json['choices'][0]['message']['content']
                console.print(f"[green]AI页面状态判断原始响应:[/green]\n{ai_response}")
                
                # 记录更详细的token使用情况
                if 'usage' in response_json:
                    usage = response_json['usage']
                    console.print(f"[grey]Token使用: 提示={usage.get('prompt_tokens', 'unknown')}, 补全={usage.get('completion_tokens', 'unknown')}, 总计={usage.get('total_tokens', 'unknown')}[/grey]")
                
                # 解析AI的判断结果
                if "状态:正常" in ai_response or "状态：正常" in ai_response:
                    console.print("[bold green]AI判定: 页面状态正常 ✓[/bold green]")
                    return True, ai_response.split("\n")[0]
                elif "状态:错误" in ai_response or "状态：错误" in ai_response:
                    console.print("[bold red]AI判定: 页面状态异常 ✗[/bold red]")
                    return False, ai_response.split("\n")[0]
                else:
                    console.print("[yellow]AI响应格式不标准，尝试进一步分析...[/yellow]")
                    
                    # 使用增强的关键词检测
                    # 正常状态关键词
                    normal_keywords = [
                        "正常", "成功", "正确", "有效", "主页", "控制面板", "仪表盘", 
                        "欢迎", "welcome", "dashboard", "菜单", "导航栏", "功能页面", "登录页"
                    ]
                    # 错误状态关键词
                    error_keywords = [
                        "错误", "失败", "异常", "无效", "sql错误", "syntax error", 
                        "database error", "not found", "forbidden", "空白页面", "404", "500"
                    ]
                    
                    # 记录关键词匹配情况
                    matched_normal = []
                    matched_error = []
                    
                    # 检查正常状态关键词
                    normal_match = False
                    for keyword in normal_keywords:
                        if keyword in ai_response.lower():
                            normal_match = True
                            matched_normal.append(keyword)
                    
                    # 检查错误状态关键词
                    error_match = False
                    for keyword in error_keywords:
                        if keyword in ai_response.lower():
                            error_match = True
                            matched_error.append(keyword)
                    
                    # 记录匹配到的关键词
                    if matched_normal:
                        console.print(f"[green]匹配到正常状态关键词: {', '.join(matched_normal)}[/green]")
                    if matched_error:
                        console.print(f"[red]匹配到错误状态关键词: {', '.join(matched_error)}[/red]")
                    
                    # 如果只匹配到正常关键词
                    if normal_match and not error_match:
                        console.print("[green]基于关键词匹配: 判定为正常状态[/green]")
                        return True, "AI判断页面状态正常: " + ai_response.split("\n")[0]
                    # 如果只匹配到错误关键词
                    elif error_match and not normal_match:
                        console.print("[red]基于关键词匹配: 判定为错误状态[/red]")
                        return False, "AI判断页面状态异常: " + ai_response.split("\n")[0]
                    # 如果两种都匹配或都不匹配
                    else:
                        console.print("[yellow]关键词匹配不明确，尝试页面内容分析...[/yellow]")
                        
                        # 通过页面内容中的额外特征再次尝试判断
                        if "欢迎" in page_content or "Welcome" in page_content:
                            console.print("[green]页面内容分析: 包含欢迎信息，判定为正常状态[/green]")
                            return True, "页面包含欢迎信息，判定为正常状态"
                        elif any(err in page_content for err in ["SQL syntax", "mysql_fetch", "未找到", "拒绝访问"]):
                            console.print("[red]页面内容分析: 包含明确的错误信息，判定为异常状态[/red]")
                            return False, "页面包含明确的错误信息，判定为异常状态"
                        else:
                            console.print("[yellow]AI无法确定页面状态[/yellow]")
                            return None, "AI无法确定页面状态，使用规则判断"
                
            except Exception as e:
                console.print(f"[bold red]解析AI响应时出错: {str(e)}[/bold red]")
                import traceback
                console.print("[red]错误堆栈:[/red]")
                console.print(traceback.format_exc()[:500])
                return None, f"解析AI响应出错: {str(e)}"
                
        except Exception as e:
            console.print(f"[bold red]请求AI判断页面状态时出错: {str(e)}[/bold red]")
            import traceback
            console.print("[red]错误堆栈:[/red]")
            console.print(traceback.format_exc()[:500])
            return None, f"请求AI判断失败: {str(e)}"
        
    async def _handle_error_with_recovery(self, error_message, error_level, command_results):
        """处理错误并执行恢复策略，返回是否已执行恢复"""
        # 记录错误状态
        if self.page and self.page.url:
            self.state_tracker.mark_error(self.page.url, error_message)
        
        command_results.append(f"检测到错误: {error_message}")
        
        # 检查是否应该自动恢复
        should_recover = error_level >= self.error_recovery_level
        if self.auto_recovery and (should_recover or self.state_tracker.should_auto_recover()):
            # 根据错误级别执行不同的恢复策略
            if error_level >= 3 or self.state_tracker.consecutive_errors >= 2:  # 严重错误或连续错误，立即自动回退
                recovery_url = self.state_tracker.get_recovery_url()
                command_results.append(f"严重错误或连续错误，正在自动恢复...")
                
                if recovery_url:
                    try:
                        console.print(f"[bold yellow]检测到严重错误或连续错误，自动恢复到 {recovery_url}[/bold yellow]")
                        await self.page.goto(recovery_url, timeout=60000)
                        command_results.append(f"已自动恢复到稳定页面: {recovery_url}")
                        return True
                    except Exception as e:
                        console.print(f"[bold red]自动恢复失败: {str(e)}[/bold red]")
                        command_results.append(f"自动恢复失败: {str(e)}")
                
                try:
                    console.print(f"[bold yellow]尝试使用浏览器后退按钮返回[/bold yellow]")
                    await self.page.go_back()
                    command_results.append("已使用浏览器后退功能返回上一页")
                    return True
                except Exception as e:
                    console.print(f"[bold red]使用后退按钮失败: {str(e)}[/bold red]")
                    command_results.append(f"使用后退按钮失败: {str(e)}")
        
        # 如果未执行自动恢复，提供相应的建议
        if error_level >= 2:  # 中等错误，提供强烈的恢复建议
            recovery_url = self.state_tracker.get_recovery_url()
            if recovery_url:
                suggestion = f"建议立即返回到稳定页面: GOTO {recovery_url} 或使用BACK命令"
                command_results.append(suggestion)
                console.print(f"[yellow]{suggestion}[/yellow]")
        
        elif error_level == 1:  # 轻微错误，提供一般建议
            recovery_suggestion = self.state_tracker.get_suggestion()
            if recovery_suggestion:
                command_results.append(recovery_suggestion)
        
        return False  # 返回是否已执行自动恢复 

    async def _get_page_text_content(self) -> str:
        """获取页面文本内容"""
        if not self.page:
            return "无页面"
        
        try:
            # 获取页面文本内容
            text_content = await self.page.evaluate("""() => {
                return document.body.innerText;
            }""")
            return text_content
        except Exception as e:
            logger.error(f"获取页面文本内容失败: {str(e)}")
            return f"无法获取文本内容: {str(e)}"

    async def _get_element_counts(self) -> Tuple[int, int, int, int, int]:
        """获取页面上不同类型元素的数量"""
        if not self.page:
            return (0, 0, 0, 0, 0)
            
        try:
            # 获取页面上的主要元素数量
            element_counts = await self.page.evaluate("""
            () => {
                return {
                    inputs: document.querySelectorAll('input').length,
                    buttons: document.querySelectorAll('button').length,
                    forms: document.querySelectorAll('form').length,
                    links: document.querySelectorAll('a').length,
                    selects: document.querySelectorAll('select').length
                }
            }
            """)
            
            return (
                element_counts['inputs'],
                element_counts['buttons'],
                element_counts['forms'],
                element_counts['links'],
                element_counts['selects']
            )
        except Exception as e:
            logger.error(f"获取元素数量失败: {str(e)}")
            return (0, 0, 0, 0, 0)

    async def _get_form_elements_details(self) -> str:
        """获取表单元素的详细信息，特别关注输入框和验证码"""
        if not self.page:
            return "无页面"
            
        try:
            # 分析输入框
            input_info = await self.page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('input')).map((input, index) => {
                    return {
                        index: index,
                        type: input.type || 'text',
                        name: input.name || '未命名',
                        id: input.id || '无ID',
                        placeholder: input.placeholder || '无占位符',
                        value: input.value || '',
                        class: input.className || '无类名',
                        // 分析父元素(寻找label或其他上下文)
                        parentText: input.parentElement ? input.parentElement.innerText.trim().substring(0, 50) : '',
                        // 检查是否可能是验证码输入框
                        possibleCaptcha: 
                            (input.name && input.name.toLowerCase().includes('captcha')) || 
                            (input.id && input.id.toLowerCase().includes('captcha')) || 
                            (input.placeholder && input.placeholder.toLowerCase().includes('验证码')) ||
                            (input.className && input.className.toLowerCase().includes('captcha')) ||
                            (input.parentElement && input.parentElement.innerText.toLowerCase().includes('验证码'))
                    };
                });
            }
            """)
            
            # 分析表单结构
            form_info = await self.page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('form')).map((form, index) => {
                    return {
                        index: index,
                        id: form.id || '无ID',
                        action: form.action || '无action',
                        method: form.method || 'GET',
                        inputCount: form.querySelectorAll('input').length,
                        submitType: form.querySelector('input[type="submit"]') ? 'input' : 
                                   form.querySelector('button[type="submit"]') ? 'button' : '无提交按钮'
                    };
                });
            }
            """)
            
            # 特别分析可能的验证码图像
            captcha_info = await self.page.evaluate("""
            () => {
                const possibleCaptchaImages = Array.from(document.querySelectorAll('img')).filter(img => {
                    // 检查图像的上下文特征(类名、ID、父元素文本等)
                    return (img.src && img.src.toLowerCase().includes('captcha')) ||
                           (img.id && img.id.toLowerCase().includes('captcha')) ||
                           (img.className && img.className.toLowerCase().includes('captcha')) ||
                           (img.alt && img.alt.toLowerCase().includes('验证码')) ||
                           (img.parentElement && img.parentElement.innerText.toLowerCase().includes('验证码'));
                });
                
                return possibleCaptchaImages.map(img => {
                    return {
                        src: img.src || '无src',
                        id: img.id || '无ID',
                        class: img.className || '无类名',
                        alt: img.alt || '无alt',
                        width: img.width,
                        height: img.height,
                        nearbyText: img.parentElement ? img.parentElement.innerText.trim().substring(0, 50) : ''
                    };
                });
            }
            """)
            
            # 分析页面文本中可能包含的验证码
            text_captcha = await self.page.evaluate("""
            () => {
                // 尝试从页面文本中提取可能的验证码
                const bodyText = document.body.innerText;
                
                // 正则表达式寻找验证码模式，例如:
                // "验证码: A1B2"
                // "验证码 (code): XYZ123"
                
                const captchaRegex = /(验证码|captcha|code)[\\s:：]*([a-zA-Z0-9]{3,8})/i;
                const match = bodyText.match(captchaRegex);
                
                return match ? match[2] : null;
            }
            """)
            
            # 构建表单元素详情字符串
            form_elements = []
            
            # 添加输入框信息
            for i, input_el in enumerate(input_info):
                captcha_marker = " (可能是验证码输入框)" if input_el['possibleCaptcha'] else ""
                form_elements.append(f"输入框 {i+1}: 类型={input_el['type']}, 名称={input_el['name']}, ID={input_el['id']}, 值={input_el['value']}{captcha_marker}")
                
                # 如果有父元素文本且非空，添加上下文
                if input_el['parentText'] and len(input_el['parentText']) > 0:
                    parent_text = input_el['parentText'].replace('\n', ' ').strip()
                    if parent_text:
                        form_elements.append(f"  上下文: {parent_text}")
            
            # 添加表单结构信息
            if form_info:
                form_elements.append("\n表单结构:")
                for i, form in enumerate(form_info):
                    form_elements.append(f"表单 {i+1}: ID={form['id']}, Action={form['action']}, Method={form['method']}, 输入框数量={form['inputCount']}")
            
            # 添加验证码图像信息
            if captcha_info:
                form_elements.append("\n可能的验证码图像:")
                for i, img in enumerate(captcha_info):
                    form_elements.append(f"验证码图像 {i+1}: ID={img['id']}, 类名={img['class']}, 大小={img['width']}x{img['height']}")
                    if img['nearbyText']:
                        form_elements.append(f"  附近文本: {img['nearbyText']}")
            
            # 添加文本验证码信息
            if text_captcha:
                form_elements.append(f"\n从页面文本提取的可能验证码: {text_captcha}")
                
            return "\n".join(form_elements)
            
        except Exception as e:
            logger.error(f"获取表单元素详情失败: {str(e)}")
            return f"获取表单元素详情失败: {str(e)}"