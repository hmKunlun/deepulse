# Deepulse

一款多功能的Web应用安全测试工具，集成人工智能辅助分析功能和浏览器自动化能力，支持多种漏洞类型的测试和验证。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

## 项目概述

Deepulse是一个基于Python开发的网站安全测试框架，通过集成大语言模型和浏览器自动化技术，提供智能、高效的Web应用安全测试能力。系统能够模拟真实用户的浏览行为，自动探测和验证各类Web安全漏洞，包括SQL注入、XSS跨站脚本、命令注入和目录穿越等多种常见安全威胁。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt
playwright install

# 运行基本测试
python main.py -u http://testphp.vulnweb.com/ --tests sql,xss

# 使用交互式界面
python main.py --cli
```

## 核心功能

- **智能浏览器自动化**：集成Playwright实现真实的浏览器操作，支持复杂的用户交互
- **人工智能驱动分析**：基于大型语言模型进行智能决策和分析
- **自定义提示词功能**：支持用户在测试过程中动态指导AI行为
- **多种漏洞测试能力**：内置SQL注入、XSS、命令注入、路径遍历等测试模块
- **错误智能恢复**：具备自动错误检测和恢复机制
- **CLI交互界面**：提供用户友好的命令行交互式界面
- **多模型自动选择**：智能检测并选择最佳可用的AI模型
- **验证码识别策略**：通过AI分析识别页面验证码并提供处理建议

## 安装指南

### 环境要求

- Python 3.8+
- 支持Playwright运行的操作系统(Windows/Linux/MacOS)

### 安装步骤

1. 克隆项目到本地：

```bash
git clone https://github.com/yourusername/deepulse.git
cd deepulse
```

2. 安装项目依赖：

```bash
pip install -r requirements.txt
```

3. 安装浏览器驱动：

```bash
playwright install
```

4. 配置API密钥（可选）：

创建`.env`文件，设置以下环境变量（参考`.env.example`）：

```
SILICONFLOW_API_KEY=您的API密钥
SILICONFLOW_API_URL=https://api.example.com/v1
SILICONFLOW_MODEL=模型名称
SILICONFLOW_TIMEOUT=60
```

## 使用指南

### 命令行参数

Deepulse支持多种命令行参数，灵活配置测试行为：

```bash
# 基本测试
python main.py -u http://testphp.vulnweb.com/ --tests sql,xss

# 启用用户自定义提示词功能
python main.py -u http://testphp.vulnweb.com/ --tests sql,xss --user-prompt --prompt-frequency 3

# 使用交互式CLI界面
python main.py --cli
```

主要参数说明：

- `-u, --url`：目标URL
- `-t, --tests`：要测试的漏洞类型，用逗号分隔（sql,xss,csrf,file_upload,command_injection,all）
- `-d, --depth`：爬取深度
- `-c, --config`：配置文件路径
- `-a, --auth`：认证信息，格式为 username:password
- `--timeout`：测试超时时间（秒）
- `--interactive`：使用交互模式配置测试
- `--model`：指定使用的AI模型
- `--cli`：启动交互式命令行界面
- `--user-prompt`：启用用户自定义提示词功能
- `--prompt-frequency`：用户提示词输入频率（迭代次数）

### 交互式界面使用

Deepulse提供了直观的交互式命令行界面，使用简单：

1. 启动交互界面：
   ```bash
   python main.py --cli
   ```

2. 在主菜单中选择操作：
   - 开始漏洞测试
   - 配置测试参数
   - 加载/保存配置
   - 查看测试结果
   - 配置用户提示词功能
   - 查看关于信息

3. 按照界面提示完成配置并执行测试

## 用户自定义提示词功能

Deepulse的特色功能之一是支持用户在测试过程中提供自定义提示词，动态指导AI行为：

### 功能优势

- **灵活干预**：在自动测试过程中，根据实际情况调整测试策略
- **专家知识融入**：允许用户注入领域专业知识，提高测试精准度
- **解决复杂场景**：针对验证码、特殊登录流程等复杂场景提供定制指导
- **快速适应变化**：对目标网站行为变化做出及时响应

### 使用方法

1. **命令行方式启用**：
   ```bash
   python main.py -u http://example.com --tests sql,xss --user-prompt --prompt-frequency 3
   ```

2. **通过CLI界面配置**：
   - 启动CLI界面：`python main.py --cli`
   - 选择"7. 配置用户提示词功能"
   - 启用功能并设置频率
   - 返回主菜单后选择"1. 开始漏洞测试"

3. **提示词输入过程**：
   - 系统会在指定迭代次数后暂停，显示当前测试状态
   - 提供输入提示词的界面
   - 用户输入提示词后回车，或直接回车跳过

### 提示词示例

根据不同测试场景，可以提供各类提示词：

- **漏洞测试策略**：
  ```
  请尝试使用布尔型盲注的方法测试此登录表单
  ```

- **特殊场景处理**：
  ```
  页面上有图形验证码，请先尝试分析验证码图像，然后再提交表单
  ```

- **目标指导**：
  ```
  优先测试用户名字段，尝试提取管理员账户信息
  ```

- **测试参数建议**：
  ```
  对email字段尝试使用'"), 或'"))等不同闭合方式的输入
  ```

## 支持的漏洞类型

Deepulse目前支持以下漏洞类型的测试：

- **SQL注入（SQLi）**
  - 基于错误的SQL注入
  - 基于布尔的盲注
  - 基于时间的盲注
  - UNION查询注入

- **跨站脚本（XSS）**
  - 反射型XSS
  - 存储型XSS
  - DOM型XSS
  - 各种绕过技术

- **命令注入**
  - 直接命令执行
  - 命令分隔符注入
  - 参数注入

- **路径遍历**
  - 目录穿越
  - 文件包含漏洞
  - 各种路径规范化绕过

- **计划中的漏洞测试**
  - CSRF（跨站请求伪造）
  - 文件上传漏洞
  - SSRF（服务器端请求伪造）
  - XXE（XML外部实体）
  - 逻辑漏洞

## 项目结构

```
deepulse/
├── agent.py                 # 浏览器自动化代理
├── browser_use.py           # 浏览器操作核心类
├── test_vulnerability.py    # 漏洞测试脚本
├── main.py                  # 主程序入口
├── cli_interface.py         # 命令行交互界面
├── modules/                 # 主要模块
│   ├── site_analyzer.py     # 站点分析器 
│   ├── test_config.py       # 测试配置
│   ├── test_framework.py    # 测试思维框架
│   ├── siliconflow_checker.py # API检查器
│   ├── llm_interface.py     # LLM接口模块
│   └── testers/             # 漏洞测试模块
│       ├── base_tester.py         # 漏洞测试基类
│       ├── sql_injection.py       # SQL注入测试
│       ├── xss.py                 # XSS测试
│       ├── command_injection.py   # 命令注入测试
│       └── path_traversal.py      # 目录穿越测试
├── screenshots/             # 截图存储目录
├── docs/                    # 文档
│   └── PROGRESS.md          # 进度记录
├── logs/                    # 日志目录
├── tests/                   # 测试目录
├── requirements.txt         # 项目依赖
└── README.md                # 项目说明
```

## AI模型集成

Deepulse集成了大型语言模型，用于智能分析：

- **自动模型选择**：系统会自动测试并选择最佳可用模型
- **智能超时管理**：根据不同模型特性设置合理的超时参数
- **模型故障转移**：当首选模型不可用时，自动切换到备选模型
- **结构化数据处理**：支持JSON格式的响应处理
- **大上下文窗口利用**：支持发送完整HTML代码并进行智能分析

## 技术亮点

- **测试思维框架**：实现了四阶段测试方法论（信息收集、基准建立、漏洞评估、漏洞验证）
- **验证码智能处理**：通过多层次验证码检测（图像、文本、上下文）提高测试适应性
- **增强的页面分析**：改进页面元素分析，特别是表单和输入字段识别
- **智能浏览器交互**：模拟真实用户行为，支持复杂表单填写和页面交互
- **错误智能恢复**：在测试过程中自动检测异常并执行恢复策略

## 开发路线

**近期计划**：
- 强化验证码识别算法
- 测试框架优化（阶段转换、指导消息）
- 优化模型交互提示词
- 实现CSRF和文件上传测试模块

**中期计划**：
- 开发Web管理界面
- 实现爬虫功能，自动发现网站结构
- 增加并行测试能力
- 完善自动报告生成

**长期计划**：
- 支持API接口集成
- 添加企业级漏洞管理功能
- 实现更多高级漏洞测试
- 开发插件系统，支持自定义测试模块

## 免责声明

本工具仅用于合法的安全测试和教育目的。未经授权对系统进行测试可能违反法律法规。使用者对使用本工具的所有后果负完全责任。禁止对未获授权的系统进行测试。

## 贡献指南

欢迎贡献代码、提交问题报告或功能建议。请确保遵循以下准则：

1. 代码应遵循PEP 8风格指南
2. 提交新功能时应包含适当的测试
3. 重要更改应更新文档
4. 提交PR前请确保所有测试通过

## 许可证

本项目采用[MIT License](LICENSE)许可证。 
二开项目希望附上源地址，谢谢！