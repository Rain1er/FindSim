"""
使用fofa搜索上一阶段提取的指纹，并统计数量。
算法：取前10条进行相似度判断，如果有5成以上，那么认为这一条是有效的指纹。
"""


import logging
import warnings
import sys
import requests


warnings.filterwarnings('ignore', message='Unverified HTTPS request')
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # 关键：stdout
)
logger = logging.getLogger(__name__)

class FofaSearch:
    def __init__(self, url: str, timeout: int = 10):
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fofa_query(self, pre_finger: list) -> list:
        """
        Args: 
            pre_finger: LLM输出的候选指纹
        """
        pass
