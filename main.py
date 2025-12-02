"""
FindSim - 网站指纹识别工具
提取网站特征并使用LLM分析识别指纹
"""

import os
import sys
import argparse
from feature_extractor import WebsiteFeatureExtractor
from deepseek_analyzer import DeepSeekAnalyzer
import warnings
import json
import base64
import httpx
import logging
from typing import Dict, List
from urllib.parse import urlparse

from fofa_search import FofaSearch
from url_list_similarity import UrlListSimilarity

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # 关键：stdout
)
logger = logging.getLogger(__name__)


def load_urls_from_stdin() -> List[str]:
    """
    从标准输入读取URL列表
    支持管道输入，如: cat urls.txt | python main.py
    或者: echo "https://example.com" | python main.py
        
    Returns:
        URL列表
    """
    urls = []
    try:
        for line in sys.stdin:
            line = line.strip()
            # 跳过空行和注释行
            if line and not line.startswith('#'):
                # 验证URL格式
                if line.startswith(('http://', 'https://')):
                    urls.append(line)
                else:
                    logger.warning(f"跳过无效URL: {line}")
    except Exception as e:
        logger.error(f"从标准输入读取URL失败: {e}")
    return urls


def get_fingerprints_sum(fingerprints: List[str]) -> List[str]:
    """
    从fingerprints列表中提取文件名，并与原始指纹合并
    
    Args:
        fingerprints: 指纹路径列表
        
    Returns:
        原始指纹 + 文件名列表（去重，排除单层路径）
    
    Note:
        list(fingerprints) 是浅拷贝，创建了新的列表对象。
        由于列表元素是字符串（不可变对象），新旧列表中的字符串元素指向相同内存。
        但后续 append 的新元素只会添加到 result 中，不影响原 fingerprints 列表。
    """
    result = list(fingerprints)  # 浅拷贝：新列表对象，但字符串元素共享内存
    for fp in fingerprints:
        # 提取路径中的文件名
        filename = os.path.basename(fp)
        # 只有当路径包含多层目录时才添加文件名（避免/finger.html -> finger.html的情况）
        if filename and filename not in result and fp != f"/{filename}":
            result.append(filename)  # 新添加的元素只存在于 result 中
    return result

def load_config():
    """加载配置文件"""
    config_file = 'config.json'
    
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        logger.error("错误: 读取配置文件失败，请检查config.json")
        sys.exit(1)
        


def save_results(url: str, features: dict, analysis: dict, valid_results: List[Dict] = None, output_file: str = None):
    """
    保存分析结果到文件
    
    Args:
        url: 目标URL
        features: 网站特征
        analysis: AI分析结果
        valid_results: 有效指纹验证结果列表
        output_file: 输出文件路径
    """
    fingerprints = analysis.get('fingerprints', [])
    
    result = {
        'url': url,
        'favicon_hash': analysis.get('favicon_hash', features.get('favicon_hash', '')),
        'resources': features.get('resources', {}),
        'fingerprints': fingerprints,
        'fingerprints_sum': get_fingerprints_sum(fingerprints),
        'results': valid_results if valid_results else []
    }
    
    if not output_file:
        # 生成默认文件名
        domain = urlparse(url).netloc.replace('.', '_').replace(':', '-')
        output_file = f"./results/fingerprint_{domain}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n结果已保存到: {output_file}")


def print_features_summary(features: dict):
    """打印特征提取摘要"""
    resources = features.get('resources', {})
    
    logger.info("\n" + "="*80)
    logger.info("网站资源提取结果")
    logger.info("="*80)
    logger.info(f"URL: {features['url']}")
    if features['favicon_hash']:
        logger.info(f"Favicon Hash (mmh3): {features['favicon_hash']}")
    logger.info(f"src数量为: {len(resources.get('all_srcs', []))} 个")
    logger.info(f"href数量为: {len(resources.get('all_hrefs', []))} 个")
    
    logger.info("="*80)


def main():
    """主函数"""
    global analyzer, config
    parser = argparse.ArgumentParser(
        description='FindSim - FOFA指纹提取工具\n提取网站资源，通过LLM排除通用组件，输出可用于FOFA检索的指纹',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python main.py -u https://example.com
  python main.py -u https://example.com --no-analysis
  echo "https://example.com" | python main.py
        """
    )
    
    parser.add_argument('-u', '--url', help='要分析的网站URL (不指定时从标准输入读取)')
    parser.add_argument('-o', '--output', help='输出文件路径 (可选)')
    parser.add_argument('--no-analysis', action='store_true', help='只提取特征,不进行AI分析')
    parser.add_argument('-t', '--timeout', type=int, default=10, help='请求超时时间(秒), 默认10秒')
    
    args = parser.parse_args()
    
    # 获取URL列表
    urls = []
    if args.url:
        # 验证单个URL
        if not args.url.startswith(('http://', 'https://')):
            logger.error("ERROR: URL必须以 http:// 或 https:// 开头")
            sys.exit(1)
        urls = [args.url]
    else:
        # 从标准输入读取URL列表
        if sys.stdin.isatty():
            logger.error("ERROR: 请通过 -u 参数指定URL，或通过管道传入URL列表")
            logger.info("示例: echo 'https://example.com' | python main.py")
            logger.info("示例: cat urls.txt | python main.py")
            sys.exit(1)
        urls = load_urls_from_stdin()
        if not urls:
            logger.error("ERROR: 未从标准输入读取到有效URL")
            sys.exit(1)
        logger.info(f"从标准输入读取到 {len(urls)} 个URL")
    
    # 加载配置
    config = load_config()
    
    # 初始化分析器
    analyzer = None
    if not args.no_analysis:
        analyzer = DeepSeekAnalyzer(config['deepseek_api_key'])
    
    # 遍历处理每个URL
    for url in urls:
        process_single_url(url, args, config, analyzer)


def process_single_url(url: str, args, config: dict, analyzer):
    """
    处理单个URL的分析流程
    
    Args:
        url: 要分析的URL
        args: 命令行参数
        config: 配置信息
        analyzer: DeepSeek分析器实例
    """
    logger.info(f"\n开始分析网站: {url}")
    logger.info("="*80)
    
    # 步骤1: 提取网站特征
    logger.info("\n步骤 1/2: 提取网站特征...")
    try:
        extractor = WebsiteFeatureExtractor(url, timeout=args.timeout, enable_favicon=True)
        features = extractor.extract_all_features()
        print_features_summary(features)
    except Exception as e:
        logger.error(f"提取特征失败: {e}")
        return
    
    analysis_result: Dict = {}   # LLM 提取的特征
    
    # 步骤2: LLM分析
    if analyzer:
        logger.info("\n步骤 2/2: LLM排除通用组件...")
        try:
            analysis_result = analyzer.analyze_features(features)
        except Exception as e:
            logger.error(f"AI分析失败: {e}")
            logger.error("特征提取已完成,但AI分析失败")
            analysis_result = {'success': False, 'error': str(e)}
    else:
        logger.warning("\n跳过AI分析 (--no-analysis)")
        analysis_result = {}
    
    # 如果AI分析失败或跳过，直接返回
    if not analysis_result or not analysis_result.get('success'):
        if args.output:
            # 即使没有AI分析也保存原始特征
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(features, f, ensure_ascii=False, indent=2)
        return

    # 将之前LLM返回的指纹放到fofa里面请求

    # 存储最终结果的字典
    final_results: Dict = {}
    final_results_count: Dict = {}  # 记录当前指纹对应的查询结果数量
    
    # 存储有效指纹结果
    valid_fingerprint_results: List[Dict] = []

    # 处理favicon指纹
    # 指纹的逻辑是：只记录查询结果小于5000的
    if features['favicon_hash']:
        logger.info("=" * 80)   # 分割线
        query_favicon: str = f"icon_hash=\"{features['favicon_hash']}\""
        fofa_query_num = len(FofaSearch(config, query_favicon).fofa_query())
        if fofa_query_num > 5000:
            logger.info(f"favicon查询结果数为{fofa_query_num}>=5000，指纹未命中")
        else:
            logger.warning(f"favicon查询结果条数为: {fofa_query_num},可能指纹命中")
            logger.warning(f"FOFA查询语句为: {query_favicon}")
        logger.info("="*80)


    # 处理body中的指纹，遍历
    fingerprints = get_fingerprints_sum(analysis_result.get('fingerprints', []))
    for i in range(len(fingerprints)):
        logger.info("=" * 80)
        finger: str = fingerprints[i]    # [ "/js/userlogin.js", ...]
        logger.info(f"当前查询指纹为: {finger}")

        query: str = f"body=\"{finger}\""
        fofa_search = FofaSearch(config, query)
        fofa_search_res: list = fofa_search.fofa_query()

        # 针对单个指纹的处理，先判断该指纹检索出的数量
        if fofa_search_res:
            if len(fofa_search_res) >= 5000:
                logger.info(f"查询结果数为{len(fofa_search_res)}>=5000条，指纹未命中")
            else:
                logger.warning(f"查询结果数量为: {len(fofa_search_res)},指纹命中")
                logger.warning(f"FOFA查询语句为: {query}")

                # 取前10条进行判断，只要指纹相似度大于某个值的就认为是相似网站（后面提供手动调整阈值的方式）

                # 首先获得url列表字典，key为指纹，value为url列表
                final_results[finger] = []
                final_results_count[finger] = 0

                for _ in range(min(len(fofa_search_res), 10)):
                    target_url: str = fofa_search_res[_][4]  # 拿到link字段
                    final_results[finger].append(target_url)  # 例如{"/js/safe/LoginSafe.js": ["http://202.114.234.188", ...]}
                    final_results_count[finger] = len(fofa_search_res)
        logger.info("=" * 80)

    # 现在需要就当前指纹进行相似度对比，如果相似度符合，则认为该条指纹有效

    # 将final_results_count进行排序，按命中数量从小到大，同时保持final_results同步排序
    sorted_fingers = sorted(final_results_count.items(), key=lambda x: x[1])
    final_results_count = {k: v for k, v in sorted_fingers}
    final_results = {k: final_results[k] for k in final_results_count.keys() if k in final_results}

    # 打印final_results字典
    logger.info(f"\n指纹查询总结:找到的候选指纹条数为:{len(final_results)}")
    for finger, target_urls in final_results.items():  # 遍历字典用items()函数
        sim_list: list = [] # 相似度列表
        logger.info(f"指纹: {finger} 命中URL数量: {final_results_count[finger]}")
        for target_url in target_urls:
            # 请求final_results中的url，使用feature_extractor和deepseek_analyzer进行特征提取，验证指纹有效性。
            logger.info("\n开始验证指纹有效性...")
            try:
                second_extractor = WebsiteFeatureExtractor(target_url, timeout=10, enable_favicon=False)
                second_features: Dict = second_extractor.extract_all_features()
                second_analysis_result: Dict = analyzer.analyze_features(second_features)

                # 比较两个列表的相似度
                sim: float = UrlListSimilarity.jaccard(analysis_result['fingerprints'], second_analysis_result.get('fingerprints', []))
                if sim > 0.1:    # 这里由于存在无关网站的干扰，所以设置一个最低阈值，低于这个值的相似度不进行记录
                    sim_list.append(sim)

            except Exception as e:
                logger.error(f"提取特征失败: {e}")
                continue
        
        # 将列表中的相似度进行平均
        if len(sim_list):
            avg_sim_list: float = sum(sim_list) / len(sim_list)
            if avg_sim_list >= 0.4:
                logger.warning(f"[*] 指纹: {finger} 有效，平均相似度: {avg_sim_list:.2f}")
                # 记录有效指纹结果
                valid_fingerprint_results.append({
                    'finger': finger,
                    'avg_similar': f"{avg_sim_list:.2f}",
                    'url_count': final_results_count[finger]
                })
            else:
                logger.warning(f"[-] 指纹: {finger} 无效，平均相似度: {avg_sim_list:.2f}")
    
    # 保存结果到JSON文件
    save_results(url, features, analysis_result, valid_fingerprint_results, args.output)


if __name__ == "__main__":
    main()
