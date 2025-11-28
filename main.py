"""
FindSim - 网站指纹识别工具
提取网站特征并使用DeepSeek AI分析识别指纹
"""

import os
import sys
import argparse
from feature_extractor import WebsiteFeatureExtractor
from deepseek_analyzer import DeepSeekAnalyzer
import warnings
import json
import base64
import requests
import logging
from typing import Dict

from url_list_similarity import UrlListSimilarity

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # 关键：stdout
)
logger = logging.getLogger(__name__)

def load_config():
    """加载配置文件"""
    config_file = 'config.json'
    
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        logger.error("❌ 错误: 读取配置文件失败，请检查config.json")
        sys.exit(1)
        


def save_results(url: str, features: dict, analysis: dict, output_file: str = None):
    """保存分析结果到文件"""
    result = {
        'url': url,
        'favicon_hash': analysis.get('favicon_hash', features.get('favicon_hash', '')),
        'fingerprints': analysis.get('fingerprints', []),
        'raw_features': features
    }
    
    if not output_file:
        # 生成默认文件名
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace('.', '_')
        output_file = f"fingerprint_{domain}.json"
    
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
    logger.info(f"Favicon Hash (mmh3): {features['favicon_hash']}")
    logger.info(f"src数量为: {len(resources.get('all_srcs', []))} 个")
    logger.info(f"href数量为: {len(resources.get('all_hrefs', []))} 个")
    
    logger.info("="*80)


def main():
    """主函数"""
    global analyzer, config
    parser = argparse.ArgumentParser(
        description='FindSim - FOFA指纹提取工具\n提取网站资源，通过DeepSeek AI排除通用组件，输出可用于FOFA检索的指纹',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python main.py -u https://example.com
  python main.py -u https://example.com -o fingerprint.json
  python main.py -u https://example.com --no-analysis
        """
    )
    
    parser.add_argument('-u', '--url', required=True, help='要分析的网站URL')
    parser.add_argument('-o', '--output', help='输出文件路径 (可选)')
    parser.add_argument('--no-analysis', action='store_true', help='只提取特征,不进行AI分析')
    parser.add_argument('-t', '--timeout', type=int, default=10, help='请求超时时间(秒), 默认10秒')
    
    args = parser.parse_args()
    
    # 验证URL
    if not args.url.startswith(('http://', 'https://')):
        logger.error("ERROR: URL必须以 http:// 或 https:// 开头")
        sys.exit(1)
    
    logger.info(f"\n开始分析网站: {args.url}")
    logger.info("="*80)
    
    # 步骤1: 提取网站特征
    logger.info("\n步骤 1/2: 提取网站特征...")
    try:
        extractor = WebsiteFeatureExtractor(args.url, timeout=args.timeout)
        features = extractor.extract_all_features()
        print_features_summary(features)
    except Exception as e:
        logger.error(f"❌ 提取特征失败: {e}")
        sys.exit(1)
    
    analysis_result: Dict   # LLM 提取的特征
    
    # 步骤2: DeepSeek AI分析
    if not args.no_analysis:
        logger.info("\n步骤 2/2: DeepSeek AI排除通用组件...")
        try:
            config = load_config()
            analyzer = DeepSeekAnalyzer(config['deepseek_api_key'])
            analysis_result = analyzer.analyze_features(features)
            # analyzer.print_analysis(analysis_result)
        except Exception as e:
            logger.error(f"❌ AI分析失败: {e}")
            logger.error("特征提取已完成,但AI分析失败")
            analysis_result = {'success': False, 'error': str(e)}
    else:
        logger.warning("\n跳过AI分析 (--no-analysis)")
        analysis_result = {}
    
    # 保存结果
    if analysis_result and analysis_result.get('success'):
        save_results(args.url, features, analysis_result, args.output)
    elif args.output:
        # 即使没有AI分析也保存原始特征
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(features, f, ensure_ascii=False, indent=2)
    #     logger.info(f"\n原始特征已保存到: {args.output}")
    #
    # logger.info("\n分析完成!")

    # 将之前LLM返回的指纹放到fofa里面请求

    # 存储最终结果的字典
    final_results: Dict = {}
    final_results_count: Dict = {}  # 记录当前指纹对应的查询结果数量

    # 如果处理图标
    # if features['favicon_hash']:
    #     logger.info("=" * 80)   # 分割线
    #     fofa_api: str = config["fofa_api"]
    #     fofa_api_key: str = config["fofa_api_key"]
    #     query: str = f"icon_hash=\"{features['favicon_hash']}\""
    #     query_base64: str = base64.b64encode(query.encode()).decode()
    #
    #     api_url: str = f"{fofa_api}?key={fofa_api_key}&size=10000&qbase64={query_base64}"
    #     try:
    #         resp = requests.get(api_url, timeout=60)
    #         resp.raise_for_status()
    #         # remaining_queries = resp.json().get("remaining_queries", [])
    #         # if remaining_queries <= 0:
    #         #     logger.error("API查询次数已用完，退出程序")
    #         #     sys.exit(0)
    #
    #         if resp.json().get("results"):
    #             data: list = resp.json().get("results", [])
    #             if len(data) > 10000:
    #                 logger.info(f"查询结果数为{len(data)}>=10000条，指纹未命中")
    #             else:
    #                 logger.warning(f"当前指纹查询结果条数为: {len(data)},可能指纹命中")
    #                 logger.warning(f"FOFA查询语句为：{query}")
    #
    #                 # 取前10条进行判断，只要指纹相似度大于80%的就认为是相似网站（后面提供手动调整阈值的方式）
    #                 for _ in range(min(len(data), 10)):
    #                     # 处理特殊情况，data[_][0]可能是完整的url
    #                     if data[_][0].startswith("http") or data[_][0].startswith("https"):
    #                         logger.info(f"{data[_][0]}")
    #                     else:
    #                         logger.info(f"{data[_][5]}://{data[_][0]}")
    #         else:
    #             logger.info(f"没有找到相关数据")
    #     except requests.exceptions.RequestException as e:
    #         logger.error(f"请求 fofa_api 时发生错误: {e}")
    #
    #     logger.info("="*80)


    # 处理body中的指纹，遍历
    for i in range(len(analysis_result['fingerprints'])):
        logger.info("=" * 80)
        finger: str = analysis_result['fingerprints'][i]    # [ "/js/userlogin.js", ...]
        logger.info(f"当前查询指纹为：{finger}")

        # TODO 后面将这一部分进行封装到fofa_search类
        fofa_api: str = config["fofa_api"]
        fofa_api_key: str = config["fofa_api_key"]

        query: str = f"body=\"{finger}\""
        query_base64: str = base64.b64encode(query.encode()).decode()

        api_url: str = f"{fofa_api}?key={fofa_api_key}&size=10000&qbase64={query_base64}"
        try:
            resp = requests.get(api_url, timeout=60)
            resp.raise_for_status()
            # 针对单个指纹的处理，先判断该指纹检索出的数量
            if resp.json().get("results"):
                data: list = resp.json().get("results", [])
                if len(data) >= 5000:
                    logger.info(f"查询结果数为{len(data)}>=5000条，指纹未命中")
                else:
                    logger.warning(f"查询结果数量为: {len(data)},指纹命中")
                    logger.warning(f"FOFA查询语句为：{query}")

                    # 取前10条进行判断，只要指纹相似度大于80%的就认为是相似网站（后面提供手动调整阈值的方式）

                    # 首先获得url列表字典，key为指纹，value为url列表
                    final_results[finger]: list = []
                    final_results_count[finger]: list = []

                    for _ in range(min(len(data), 10)):
                        if not data[_][0].startswith("0"):   # 处理特殊情况，可能查出IP地址为这个0.0.0.0
                            # 处理特殊情况，data[_][0]可能是完整的url,https也是http开头
                            if data[_][0].startswith("http"):
                                # logger.info(f"{data[_][0]}")
                                url: str = data[_][0]
                            else:
                                # logger.info(f"{data[_][5]}://{data[_][0]}")
                                url: str = f"{data[_][5]}://{data[_][0]}"

                            final_results[finger].append(url)    # 例如{"/js/safe/LoginSafe.js": ["http://202.114.234.188", ...]}
                            final_results_count[finger] = len(data)

            else:
                logger.info(f"没有找到相关数据")
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 fofa_api 时发生错误: {e}")
    logger.info("=" * 80)

    # 现在需要就当前指纹进行相似度对比，如果相似度符合，则认为该条指纹有效

    # 将final_results_count进行排序，按命中数量从小到大，同时保持final_results同步排序
    sorted_fingers = sorted(final_results_count.items(), key=lambda x: x[1])
    final_results_count = {k: v for k, v in sorted_fingers}
    final_results = {k: final_results[k] for k in final_results_count.keys()
                        if k in final_results}

    # 打印final_results字典
    logger.info(f"\n指纹查询总结:找到的候选指纹条数为:{len(final_results)}")
    for finger, urls in final_results.items():  # 遍历字典用items()函数
        jac_list: list = [] # 相似度列表
        logger.info(f"指纹: {finger} 命中URL数量: {final_results_count[finger]}")
        for url in urls:
            # logger.info(f"  - {url}")

            # 请求final_results中的url，使用feature_extractor和deepseek_analyzer进行特征提取，验证指纹有效性。
            logger.info("\n开始验证指纹有效性...")
            try:
                seccond_extractor = WebsiteFeatureExtractor(url, timeout=10)
                seccond_features: Dict = seccond_extractor.extract_all_features()
                seccond_analysis_result: Dict = analyzer.analyze_features(seccond_features)

                # 比较两个列表的相似度
                # logger.info("开始比较指纹相似度...")
                # logger.info(f"原始指纹特征: {analysis_result['fingerprints']}")
                # logger.info(f"对比指纹特征: {seccond_analysis_result['fingerprints']}")

                jac: float = UrlListSimilarity.jaccard(analysis_result['fingerprints'], seccond_analysis_result['fingerprints'])
                if jac > 0: # 避免获取失败的情况
                    jac_list.append(jac)
            except Exception as e:
                logger.error(f"❌ 提取特征失败: {e}")
                sys.exit(1)
            # 将列表中的相似度进行平均
        if len(jac_list):
            avg_jac: float = sum(jac_list) / len(jac_list)
            if avg_jac >= 0.5:
                logger.warning(f"[*] 指纹: {finger} 有效，平均相似度: {avg_jac:.2f}")
                # 写到结果文件中
                with open("valid_fingerprints.txt", "a", encoding="utf-8") as f:
                    f.write(f"指纹: {finger} 平均相似度: {avg_jac:.2f} 命中URL数量: {final_results_count[finger]}\n")
            else:
                logger.warning(f"[-] 指纹: {finger} 无效，平均相似度: {avg_jac:.2f}")
    # 插入分割线
    with open("valid_fingerprints.txt", "a", encoding="utf-8") as f:
            f.write("="*40 + "\n")

if __name__ == "__main__":
    main()
