#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
轨迹流动API连接测试脚本
用于验证API密钥、连接状态和模型响应
"""

import os
import json
import time
import socket
import traceback
from dotenv import load_dotenv

# 加载环境变量（如果有.env文件）
load_dotenv()

# API配置 - 可直接修改或通过环境变量设置
API_KEY = os.getenv('SILICONFLOW_API_KEY', 'YOUR_API_KEY')
BASE_URL = os.getenv('SILICONFLOW_API_URL', 'https://api.siliconflow.cn/v1')
MODEL_LIST = [
    "Qwen/QwQ-32B",          # 原始设置的模型
    "deepseek-ai/DeepSeek-V2.5",  # 用户示例中的模型
    "01-ai/Yi-1.5-34B"       # 其他可用模型
]

def test_dns_connectivity(api_url):
    """测试DNS解析和TCP连接"""
    print("\n=== 测试DNS和TCP连接 ===")
    
    try:
        # 提取主机名
        api_host = api_url.split("://")[1].split("/")[0]
        print(f"API主机名: {api_host}")
        
        # DNS解析
        start_time = time.time()
        ip_address = socket.gethostbyname(api_host)
        dns_time = time.time() - start_time
        print(f"✓ DNS解析成功: {api_host} -> {ip_address} (耗时: {dns_time:.3f}秒)")
        
        # TCP连接测试
        start_time = time.time()
        socket_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_conn.settimeout(5)
        result = socket_conn.connect_ex((api_host, 443))
        tcp_time = time.time() - start_time
        
        if result == 0:
            print(f"✓ TCP连接成功，端口443开放 (耗时: {tcp_time:.3f}秒)")
        else:
            print(f"✗ TCP连接失败，端口443可能被封锁，错误码: {result}")
        socket_conn.close()
        
        return True
    except Exception as e:
        print(f"✗ 网络连接测试失败: {str(e)}")
        return False

def test_api_with_openai(api_key, base_url, model):
    """使用OpenAI客户端库测试API"""
    print(f"\n=== 测试模型: {model} ===")
    
    try:
        from openai import OpenAI
        
        # 创建客户端
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # 准备简单请求
        test_prompt = "你好，请用一句话回答我。"
        
        # 记录时间并发送请求
        print(f"发送请求: '{test_prompt}'")
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": test_prompt}
            ],
            max_tokens=50,
            temperature=0.7
        )
        
        # 计算响应时间
        request_time = time.time() - start_time
        
        # 输出结果
        print(f"✓ 请求成功! 响应时间: {request_time:.2f}秒")
        content = response.choices[0].message.content.strip()
        print(f"响应内容: \"{content}\"")
        
        # 显示更多响应信息
        model_used = response.model
        finish_reason = response.choices[0].finish_reason
        
        print(f"完成原因: {finish_reason}")
        print(f"实际使用模型: {model_used}")
        
        return True, content
    
    except ImportError as e:
        print("✗ 错误: 未安装OpenAI客户端库")
        print("  请运行: pip install openai")
        return False, None
        
    except Exception as e:
        print(f"✗ API请求失败: {str(e)}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False, None

def test_api_with_requests(api_key, base_url, model):
    """使用requests库测试API"""
    print(f"\n=== 使用Requests测试模型: {model} ===")
    
    try:
        import requests
        
        # 准备请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "你好，请用一句话回答我。"}],
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        print("发送请求...")
        start_time = time.time()
        
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        request_time = time.time() - start_time
        
        # 检查响应
        if response.status_code == 200:
            print(f"✓ 请求成功! 响应时间: {request_time:.2f}秒")
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            print(f"响应内容: \"{content}\"")
            return True, content
        else:
            print(f"✗ 请求失败，状态码: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False, None
            
    except Exception as e:
        print(f"✗ API请求失败: {str(e)}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return False, None

def main():
    """主测试函数"""
    print("=" * 60)
    print("轨迹流动API连接测试")
    print("=" * 60)
    print(f"API URL: {BASE_URL}")
    print(f"API KEY: {API_KEY[:8]}...{API_KEY[-4:]}")
    
    # 测试网络连接
    network_ok = test_dns_connectivity(BASE_URL)
    if not network_ok:
        print("\n[警告] 网络连接测试失败，但仍将尝试API请求")
    
    # 尝试导入OpenAI库
    try:
        import openai
        print(f"\n发现OpenAI库 v{openai.__version__}")
        use_openai = True
    except ImportError:
        print("\n未安装OpenAI库，将使用requests库代替")
        use_openai = False
    
    # 测试每个模型
    successful_models = []
    
    for model in MODEL_LIST:
        if use_openai:
            success, _ = test_api_with_openai(API_KEY, BASE_URL, model)
        else:
            success, _ = test_api_with_requests(API_KEY, BASE_URL, model)
            
        if success:
            successful_models.append(model)
    
    # 总结结果
    print("\n" + "=" * 60)
    print("测试结果摘要:")
    
    if successful_models:
        print(f"✓ 成功连接 {len(successful_models)}/{len(MODEL_LIST)} 个模型")
        print("可用模型:")
        for model in successful_models:
            print(f"  - {model}")
        print("\n恭喜！API连接正常工作。")
    else:
        print("✗ 所有模型测试均失败")
        print("\n请检查以下可能的问题:")
        print("1. API密钥是否正确")
        print("2. 网络连接是否稳定")
        print("3. 是否需要配置代理服务器")
        print("4. 模型名称是否正确")

if __name__ == "__main__":
    main() 