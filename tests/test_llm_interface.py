#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
LLM接口测试
"""

import os
import pytest
from unittest.mock import MagicMock, patch
import json

# 导入要测试的模块
from modules.llm_interface import LLMInterface

class TestLLMInterface:
    """测试LLM接口类"""
    
    @pytest.fixture
    def llm_interface(self):
        """创建LLM接口实例"""
        # 设置测试环境变量
        os.environ['SILICONFLOW_API_KEY'] = 'test_api_key'
        
        # 使用补丁模拟OpenAI客户端
        with patch('modules.llm_interface.OpenAI') as mock_openai:
            # 配置模拟对象
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            
            # 创建接口实例
            llm = LLMInterface(
                api_key='test_api_key',
                model='test-model',
                backup_model='backup-model'
            )
            
            # 注入模拟客户端
            llm.client = mock_client
            yield llm
    
    def test_initialization(self, llm_interface):
        """测试初始化"""
        assert llm_interface.api_key == 'test_api_key'
        assert llm_interface.primary_model == 'test-model'
        assert llm_interface.backup_model == 'backup-model'
        assert llm_interface.current_model == 'test-model'
        assert llm_interface.call_count == 0
        assert llm_interface.error_count == 0
    
    def test_chat_completion_success(self, llm_interface):
        """测试聊天补全成功"""
        # 配置模拟响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '测试响应'
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        
        # 配置模拟客户端
        llm_interface.client.chat.completions.create.return_value = mock_response
        
        # 执行测试
        messages = [{"role": "user", "content": "测试消息"}]
        result = llm_interface.chat_completion(messages)
        
        # 验证结果
        assert result == '测试响应'
        assert llm_interface.call_count == 1
        assert llm_interface.error_count == 0
        assert llm_interface.total_tokens == 30
        
        # 验证调用参数
        llm_interface.client.chat.completions.create.assert_called_with(
            model='test-model',
            messages=messages,
            max_tokens=4000,
            temperature=0.7,
            response_format=None
        )
    
    def test_chat_completion_failure_with_backup(self, llm_interface):
        """测试聊天补全失败时使用备选模型"""
        # 配置主模型失败
        llm_interface.client.chat.completions.create.side_effect = [
            Exception("模型不可用"),  # 第一次调用主模型失败
            MagicMock(  # 第二次调用备选模型成功
                choices=[MagicMock(message=MagicMock(content='备选响应'))],
                usage=MagicMock(prompt_tokens=5, completion_tokens=10)
            )
        ]
        
        # 执行测试
        messages = [{"role": "user", "content": "测试消息"}]
        result = llm_interface.chat_completion(messages)
        
        # 验证结果
        assert result == '备选响应'
        assert llm_interface.call_count == 2  # 两次调用
        assert llm_interface.error_count == 1  # 一次错误
        assert llm_interface.current_model == 'backup-model'  # 已经切换到备选模型
        assert llm_interface.total_tokens == 15
    
    def test_chat_completion_complete_failure(self, llm_interface):
        """测试聊天补全完全失败"""
        # 配置所有模型都失败
        llm_interface.client.chat.completions.create.side_effect = Exception("API错误")
        
        # 执行测试
        messages = [{"role": "user", "content": "测试消息"}]
        result = llm_interface.chat_completion(
            messages=messages,
            use_backup_on_failure=False  # 禁用备选模型
        )
        
        # 验证结果
        assert result is None
        assert llm_interface.call_count == 1
        assert llm_interface.error_count == 1
    
    def test_json_completion(self, llm_interface):
        """测试JSON补全"""
        # 配置模拟响应
        json_response = '{"result": "success", "data": [1, 2, 3]}'
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json_response
        mock_response.usage.prompt_tokens = 15
        mock_response.usage.completion_tokens = 25
        
        # 配置模拟客户端
        llm_interface.client.chat.completions.create.return_value = mock_response
        
        # 执行测试
        messages = [{"role": "user", "content": "返回JSON"}]
        result = llm_interface.json_completion(messages)
        
        # 验证结果
        assert result == json.loads(json_response)
        assert llm_interface.call_count == 1
        
        # 验证调用参数
        call_args = llm_interface.client.chat.completions.create.call_args
        assert call_args[1]['response_format'] == {"type": "json_object"}
    
    def test_reset_model(self, llm_interface):
        """测试重置模型"""
        # 切换到备选模型
        llm_interface.current_model = 'backup-model'
        
        # 重置模型
        llm_interface.reset_model()
        
        # 验证结果
        assert llm_interface.current_model == 'test-model'
    
    def test_get_stats(self, llm_interface):
        """测试获取统计数据"""
        # 设置统计数据
        llm_interface.call_count = 10
        llm_interface.error_count = 2
        llm_interface.total_tokens = 500
        llm_interface.total_time = 5.5
        
        # 获取统计
        stats = llm_interface.get_stats()
        
        # 验证结果
        assert stats['call_count'] == 10
        assert stats['error_count'] == 2
        assert stats['success_rate'] == '80.00%'
        assert stats['total_tokens'] == 500
        assert stats['total_time'] == '5.50秒'
        assert stats['avg_time'] == '0.55秒/请求'
        assert stats['current_model'] == 'test-model' 