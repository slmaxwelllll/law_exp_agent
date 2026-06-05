# tool类，作为整体服务编排层
# 1、调用crawler获取抖音数据流
# 2、调用parser解析数据流，得到视频链接列表
# 3、对获取到的视频链接，根据media_type分类操作，
#    视频链接：先不管，舍弃，后续可能要接多模态模型。可以拿到音频，但是只有内容为作者本身是讲解视频，才需要提取音频
#    图片链接：尝试提取图片并ocr
from ..douyin_service.douyin_crawl import DouyinCrawlService
from ..douyin_service.douyin_data_parse import parse_douyin_data
class GetDouyinTool:
    def __init__(self):
        self.crawler = DouyinCrawlService()
    
    def run(self, keyword: str) -> list[dict]:
        """主流程"""
        data = self.crawler.search(keyword)
        result = parse_douyin_data(data)
        return result

if __name__ == "__main__":
    tool = GetDouyinTool()
    result = tool.run("肇事逃逸")
    
