from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app.chat_view import render_chat_tab  # noqa: E402
from src.app.intake_view import render_intake_tab  # noqa: E402
from src.app.jobs_view import render_jobs_tab, render_tracking_tab  # noqa: E402
from src.app.resume_view import render_resume_tab  # noqa: E402
from src.app.trace_panel import render_section_trace  # noqa: E402

st.set_page_config(page_title="应届生求职助手", page_icon="🎯", layout="wide")

CSS = """
<style>
.block-container { padding-top: 4.4rem; }
.hero { font-size: 1.55rem; font-weight: 750; color: #0f172a; margin-bottom: 2px; }
.sub { color: #64748b; margin-bottom: 16px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.sidebar.markdown("## 🎯 求职助手")
city = st.sidebar.text_input("目标城市", value="上海")
families = st.sidebar.multiselect(
    "目标方向",
    ["数据分析", "产品经理", "产品运营", "运营", "算法", "其他"],
    default=["数据分析", "产品运营"],
)
st.sidebar.markdown("---")

FRIEND_CSS = """
<style>
.friend-title { font-size: 12px; font-weight: 650; color: #64748b; margin: 4px 0 6px; }
.friend-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.friend-link {
  display: block; padding: 7px 9px; border-radius: 8px;
  background: #f8fafc; border: 1px solid #e2e8f0;
  color: #334155 !important; font-size: 11.5px; text-decoration: none !important;
  transition: all 0.15s ease;
}
.friend-link:hover { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8 !important; }
</style>
"""
FRIEND_LINKS = """
<div class="friend-title">友情链接</div>
<div class="friend-grid">
  <a class="friend-link" href="https://www.zhipin.com/" target="_blank" rel="noopener noreferrer">BOSS直聘 ↗</a>
  <a class="friend-link" href="https://www.shixiseng.com/" target="_blank" rel="noopener noreferrer">实习僧 ↗</a>
  <a class="friend-link" href="https://www.nowcoder.com/" target="_blank" rel="noopener noreferrer">牛客 ↗</a>
  <a class="friend-link" href="https://www.51job.com/" target="_blank" rel="noopener noreferrer">前程无忧 ↗</a>
  <a class="friend-link" href="https://www.zhaopin.com/" target="_blank" rel="noopener noreferrer">智联招聘 ↗</a>
  <a class="friend-link" href="https://www.yingjiesheng.com/" target="_blank" rel="noopener noreferrer">应届生求职网 ↗</a>
</div>
"""
st.sidebar.markdown(FRIEND_CSS + FRIEND_LINKS, unsafe_allow_html=True)
st.sidebar.markdown("---")

BUBBLE_CSS = """
<style>
.bubble-cloud {
  display: flex; flex-wrap: wrap; align-items: flex-start;
  gap: 7px 6px; padding: 4px 0 0;
}
.bubble {
  display: inline-block;
  padding: 8px 13px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  border: 1px solid rgba(15, 23, 42, 0.06);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
  animation: floaty 5.2s ease-in-out infinite;
  will-change: transform;
}
.bubble:nth-child(1) { margin-top: 0; }
.bubble:nth-child(2) { margin-top: 12px; }
.bubble:nth-child(3) { margin-top: 3px; }
.bubble:nth-child(4) { margin-top: 14px; }
.bubble:nth-child(5) { margin-top: 6px; }
.bubble:nth-child(6) { margin-top: 1px; }
.bubble:nth-child(7) { margin-top: 12px; }
.bubble:nth-child(8) { margin-top: 5px; }
.bubble:nth-child(2n) { animation-duration: 6.2s; animation-delay: -1.4s; }
.bubble:nth-child(3n) { animation-duration: 7.0s; animation-delay: -2.2s; }
.bubble:nth-child(4n) { animation-duration: 5.8s; animation-delay: -0.8s; }
@keyframes floaty {
  0%, 100% { transform: translateY(0px) rotate(-0.4deg); }
  50% { transform: translateY(-7px) rotate(0.6deg); }
}
</style>
"""
BUBBLES = """
<div class="bubble-cloud">
  <span class="bubble" style="background:linear-gradient(135deg,#e0f2fe,#bae6fd)">简历生成</span>
  <span class="bubble" style="background:linear-gradient(135deg,#dcfce7,#bbf7d0)">方向推荐</span>
  <span class="bubble" style="background:linear-gradient(135deg,#fef3c7,#fde68a)">岗位匹配</span>
  <span class="bubble" style="background:linear-gradient(135deg,#fae8ff,#f5d0fe)">模板库</span>
  <span class="bubble" style="background:linear-gradient(135deg,#e2e8f0,#cbd5e1)">投递记录</span>
  <span class="bubble" style="background:linear-gradient(135deg,#ccfbf1,#99f6e4)">多段经历</span>
  <span class="bubble" style="background:linear-gradient(135deg,#ffe4e6,#fecdd3)">奖学金</span>
  <span class="bubble" style="background:linear-gradient(135deg,#f1f5f9,#e2e8f0)">面试跟进</span>
</div>
"""
st.sidebar.markdown(BUBBLE_CSS + BUBBLES, unsafe_allow_html=True)

# 侧栏不出现滚动条，链接在上、气泡在最下
st.sidebar.markdown("""
<style>
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.8rem; }
[data-testid="stSidebar"] > div:first-child { padding-top: 0.8rem; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero">应届生简历与投递助手</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub">你的信息 → 简历内容 → 岗位推荐 → 投递记录</div>',
    unsafe_allow_html=True,
)

# 分享/截图用：?preview=jobs 直接看三档岗位
if st.query_params.get("preview") == "jobs":
    st.markdown("### 三档岗位（预览）")
    render_jobs_tab(city, families)
    st.stop()

tab_chat, tab_intake, tab_jobs, tab_resume, tab_track = st.tabs(
    ["💬 对话采集", "📝 表单填写", "🎯 三档岗位", "📄 简历模板", "📮 投递追踪"]
)

with tab_chat:
    main, side = st.columns([0.74, 0.26], gap="medium")
    with main:
        render_chat_tab()
    with side:
        render_section_trace("chat")

with tab_intake:
    main, side = st.columns([0.74, 0.26], gap="medium")
    with main:
        render_intake_tab()
    with side:
        render_section_trace("intake")

with tab_jobs:
    main, side = st.columns([0.74, 0.26], gap="medium")
    with main:
        render_jobs_tab(city, families)
    with side:
        render_section_trace("jobs")

with tab_resume:
    main, side = st.columns([0.74, 0.26], gap="medium")
    with main:
        render_resume_tab()
    with side:
        render_section_trace("resume")

with tab_track:
    main, side = st.columns([0.74, 0.26], gap="medium")
    with main:
        render_tracking_tab()
    with side:
        render_section_trace("tracking")
