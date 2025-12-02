"""
使用fofa搜索上一阶段提取的指纹，并统计数量。
算法：取前10条进行相似度判断，如果有5成以上，那么认为这一条是有效的指纹。
"""
import base64
import logging
import warnings
import sys
from typing import Dict

import httpx
import requests


warnings.filterwarnings('ignore', message='Unverified HTTPS request')
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # 关键：stdout
)
logger = logging.getLogger(__name__)

class FofaSearch:
    def __init__(self, config: Dict, query: str):
        self.config = config
        self.query = query

    
    def fofa_query(self) -> list:
        """
        Args: 
            pre_finger: LLM输出的候选指纹
        """
        fofa_api: str = self.config["fofa_api"]
        fofa_api_key: str = self.config["fofa_api_key"]
        query_base64: str = base64.b64encode(self.query.encode()).decode()

        api_url: str = f"{fofa_api}?key={fofa_api_key}&size=10000&qbase64={query_base64}&fields=ip,port,host,icp,link"
        try:
            resp = httpx.get(api_url, timeout=60)  # TODO 设置一个全局变量，对FOFA api调用次数进行计数
            resp.raise_for_status()
            if resp.json().get("results"):
                data: list = resp.json().get("results", [])
                return data
            else:
                return []
        except httpx.RequestError as e:
            logger.error(f"请求 fofa_api 时发生错误: {e}")
            return []