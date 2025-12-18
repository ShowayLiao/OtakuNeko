# src/agent/refiner.py
from .base import BaseAgent
from src.config.personas import ROLES, TEMPLATES

class RefinerAgent(BaseAgent):
    """
    RefinerAgent: 专门处理模糊指令、情绪宣泄或无意义输入的 Agent。
    它的目标不是执行任务，而是通过对话明确用户的真实需求。
    """
    def __init__(self, llm_service, bgm_service):
        super().__init__(llm_service, bgm_service)

    def clarify(self, user_input, style="cat"):
        """
        处理模糊指令，生成追问或引导性回复
        Returns:
            str: 完整的回复文本 (非流式，因为通常很短)
        """
        print(f"🤔 [Refiner] 正在澄清模糊指令: {user_input}...")

        # 1. 获取人设配置
        # 默认为 cat
        persona_key = "cat" if style == "cat" else "normal"
        persona = ROLES.get(persona_key, ROLES["cat"])

        role_def = persona["system_prompt"]
        refiner_tone = persona.get("refiner_tone", "礼貌引导")

        # 2. 构建 Prompt
        try:
            prompt = TEMPLATES["refiner_task"].format(
                role_def=role_def,
                user_input=user_input,
                refiner_tone=refiner_tone
            )
        except KeyError as e:
            return f"系统配置错误: {e}"

        # 3. 调用 LLM
        try:
            response = self.run(
                messages=[
                    # 注意：system prompt 已经在模板里包含了，这里可以直接用 user 发送全部
                    # 或者拆分也可以，这里为了简单直接发
                    {"role": "user", "content": prompt}
                ],
                stream=False,
                temperature=1.1, # 稍微高一点，让回复更有灵性
                timeout=15
            )
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"❌ Refiner Error: {e}")
            return f"系统有点晕喵... ({str(e)})"