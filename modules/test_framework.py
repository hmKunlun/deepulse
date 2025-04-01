import time
from typing import List, Dict, Optional, Any, Tuple

class TestFramework:
    """
    集成测试框架(简化版)
    提供测试状态管理和指导消息功能
    """
    
    # 测试阶段常量
    PHASE_RECON = 1      # 信息收集阶段
    PHASE_BASELINE = 2   # 基准建立阶段
    PHASE_PLANNING = 3   # 漏洞评估规划阶段
    PHASE_EXPLOIT = 4    # 漏洞验证利用阶段
    
    def __init__(self):
        """初始化测试框架"""
        # 当前测试阶段
        self.current_phase = self.PHASE_RECON
        # 阶段进度(0-100)
        self.phase_progress = 0
        # 已发现的安全机制
        self.security_mechanisms = []
        # 已识别的输入点
        self.input_points = []
        # 上次发送指导消息的时间
        self.last_guidance_time = 0
        # 指导消息发送间隔(秒)
        self.guidance_interval = 30
        # 阶段转换后是否已发送过提示
        self.phase_intro_sent = {
            self.PHASE_RECON: True,      # 初始阶段默认已发送
            self.PHASE_BASELINE: False,
            self.PHASE_PLANNING: False,
            self.PHASE_EXPLOIT: False
        }
        # 记录测试发现
        self.discoveries = []
        # 命令计数器
        self.command_counter = 0
        
    def get_phase_name(self, phase=None) -> str:
        """获取测试阶段名称"""
        if phase is None:
            phase = self.current_phase
            
        phase_names = {
            self.PHASE_RECON: "信息收集",
            self.PHASE_BASELINE: "基准建立",
            self.PHASE_PLANNING: "漏洞评估",
            self.PHASE_EXPLOIT: "漏洞验证"
        }
        return phase_names.get(phase, "未知阶段")
        
    def get_current_guidance(self) -> str:
        """获取当前阶段的指导信息"""
        guidance = {
            self.PHASE_RECON: "全面观察网站结构和功能，识别安全机制，记录输入点",
            self.PHASE_BASELINE: "验证核心功能是否正常工作，使用有效输入测试正常流程",
            self.PHASE_PLANNING: "评估每个输入点的漏洞可能性，制定详细测试计划",
            self.PHASE_EXPLOIT: "系统化执行测试计划，验证所有可能的漏洞"
        }
        return guidance.get(self.current_phase, "按渗透测试流程进行")
        
    def get_initial_guidance(self) -> str:
        """获取初始指导消息"""
        return f"""
[系统] DeePulse测试启动，请遵循递进式测试方法：
1. 信息收集 - 先全面了解系统
2. 基准建立 - 再验证基本功能
3. 漏洞评估 - 然后制定测试计划
4. 漏洞验证 - 最后执行漏洞验证

当前阶段：{self.get_phase_name()}
[系统] {self.get_current_guidance()}
"""
    
    def process_command(self, command: str) -> Optional[str]:
        """
        处理命令并返回可能的指导消息
        如果需要发送指导消息，返回消息内容
        否则返回None
        """
        if not command:
            return None
            
        self.command_counter += 1
        
        # 解析命令
        cmd_parts = command.split(' ', 1)
        cmd_type = cmd_parts[0] if cmd_parts else ""
        cmd_content = cmd_parts[1] if len(cmd_parts) > 1 else ""
        
        # 更新测试状态
        self._update_state_from_command(cmd_type, cmd_content)
        
        # 检查是否需要发送阶段介绍
        phase_intro = self._check_phase_intro()
        if phase_intro:
            return phase_intro
            
        # 检查是否需要发送周期性指导
        if self._should_send_guidance():
            return self._get_guidance_message()
            
        # 检查是否有特定事件触发的指导
        event_guidance = self._check_event_guidance(cmd_type, cmd_content)
        if event_guidance:
            return event_guidance
            
        return None
        
    def _update_state_from_command(self, cmd_type: str, cmd_content: str) -> None:
        """根据命令更新测试状态"""
        # 信息收集阶段状态更新
        if self.current_phase == self.PHASE_RECON:
            # 识别安全机制
            if cmd_type == "THINK" and ("验证码" in cmd_content or "captcha" in cmd_content.lower()):
                self._add_security_mechanism("captcha", "验证码保护")
                self.phase_progress += 10
                
            # 识别其他安全机制
            if cmd_type == "THINK" and ("csrf" in cmd_content.lower() or "令牌" in cmd_content or "token" in cmd_content.lower()):
                self._add_security_mechanism("csrf", "CSRF令牌保护")
                self.phase_progress += 10
                
            # 识别输入点
            if cmd_type == "TYPE":
                parts = cmd_content.split(' ', 1)
                if len(parts) > 0:
                    self._add_input_point(parts[0], cmd_content)
                    self.phase_progress += 5
                    
            # 探索网站
            if cmd_type == "GOTO" or cmd_type == "CLICK":
                self.phase_progress += 3
                
            # 信息分析
            if cmd_type == "SCREENSHOT":
                self.phase_progress += 2
        
        # 基准建立阶段状态更新
        elif self.current_phase == self.PHASE_BASELINE:
            # 功能验证
            if cmd_type == "TYPE" and len(cmd_content.split(' ')) > 1:
                self.phase_progress += 5
                
            # 功能确认
            if cmd_type == "CLICK" and "登录" in cmd_content:
                self.phase_progress += 10
                self._add_discovery("尝试正常登录流程")
                
            # 验证码处理
            if cmd_type == "TYPE" and "验证码" in cmd_content:
                self.phase_progress += 8
                self._add_discovery("正确处理验证码")
                
        # 漏洞评估阶段状态更新
        elif self.current_phase == self.PHASE_PLANNING:
            # 漏洞分析
            if cmd_type == "THINK" and any(term in cmd_content.lower() for term in ["sql", "注入", "xss", "csrf", "漏洞"]):
                self.phase_progress += 10
                terms = ["sql注入", "xss", "csrf", "命令注入", "文件上传"]
                for term in terms:
                    if term in cmd_content.lower():
                        self._add_discovery(f"计划测试{term}漏洞")
                
        # 漏洞验证阶段状态更新
        elif self.current_phase == self.PHASE_EXPLOIT:
            # SQL注入测试
            if cmd_type == "TYPE" and any(term in cmd_content for term in ["'", "\"", "--", "UNION", "SELECT"]):
                self.phase_progress += 5
                self._add_discovery("执行SQL注入测试")
                
            # XSS测试
            if cmd_type == "TYPE" and any(term in cmd_content for term in ["<script>", "alert", "onerror", "javascript:"]):
                self.phase_progress += 5
                self._add_discovery("执行XSS注入测试")
                
        # 限制进度最大值
        self.phase_progress = min(100, self.phase_progress)
        
        # 检查阶段转换
        self._check_phase_transition()
        
    def _check_phase_transition(self) -> None:
        """检查是否应该转换到下一个阶段"""
        # 信息收集 -> 基准建立
        if self.current_phase == self.PHASE_RECON and self.phase_progress >= 80:
            # 已识别足够的安全机制和输入点
            if len(self.security_mechanisms) >= 1 and len(self.input_points) >= 2:
                self.current_phase = self.PHASE_BASELINE
                self.phase_progress = 0
                
        # 基准建立 -> 漏洞评估
        elif self.current_phase == self.PHASE_BASELINE and self.phase_progress >= 60:
            self.current_phase = self.PHASE_PLANNING
            self.phase_progress = 0
            
        # 漏洞评估 -> 漏洞验证
        elif self.current_phase == self.PHASE_PLANNING and self.phase_progress >= 70:
            self.current_phase = self.PHASE_EXPLOIT
            self.phase_progress = 0
            
    def _add_security_mechanism(self, mech_type: str, description: str) -> None:
        """添加安全机制"""
        # 检查是否已存在
        for mech in self.security_mechanisms:
            if mech.get("type") == mech_type:
                return
                
        self.security_mechanisms.append({
            "type": mech_type,
            "description": description,
            "timestamp": time.time()
        })
        
    def _add_input_point(self, selector: str, context: str) -> None:
        """添加输入点"""
        # 检查是否已存在
        for point in self.input_points:
            if point.get("selector") == selector:
                return
                
        self.input_points.append({
            "selector": selector,
            "context": context,
            "timestamp": time.time()
        })
        
    def _add_discovery(self, description: str) -> None:
        """添加测试发现"""
        self.discoveries.append({
            "description": description,
            "phase": self.current_phase,
            "timestamp": time.time()
        })
        
    def _should_send_guidance(self) -> bool:
        """检查是否应该发送周期性指导"""
        current_time = time.time()
        # 至少经过一定时间间隔
        if current_time - self.last_guidance_time < self.guidance_interval:
            return False
            
        # 根据命令数量控制频率（每10条命令可能触发一次）
        if self.command_counter % 10 != 0:
            return False
            
        self.last_guidance_time = current_time
        return True
        
    def _get_guidance_message(self) -> str:
        """获取周期性指导消息"""
        # 根据当前阶段和进度选择合适的指导消息
        guidance_by_phase = {
            self.PHASE_RECON: [
                "继续探索网站结构，确保不遗漏任何功能点",
                "特别注意隐藏的安全机制，如请求头中的令牌",
                f"已发现{len(self.security_mechanisms)}个安全机制和{len(self.input_points)}个输入点",
                "记住SCAN方法：勘察环境、关联信息、分析路径、决定行动"
            ],
            
            self.PHASE_BASELINE: [
                "确保验证所有主要功能，而不仅仅是登录功能",
                "记录系统如何处理边界情况和无效输入",
                "注意验证码刷新机制和错误处理方式",
                "记住SCAN方法：勘察环境、关联信息、分析路径、决定行动"
            ],
            
            self.PHASE_PLANNING: [
                "考虑不同类型的漏洞测试向量",
                "注意安全机制之间的相互作用",
                "记住规划测试顺序，从低风险测试开始",
                "记住SCAN方法：勘察环境、关联信息、分析路径、决定行动"
            ],
            
            self.PHASE_EXPLOIT: [
                "保持对验证码等安全机制的正确处理",
                "系统化验证每个潜在漏洞",
                "记录每个测试的详细结果",
                "记住SCAN方法：勘察环境、关联信息、分析路径、决定行动"
            ]
        }
        
        # 根据当前阶段选择消息组
        guidance_list = guidance_by_phase.get(self.current_phase, ["继续系统化测试"])
        
        # 根据进度选择指导消息
        if self.phase_progress < 30:
            index = 0
        elif self.phase_progress < 70:
            index = 1
        else:
            index = 2
            
        # 如果索引超出范围，使用最后一条消息
        if index >= len(guidance_list):
            index = len(guidance_list) - 1
            
        return f"[系统提示] {guidance_list[index]}"
        
    def _check_phase_intro(self) -> Optional[str]:
        """检查是否需要发送阶段介绍"""
        if not self.phase_intro_sent.get(self.current_phase, True):
            # 更新状态，避免重复发送
            self.phase_intro_sent[self.current_phase] = True
            
            # 准备阶段介绍
            phase_intros = {
                self.PHASE_BASELINE: f"""
[系统] 进入{self.get_phase_name()}阶段

在这个阶段，您需要：
1. 使用有效输入验证基本功能
2. 特别注意验证码等安全机制的正确处理
3. 记录正常响应和错误响应的特征

请确保基本功能正常工作，再考虑漏洞测试。
""",
                self.PHASE_PLANNING: f"""
[系统] 进入{self.get_phase_name()}阶段

在这个阶段，您需要：
1. 分析每个输入点可能存在的漏洞
2. 评估安全机制的有效性
3. 按威胁程度排序可能的漏洞
4. 制定详细的测试计划

请系统思考每个可能的漏洞点，而不是随机测试。
""",
                self.PHASE_EXPLOIT: f"""
[系统] 进入{self.get_phase_name()}阶段

在这个阶段，您需要：
1. 系统执行测试计划
2. 对每个输入点尝试适当的测试向量
3. 同时正确处理验证码等安全机制
4. 收集每个漏洞的证据

请记住，漏洞测试需要在保持系统稳定的前提下进行。
"""
            }
            
            return phase_intros.get(self.current_phase)
        
        return None
        
    def _check_event_guidance(self, cmd_type: str, cmd_content: str) -> Optional[str]:
        """检查是否有特定事件触发的指导"""
        # 验证码相关事件
        if self.current_phase >= self.PHASE_BASELINE:
            if cmd_type == "TYPE" and any(term in cmd_content.lower() for term in ["验证码", "captcha"]):
                return "[系统反馈] 正确处理验证码，这是漏洞测试中的重要一步"
                
            if cmd_type == "THINK" and "验证码错误" in cmd_content:
                return "[系统反馈] 验证码处理失败，尝试刷新获取新验证码"
                
        # SQL注入测试事件
        if self.current_phase == self.PHASE_EXPLOIT:
            if cmd_type == "TYPE" and any(term in cmd_content for term in ["'", "\"", "--", "UNION", "SELECT"]):
                return "[系统反馈] 正在测试SQL注入，请确保同时正确处理其他安全机制"
                
            if cmd_type == "TYPE" and any(term in cmd_content for term in ["<script>", "alert", "onerror"]):
                return "[系统反馈] 正在测试XSS漏洞，记得测试不同的XSS向量"
                
        # 思考方法指导
        if cmd_type == "THINK" and len(cmd_content) > 50:
            if "验证码" in cmd_content and "正确" not in cmd_content:
                return "[系统反馈] 考虑在测试漏洞前先处理好验证码等安全机制"
                
        return None 