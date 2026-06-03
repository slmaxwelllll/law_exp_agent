class law_exp_agent:
    # 需要接收的参数有：keyword，strategic_plan

    # 需要初始化的对象有：
    # 1、模型和agent需要的参数：
    def __init__(self, model):
        self.model = model


    # agent 主循环
    def run(self, query):
        step = 0

        # 主循环 mock 10 步
        while step < 10:
            step += 1
            query = self.model.generate(query)
            break
        return self.model.generate(query)
