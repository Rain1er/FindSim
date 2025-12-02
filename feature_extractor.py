"""
网站特征提取模块
提取图标MD5、src、href等关键资源
"""

import httpx
from urllib.parse import urljoin, urlparse
from typing import Dict, List
import logging
import re
import base64
import mmh3
import sys
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # 关键：stdout
)
logger = logging.getLogger(__name__)


class WebsiteFeatureExtractor:
    """网站特征提取器"""
    
    def __init__(self, url: str, timeout: int = 10, enable_favicon: bool = True):
        """
        初始化特征提取器
        
        Args:
            url: 目标网站URL
            timeout: 请求超时时间
            enable_favicon: 是否启用favicon hash提取
        """
        self.url = url
        self.timeout = timeout
        self.enable_favicon = enable_favicon
        self.client = httpx.Client(
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            verify=False,
            follow_redirects=True,
            timeout=timeout
        )
    
    def extract_all_features(self) -> Dict:
        """提取网站关键特征"""
        features = {
            'url': self.url,
            'favicon_hash': self.get_favicon_hash() if self.enable_favicon else "",
            'resources': self.extract_resources()
        }
        return features

    def get_favicon_hash(self) -> str:
        """获取网站图标的 mmh3 哈希值（base64编码后计算）"""
        try:
            favicon_paths = ['/favicon.ico', '/favicon.png']

            # 尝试从HTML中获取favicon链接
            try:
                response = self.client.get(self.url)
                html_content = response.text

                # 使用正则提取icon相关的link标签
                icon_pattern = r'<link[^>]+rel=["\'](?:[^"\']*\s)?icon(?:\s[^"\']*)?["\'][^>]*href=["\']([^"\']+)["\']'
                icon_match = re.search(icon_pattern, html_content, re.IGNORECASE)

                if not icon_match:
                    # 尝试另一种顺序的正则: href在前, rel在后
                    icon_pattern = r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\'](?:[^"\']*\s)?icon(?:\s[^"\']*)?["\']'
                    icon_match = re.search(icon_pattern, html_content, re.IGNORECASE)

                if icon_match:
                    favicon_url = urljoin(self.url, icon_match.group(1))
                    favicon_paths.insert(0, urlparse(favicon_url).path)
            except Exception as e:
                logger.warning(f"无法从HTML解析favicon: {e}")

            # 尝试下载favicon
            for path in favicon_paths:
                favicon_url = urljoin(self.url, path)
                try:
                    response = self.client.get(favicon_url)
                    if response.status_code == 200:
                        # 使用 mmh3.hash(base64.encodebytes(content)) 计算哈希，这是FOFA的算法
                        favicon_content = response.content
                        favicon_base64 = base64.encodebytes(favicon_content)
                        favicon_hash = mmh3.hash(favicon_base64)
                        hash_str = str(favicon_hash)
                        logger.info(f"成功获取favicon hash: {hash_str}")
                        return hash_str
                except Exception as e:
                    continue

            return ""
        except Exception as e:
            logger.error(f"获取favicon hash失败: {e}")
            return ""
    
    def extract_resources(self) -> Dict[str, List[str]]:
        """使用正则表达式提取网页中的所有资源(src和href)"""
        try:
            response = self.client.get(self.url)
            html_content = response.text
            
            resources = {
                'all_srcs': [],
                'all_hrefs': []
            }
            
            # 提取所有src属性（包括重复的）
            all_srcs = self._extract_all_attributes(html_content, 'src')
            
            # 提取所有href属性（包括重复的）
            all_hrefs = self._extract_all_attributes(html_content, 'href')
            
            # 转换为完整URL
            for src in all_srcs:
                full_url = urljoin(self.url, src)
                resources['all_srcs'].append(full_url)
            
            for href in all_hrefs:
                full_url = urljoin(self.url, href)
                resources['all_hrefs'].append(full_url)
            
            return resources
        except Exception as e:
            logger.error(f"提取资源失败: {e}")
            return {
                'all_srcs': [],
                'all_hrefs': []
            }
    
    def _extract_all_attributes(self, html_content: str, attr_name: str) -> set:
        """
        从HTML源码中提取所有指定属性的值（包括重复的）
        
        Args:
            html_content: HTML源码
            attr_name: 属性名（如'src'或'href'）
        
        Returns:
            属性值的集合
        """
        values = set()
        
        # 匹配 attr="value" 或 attr='value'
        pattern = rf'{attr_name}\s*=\s*["\']([^"\']+)["\']'
        
        for match in re.finditer(pattern, html_content, re.IGNORECASE):
            value = match.group(1)
            # 去除查询参数
            if '?' in value:
                value = value.split('?', 1)[0]
            # 过滤掉特殊协议
            if attr_name == 'src':
                if not value.startswith(('data:', 'javascript:', 'about:', 'blob:')):
                    values.add(value)
            elif attr_name == 'href':
                if not value.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    values.add(value)
            else:
                values.add(value)
        
        return values
