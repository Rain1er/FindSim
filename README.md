# FindSim - 查找相同指纹的网站

专注于指纹识别的轻量级工具。旨在提取网站资源特征，通过LLM排除通用组件，并在FOFA上批量查找。


## 快速开始
1. 开发环境配置
```bash
# 创建并激活虚拟环境
uv venv --python 3.12
# 安装项目中的uv pip
uv pip install pip
# 在当前终端中激活虚拟环境
source .venv/bin/activate
```

2. 运行
```bash
# 填入密钥
mv config_example.json config.json
# go
uv python main.py -u https://example.com
```

3. 进阶  
```bash
cat tmp.txt | httpx -silent | uv run python main.py
```

