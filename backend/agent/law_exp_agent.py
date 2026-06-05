import os


class law_exp_agent:
    # 测试管道一：接入agent让llm调用管道一的tool，返回一个响应结果
    # 接入模型：deepseek-v4-pro
    # agent 需要的内部方法：
    # 1、
    def __init__(self):
        pass

    def run(self, query):
        step = 0
        # 主循环 mock 10 步
        while step < 10:
            step += 1
            query = self.model.generate(query)
            break
        return self.model.generate(query)