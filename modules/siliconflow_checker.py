#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SiliconFlow API检查器
用于检查和测试不同SiliconFlow模型的连接性
"""

import json
import socket
import time
import urllib.parse
import os
import traceback
from typing import Dict, List, Optional, Tuple, Union

import requests
from openai import OpenAI

class SiliconFlowChecker:
    """SiliconFlow API连接检查器"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.siliconflow.cn/v1"):
        """
        初始化SiliconFlow检查器
        
        Args:
            api_key: SiliconFlow API密钥，如果为None则尝试从环境变量获取
            base_url: SiliconFlow API基础URL
        """
        self.api_key = api_key or os.getenv('SILICONFLOW_API_KEY', 'YOUR_API_KEY')
        self.base_url = base_url
        self.timeout = 30  # 默认超时时间（秒）
        
        # 推荐模型列表
        self.recommended_models = [
            "deepseek-ai/DeepSeek-V3", 
            "deepseek-ai/DeepSeek-V2.5", 
            "01-ai/Yi-VL-34B",
            "Qwen/Qwen2-72B-Instruct"
        ]
        
        # 存储测试结果
        self.test_results = {}
        
    def check_dns_resolution(self, hostname: str = None) -> Tuple[bool, str]:
        """
        检查DNS解析
        
        Args:
            hostname: 主机名，默认从base_url提取
            
        Returns:
            (成功状态, 结果消息)
        """
        if hostname is None:
            hostname = urllib.parse.urlparse(self.base_url).netloc
            
        print(f"检查DNS解析: {hostname}")
        try:
            start_time = time.time()
            ip_address = socket.gethostbyname(hostname)
            resolution_time = time.time() - start_time
            
            return True, f"DNS解析成功: {hostname} -> {ip_address} (耗时: {resolution_time:.2f}秒)"
        except socket.gaierror as e:
            return False, f"DNS解析失败: {hostname}, 错误: {str(e)}"
    
    def check_tcp_connection(self, hostname: str = None, port: int = 443) -> Tuple[bool, str]:
        """
        检查TCP连接
        
        Args:
            hostname: 主机名，默认从base_url提取
            port: 端口号，默认443（HTTPS）
            
        Returns:
            (成功状态, 结果消息)
        """
        if hostname is None:
            hostname = urllib.parse.urlparse(self.base_url).netloc
            
        print(f"检查TCP连接: {hostname}:{port}")
        try:
            start_time = time.time()
            with socket.create_connection((hostname, port), timeout=10) as sock:
                connection_time = time.time() - start_time
                return True, f"TCP连接成功: {hostname}:{port} (耗时: {connection_time:.2f}秒)"
        except (socket.timeout, socket.error) as e:
            return False, f"TCP连接失败: {hostname}:{port}, 错误: {str(e)}"
    
    def test_model_connection(self, model_name: str) -> Tuple[bool, Dict]:
        """
        测试指定模型的连接
        
        Args:
            model_name: 要测试的模型名称
            
        Returns:
            (成功状态, 详细结果数据)
        """
        result = {
            "model": model_name,
            "status": "失败",
            "time_taken": 0,
            "error": None,
            "response": None
        }
        
        print(f"\n测试模型: {model_name}")
        
        # 创建OpenAI客户端
        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )
        
        # 准备测试请求
        messages = [
            {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
            {"role": "user", "content": "返回一个简单的JSON，包含字段：success和message，值都是字符串。"}
        ]
        
        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=100,
                temperature=0
            )
            
            # 更新结果
            result["time_taken"] = time.time() - start_time
            result["status"] = "成功"
            result["response"] = response.choices[0].message.content
            
            print(f"✓ 成功连接到模型: {model_name} (耗时: {result['time_taken']:.2f}秒)")
            print(f"响应: {result['response']}")
            
            return True, result
            
        except Exception as e:
            # 更新结果
            result["time_taken"] = time.time() - start_time
            result["error"] = str(e)
            
            print(f"✗ 连接模型失败: {model_name}")
            print(f"错误: {str(e)}")
            
            return False, result
    
    def test_all_recommended_models(self) -> Dict:
        """
        测试所有推荐模型
        
        Returns:
            测试结果字典
        """
        print(f"开始测试所有推荐的SiliconFlow模型...")
        
        # 先检查DNS和TCP连接
        dns_result = self.check_dns_resolution()
        tcp_result = self.check_tcp_connection()
        
        # 如果基础连接失败，返回结果
        if not dns_result[0] or not tcp_result[0]:
            return {
                "dns_check": dns_result[1],
                "tcp_check": tcp_result[1],
                "model_tests": "跳过 - 基础连接失败",
                "successful_models": []
            }
        
        # 测试所有推荐模型
        successful_models = []
        all_results = {}
        
        for model in self.recommended_models:
            success, result = self.test_model_connection(model)
            all_results[model] = result
            if success:
                successful_models.append(model)
        
        # 保存并返回结果
        self.test_results = {
            "dns_check": dns_result[1],
            "tcp_check": tcp_result[1],
            "model_tests": all_results,
            "successful_models": successful_models
        }
        
        # 显示摘要
        print("\n" + "=" * 60)
        print(f"测试完成! 共测试了 {len(self.recommended_models)} 个模型，{len(successful_models)} 个成功")
        print(f"成功模型: {', '.join(successful_models) if successful_models else '无'}")
        print("=" * 60)
        
        return self.test_results
        
    def get_best_available_model(self) -> Optional[str]:
        """
        获取最佳可用模型
        
        Returns:
            可用的最佳模型名称，如果没有则返回None
        """
        # 如果没有测试结果，先运行测试
        if not self.test_results:
            self.test_all_recommended_models()
            
        # 返回第一个成功的模型
        return self.test_results.get("successful_models", [None])[0]
    
    def get_model_specific_timeout(self, model_name: str) -> int:
        """
        获取特定模型推荐的超时设置
        
        Args:
            model_name: 模型名称
            
        Returns:
            推荐的超时秒数
        """
        timeout_map = {
            "deepseek-ai/DeepSeek-V3": 60,
            "deepseek-ai/DeepSeek-V2.5": 45,
            "01-ai/Yi-VL-34B": 90,
            "Qwen/Qwen2-72B-Instruct": 60
        }
        
        return timeout_map.get(model_name, 30)

def test_siliconflow_api():
    """测试SiliconFlow API连接并显示结果"""
    checker = SiliconFlowChecker()
    results = checker.test_all_recommended_models()
    
    best_model = checker.get_best_available_model()
    if best_model:
        timeout = checker.get_model_specific_timeout(best_model)
        print(f"\n推荐使用模型: {best_model}")
        print(f"建议超时设置: {timeout}秒")
    else:
        print("\n警告: 没有可用的SiliconFlow模型")
        print("请检查您的网络连接和API密钥")
    
    return results

if __name__ == "__main__":
    test_siliconflow_api() 