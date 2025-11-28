"""
DeepSeek API 集成模块
用于分析网站特征并识别指纹
"""

import json
import logging
from typing import Dict
from openai import OpenAI
import sys

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # 关键：stdout
)
logger = logging.getLogger(__name__)


class DeepSeekAnalyzer:
    """DeepSeek分析器"""
    
    def __init__(self, api_key: str):
        """
        初始化DeepSeek客户端
        
        Args:
            api_key: DeepSeek API密钥
        """
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    
    def analyze_features(self, features: Dict) -> Dict:
        """
        分析网站特征并识别指纹
        
        Args:
            features: 网站特征字典
            
        Returns:
            分析结果
        """
        try:
            # 构建提示词
            prompt = self._build_prompt(features)
            
            logger.info("正在调用DeepSeek API分析特征...")
            
            # 调用DeepSeek API
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个网站指纹识别专家。你的任务是从网站资源中排除通用组件和明显非指纹的信息，只提取可用于FOFA等搜索引擎检索同类网站的特征指纹。必须严格按JSON格式输出，不要添加任何额外文字。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            # 解析响应
            analysis_text = response.choices[0].message.content
            
            # 尝试解析JSON
            import json
            import re
            
            # 提取JSON内容
            json_match = re.search(r'```json\s*(.*?)\s*```', analysis_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 如果没有代码块，尝试直接解析
                json_str = analysis_text
            
            fingerprint_data = json.loads(json_str)
            
            result = {
                'success': True,
                'favicon_hash': fingerprint_data.get('favicon_hash', features.get('favicon_hash', '')),
                'fingerprints': fingerprint_data.get('fingerprints', []),
                'raw_response': analysis_text,
                'usage': {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                }
            }
            
            logger.info("DeepSeek分析完成")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {
                'success': False,
                'error': f'JSON解析失败: {str(e)}',
                'raw_response': analysis_text if 'analysis_text' in locals() else None,
                'fingerprints': []
            }
        except Exception as e:
            logger.error(f"DeepSeek分析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'fingerprints': []
            }
    
    def _build_prompt(self, features: Dict) -> str:
        """
        构建发送给DeepSeek的提示词
        
        Args:
            features: 网站特征字典
            
        Returns:
            格式化的提示词
        """
        resources = features.get('resources', {})
        
        prompt = f"""分析以下网站资源，排除通用组件，只返回可用于FOFA检索的特征信息。

**目标网站：** {features.get('url', 'N/A')}

**Favicon Hash (mmh3)：** {features.get('favicon_hash', '未获取')}

**所有src资源 (共{len(resources.get('all_srcs', []))}个)：**
{self._format_list(resources.get('all_srcs', [])[:50])}

**所有href资源 (共{len(resources.get('all_hrefs', []))}个)：**
{self._format_list(resources.get('all_hrefs', [])[:50])}

---

**任务：排除所有通用组件**
通用组件包括但不限于：
- CDN资源 (jsdelivr, cdnjs, unpkg, cloudflare, etc.)
- 公共库 (jquery, bootstrap, vue, react, angular, etc.)
- 通用广告/统计代码 (google-analytics, baidu统计, etc.)
- 社交媒体组件 (facebook, twitter, etc.)

**输出要求：**
严格按照以下JSON格式输出，不要添加任何其他内容：

```json
{{
  "favicon_hash": "{features.get('favicon_hash', '')}",
  "fingerprints": [
    "/path/to/custom/file.js",
    "/unique/api/endpoint",
    "/special/resource.css"
  ]
}}
```

注意：
1. 只输出JSON，不要任何解释文字
2. fingerprints数组只包含非通用的URL路径或完整URL
3. 如果全是通用组件，fingerprints为空数组
4. 保持原始favicon_hash值
"""
        return prompt
    
    def _format_list(self, items: list, max_items: int = 50) -> str:
        """格式化列表项"""
        if not items:
            return "  (无)"
        
        formatted = []
        for i, item in enumerate(items[:max_items], 1):
            formatted.append(f"  {i}. {item}")
        
        if len(items) > max_items:
            formatted.append(f"  ... 还有 {len(items) - max_items} 项")
        
        return "\n".join(formatted)
    
    def print_analysis(self, result: Dict):
        """
        格式化打印分析结果
        
        Args:
            result: 分析结果字典
        """
        print("\n" + "="*80)
        print("FOFA指纹识别结果")
        print("="*80)
        
        if result.get('success'):
            print(f"\n📌 Favicon Hash (mmh3): {result.get('favicon_hash', 'N/A')}")
            
            fingerprints = result.get('fingerprints', [])
            if fingerprints:
                print(f"\n🎯 可用于FOFA检索的指纹特征 ({len(fingerprints)}个):")
                for i, fp in enumerate(fingerprints, 1):
                    print(f"  {i}. {fp}")
                
                print("\n💡 FOFA检索语法示例:")
                if result.get('favicon_hash') and result['favicon_hash'] != '未找到favicon':
                    print(f'  icon_hash="{result["favicon_hash"]}"')
                if fingerprints:
                    print(f'  body="{fingerprints[0]}"')
                    if len(fingerprints) > 1:
                        print(f'  body="{fingerprints[0]}" && body="{fingerprints[1]}"')
            else:
                print("\n⚠️  未识别到特征指纹(全部为通用组件)")
            
            print("\n" + "-"*80)
            print(f"Token使用: {result.get('usage', {})}")
        else:
            print(f"\n❌ 分析失败: {result.get('error')}")
        
        print("="*80 + "\n")
