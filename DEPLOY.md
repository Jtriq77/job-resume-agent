# 部署：Streamlit Cloud + Netlify

> 本项目是 Python/Streamlit 应用，不能直接作为静态站点放在 Netlify 上运行。采用“Netlify 入口页 + Streamlit 云端应用”。

## 1. 上传 GitHub

把本仓库（`github_repo/` 的内容）作为 GitHub 仓库根目录上传。仓库已经排除了 `.env`、个人画像、导出文件、1G 原始库和 291M 全量模板。

## 2. 部署 Streamlit

1. 打开 https://share.streamlit.io/ ，用 GitHub 登录；
2. New app → 选择仓库；
3. Main file path：

   ```text
   src/app/streamlit_app.py
   ```

4. Python 版本选 3.11 或 3.12；
5. Advanced settings → Secrets：

   ```toml
   DEEPSEEK_API_KEY = "sk-..."
   DEEPSEEK_BASE_URL = "https://api.deepseek.com"
   DEEPSEEK_MODEL = "deepseek-chat"
   ```

6. Deploy，得到 `https://xxxx.streamlit.app`。

> 免费版闲置后会休眠，首次访问可能需要 20–60 秒唤醒；文件系统是临时的，画像/投递记录在重启后可能丢失。

## 3. 部署 Netlify 入口页

1. 打开 `netlify/index.html`，把 `__APP_URL__` 替换成上一步的 Streamlit 地址；
2. 打开 https://app.netlify.com/drop ；
3. 把 `netlify/` 文件夹拖进去；
4. 得到 `https://xxxx.netlify.app`，提交这个网址即可。

## 4. 部署后检查

- 首页能否打开；
- 对话采集能否整理四段；
- 选方向能否生成 DOCX；
- 模板库下载是否正常；
- 三档岗位链接是否可点；
- 投递记录能否新增。

## 5. 注意

不要把 `.env`、`data/profile.json`、`data/output/`、`data/applications.csv` 提交到 GitHub；这些已在 `.gitignore` 中忽略。
