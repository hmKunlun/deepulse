#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LLM接口模块
用于统一管理与SiliconFlow API的通信
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Union, Tuple

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage
from dotenv import load_dotenv

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("LLMInterface")

# 加载环境变量
load_dotenv()

class LLMInterface:
    """
    大语言模型接口类
    用于统一管理与SiliconFlow API的通信
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        base_url: str = "https://api.siliconflow.cn/v1",
        model: str = "Pro/deepseek-ai/DeepSeek-V3",
        backup_model: str = "deepseek-ai/DeepSeek-V2.5",
        timeout: int = 60,
        verbose_logging: bool = True
    ):
        """
        初始化LLM接口
        
        Args:
            api_key: API密钥，如果为None则从环境变量获取
            base_url: API基础URL
            model: 默认使用的模型
            backup_model: 备选模型，当默认模型不可用时使用
            timeout: 请求超时时间（秒）
            verbose_logging: 是否启用详细日志记录
        """
        self.api_key = api_key or os.getenv('SILICONFLOW_API_KEY', 'YOUR_API_KEY')
        self.base_url = base_url
        self.primary_model = model
        self.backup_model = backup_model
        self.current_model = model  # 当前使用的模型
        self.timeout = timeout
        self.verbose_logging = verbose_logging
        
        # 统计数据
        self.call_count = 0
        self.error_count = 0
        self.total_tokens = 0
        self.total_time = 0
        
        # 创建OpenAI客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )
        
        logger.info(f"LLM接口初始化完成，使用模型: {self.current_model}")
    
    def _truncate_message_for_log(self, message: Dict[str, Any], max_length: int = 500) -> Dict[str, Any]:
        """
        截断消息内容以便日志记录
        
        Args:
            message: 消息字典
            max_length: 最大长度
            
        Returns:
            截断后的消息字典
        """
        result = message.copy()
        if 'content' in result:
            if isinstance(result['content'], str):
                if len(result['content']) > max_length:
                    result['content'] = result['content'][:max_length] + f"... (截断，完整长度: {len(message['content'])}字符)"
            elif isinstance(result['content'], list):
                # 处理多模态内容
                truncated_content = []
                for item in result['content']:
                    if isinstance(item, dict):
                        item_copy = item.copy()
                        if 'text' in item_copy and isinstance(item_copy['text'], str) and len(item_copy['text']) > max_length:
                            item_copy['text'] = item_copy['text'][:max_length] + f"... (截断，完整长度: {len(item['text'])}字符)"
                        elif 'image_url' in item_copy:
                            item_copy['image_url'] = "[图像数据]"
                        truncated_content.append(item_copy)
                    else:
                        truncated_content.append(item)
                result['content'] = truncated_content
        return result
        
    def _format_messages_for_log(self, messages: List[Dict[str, Any]]) -> str:
        """
        格式化消息列表以便日志记录
        
        Args:
            messages: 消息列表
            
        Returns:
            格式化后的消息字符串
        """
        result = []
        for msg in messages:
            truncated_msg = self._truncate_message_for_log(msg)
            result.append(f"{truncated_msg['role']}: {truncated_msg['content']}")
        return "\n".join(result)
    
    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        max_tokens: int = 4000,
        temperature: float = 0.7,
        response_format: Optional[Dict[str, str]] = None,
        use_backup_on_failure: bool = True
    ) -> Optional[str]:
        """
        发送聊天补全请求
        
        Args:
            messages: 聊天消息列表
            max_tokens: 最大生成token数
            temperature: 温度（创造性）
            response_format: 响应格式，例如 {"type": "json_object"}
            use_backup_on_failure: 失败时是否使用备选模型
            
        Returns:
            生成的文本，失败时返回None
        """
        self.call_count += 1
        start_time = time.time()
        request_id = f"req-{int(time.time())}-{self.call_count}"
        
        # 记录请求详情
        if self.verbose_logging:
            logger.info(f"[{request_id}] 向模型 [{self.current_model}] 发送请求")
            logger.info(f"[{request_id}] 请求参数: max_tokens={max_tokens}, temperature={temperature}")
            
            # 记录消息数量和总体大小
            total_chars = sum(len(str(msg.get("content", ""))) for msg in messages)
            logger.info(f"[{request_id}] 总消息数: {len(messages)}, 总字符数: {total_chars}")
            
            # 记录每条消息的大小
            for i, msg in enumerate(messages):
                content = msg.get("content", "")
                content_len = len(str(content))
                if content_len > 1000:
                    # 检查是否包含HTML代码
                    html_start = content.find("```html")
                    if html_start > -1:
                        html_end = content.find("```", html_start + 7)
                        if html_end > -1:
                            html_len = html_end - html_start - 7
                            non_html_len = content_len - html_len
                            logger.info(f"[{request_id}] 消息[{i+1}/{len(messages)}] ({msg['role']}): 总长度={content_len}字符, HTML={html_len}字符, 其他={non_html_len}字符")
                        else:
                            logger.info(f"[{request_id}] 消息[{i+1}/{len(messages)}] ({msg['role']}): 长度={content_len}字符 (包含未闭合的HTML代码块)")
                    else:
                        logger.info(f"[{request_id}] 消息[{i+1}/{len(messages)}] ({msg['role']}): 长度={content_len}字符")
                else:
                    logger.info(f"[{request_id}] 消息[{i+1}/{len(messages)}] ({msg['role']}): 长度={content_len}字符")
        
        try:
            logger.info(f"[{request_id}] 正在调用API...")
            
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format=response_format
            )
            
            # 更新统计数据
            end_time = time.time()
            elapsed_time = end_time - start_time
            self.total_time += elapsed_time
            
            # 获取token使用情况
            try:
                prompt_tokens = response.usage.prompt_tokens
                completion_tokens = response.usage.completion_tokens
                self.total_tokens += (prompt_tokens + completion_tokens)
                logger.info(f"[{request_id}] Token使用: 提示={prompt_tokens}, 补全={completion_tokens}, 总计={prompt_tokens + completion_tokens}")
            except:
                logger.warning(f"[{request_id}] 无法获取token使用情况")
            
            # 获取并记录生成的文本
            content = response.choices[0].message.content
            
            if self.verbose_logging:
                # 记录响应内容，保留格式
                if len(content) > 1000:
                    # 截断过长内容，但保持格式，并分别显示开头和结尾部分
                    # 创建一个缩进前缀，让日志更清晰
                    indent = "    "
                    log_lines = []
                    log_lines.append(f"[{request_id}] API响应内容 (总长度: {len(content)}字符):")
                    log_lines.append(f"{indent}--- 开始部分 (前300字符) ---")
                    
                    # 处理开头部分，保留格式
                    start_content = content[:300]
                    # 将开头部分的每一行添加缩进
                    for line in start_content.split('\n'):
                        log_lines.append(f"{indent}{line}")
                    
                    log_lines.append(f"{indent}...")
                    log_lines.append(f"{indent}--- 省略了 {len(content) - 600} 字符 ---")
                    log_lines.append(f"{indent}...")
                    
                    # 处理结尾部分，保留格式
                    end_content = content[-300:]
                    # 将结尾部分的每一行添加缩进
                    for line in end_content.split('\n'):
                        log_lines.append(f"{indent}{line}")
                    
                    log_lines.append(f"{indent}--- 结束部分 ---")
                    
                    # 合并所有行并记录
                    logger.info('\n'.join(log_lines))
                else:
                    # 对于较短的内容，保留完整格式
                    log_lines = [f"[{request_id}] API响应内容:"]
                    # 添加4个空格缩进，保持格式清晰
                    indent = "    "
                    for line in content.split('\n'):
                        log_lines.append(f"{indent}{line}")
                    logger.info('\n'.join(log_lines))
            
            logger.info(f"[{request_id}] 请求成功，耗时: {elapsed_time:.2f}秒")
            
            return content
            
        except Exception as e:
            # 更新统计数据
            end_time = time.time()
            elapsed_time = end_time - start_time
            self.total_time += elapsed_time
            self.error_count += 1
            
            logger.error(f"[{request_id}] 请求失败，耗时: {elapsed_time:.2f}秒，错误: {str(e)}")
            
            # 如果启用了备选模型且当前不是备选模型，则尝试使用备选模型
            if use_backup_on_failure and self.current_model != self.backup_model:
                logger.info(f"[{request_id}] 尝试使用备选模型: {self.backup_model}")
                self.current_model = self.backup_model
                return self.chat_completion(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format=response_format,
                    use_backup_on_failure=False  # 防止无限递归
                )
            
            return None
    
    def json_completion(
        self, 
        messages: List[Dict[str, str]], 
        max_tokens: int = 2000,
        temperature: float = 0.5
    ) -> Optional[Dict]:
        """
        发送JSON格式的聊天补全请求
        
        Args:
            messages: 聊天消息列表
            max_tokens: 最大生成token数
            temperature: 温度（创造性）
            
        Returns:
            JSON格式的响应，失败时返回None
        """
        # 确保系统消息包含JSON输出说明
        has_system_message = False
        for msg in messages:
            if msg.get("role") == "system":
                if "JSON" not in msg.get("content", ""):
                    msg["content"] += " You are a helpful assistant designed to output JSON."
                has_system_message = True
                break
        
        if not has_system_message:
            messages.insert(0, {
                "role": "system",
                "content": "You are a helpful assistant designed to output JSON."
            })
        
        # 设置JSON响应格式
        response_format = {"type": "json_object"}
        
        # 发送请求
        content = self.chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format
        )
        
        if content:
            try:
                json_result = json.loads(content)
                
                if self.verbose_logging:
                    # 记录解析后的JSON
                    json_str = json.dumps(json_result, ensure_ascii=False, indent=2)
                    logger.info(f"解析后的JSON响应:\n{json_str}")
                
                return json_result
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {str(e)}")
                logger.debug(f"原始内容: {content}")
                return None
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取接口统计数据
        
        Returns:
            统计数据字典
        """
        avg_time = self.total_time / self.call_count if self.call_count > 0 else 0
        success_rate = (self.call_count - self.error_count) / self.call_count * 100 if self.call_count > 0 else 0
        
        return {
            "call_count": self.call_count,
            "error_count": self.error_count,
            "success_rate": f"{success_rate:.2f}%",
            "total_tokens": self.total_tokens,
            "total_time": f"{self.total_time:.2f}秒",
            "avg_time": f"{avg_time:.2f}秒/请求",
            "current_model": self.current_model
        }
    
    def reset_model(self):
        """重置为默认模型"""
        self.current_model = self.primary_model
        logger.info(f"已重置为默认模型: {self.current_model}")

    async def get_chat_response(self, messages: List[Dict[str, Any]]) -> str:
        """
        获取LLM聊天回复（异步版本）
        
        Args:
            messages: 聊天消息列表
            
        Returns:
            生成的文本，如果发生错误则返回错误消息
        """
        try:
            # 向客户端添加系统提醒（当消息数量大于3且不包含提醒时）
            system_reminder = """记住：
1. 你需要分析每个命令执行结果，特别注意错误和异常情况
2. 注意观察SQL注入测试中的页面变化，包括空白页面和错误页面
3. 必须正确解读ORDER BY测试的结果来确定列数
4. 使用UNION SELECT确定哪些列可以回显数据
5. 一旦获得关键信息，根据这些信息调整后续查询
6. 所有分析和解释必须使用中文
7. 你的输出必须是命令，每行一个，不要添加任何前缀
8. 特别注意分析HTML代码，寻找验证码和隐藏字段
9. 仔细分析页面结构和CSS类名，以便更精确地定位元素
10. 观察HTML中的表单结构，确保正确识别所有输入字段尤其是验证码字段
"""
            
            # 检查是否已经有系统提醒消息
            has_reminder = False
            for msg in messages:
                if msg.get("role") == "system" and "记住：" in str(msg.get("content", "")):
                    has_reminder = True
                    break
            
            # 如果消息数量大于3且没有系统提醒，添加一个
            messages_with_reminder = messages.copy()
            if len(messages) > 3 and not has_reminder:
                # 插入在第二个位置（通常系统提示之后）
                messages_with_reminder.insert(1, {"role": "system", "content": system_reminder})
            else:
                messages_with_reminder = messages
            
            # 记录请求信息
            request_id = f"req-{int(time.time())}"
            logger.info(f"[{request_id}] 发送聊天请求，消息数量: {len(messages_with_reminder)}")
            
            # 记录消息总大小
            total_chars = sum(len(str(msg.get("content", ""))) for msg in messages_with_reminder)
            logger.info(f"[{request_id}] 总字符数: {total_chars}")
            
            # 获取聊天补全
            content = self.chat_completion(
                messages=messages_with_reminder,
                max_tokens=1024,
                temperature=0.3
            )
            
            # 如果响应为空，返回默认消息
            if not content:
                logger.error(f"[{request_id}] LLM返回了空内容")
                return "SCREENSHOT\nTHINK API返回了空内容，需要检查API配置"
            
            # 记录响应内容
            logger.info(f"[{request_id}] 接收到响应，长度: {len(content)}字符")
            logger.info(f"[{request_id}] 响应内容(截断):\n{content[:500]}..." + ("" if len(content) <= 500 else f"\n... 截断，完整长度: {len(content)}字符"))
            
            return content
                
        except Exception as e:
            logger.error(f"获取聊天响应出错: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 返回错误信息作为响应
            return f"SCREENSHOT\nTHINK LLM调用出错: {str(e)}"

# 简单的测试函数
def test_llm_interface():
    """测试LLM接口"""
    llm = LLMInterface()
    
    # 测试普通补全
    messages = [
        {"role": "user", "content": "请简要介绍自己，不要超过50个字"}
    ]
    
    print("发送普通补全请求...")
    response = llm.chat_completion(messages)
    print(f"响应: {response}")
    
    # 测试JSON补全
    json_messages = [
        {"role": "user", "content": "我喜欢吃苹果和香蕉。请以JSON格式返回我喜欢的水果列表，键名为'fruits'"}
    ]
    
    print("\n发送JSON补全请求...")
    json_response = llm.json_completion(json_messages)
    print(f"JSON响应: {json.dumps(json_response, ensure_ascii=False, indent=2)}")
    
    # 输出统计信息
    print("\n统计信息:")
    stats = llm.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    test_llm_interface() 