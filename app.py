import streamlit as st
import os
import datetime
import re
import glob
import urllib.request
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator

# 设置宽屏模式
st.set_page_config(page_title="TikTok AI 视频字幕工作台", page_icon="🎬", layout="wide")

# ================= 🎨 注入微调 CSS 样式 =================
st.markdown("""
<style>
    .time-badge {
        color: #666666;
        font-family: 'Courier New', Courier, monospace;
        font-weight: 500;
        font-size: 15px;
        padding-top: 2px;
    }
    .en-text {
        color: #111111;
        font-weight: 500;
        font-size: 16px;
        margin-bottom: 2px;
    }
    .zh-text {
        color: #888888;
        font-weight: 400;
        font-size: 14px;
        margin-bottom: 12px;
    }
    .sub-divider {
        border-bottom: 1px dashed #eef2f6;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ================= 模型缓存 =================
@st.cache_resource
def load_whisper_model():
    return WhisperModel("tiny", device="cpu", compute_type="int8")

# 清理 Windows 文件名非法字符
def safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")

# 全盘自动大扫除函数（只清理打上 temp_ 前缀的临时生成资产）
def auto_cleanup_old_files(current_video_path=""):
    all_temp_files = glob.glob("temp_*.mp4") + glob.glob("temp_*.mp3")
    current_audio_path = current_video_path.replace(".mp4", ".mp3") if current_video_path else ""
    for file in all_temp_files:
        if file != current_video_path and file != current_audio_path:
            try: os.remove(file)
            except: pass

# ================= 纯 Python 极速音频分离函数 =================
def extract_audio_pure_python(video_path, output_audio_path):
    try:
        from moviepy.editor import VideoFileClip
    except ImportError:
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "moviepy==1.0.3"])
        from moviepy.editor import VideoFileClip
        
    try:
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(output_audio_path, logger=None)
        video.close()
        return True
    except Exception as e:
        print(f"音频分离失败: {str(e)}")
        return False

# ================= 防断流多线程自适应链接下载函数 =================
def download_tk_video(video_url, status_text):
    status_text.text("正在智能解析本地网络代理环境...")
    
    system_proxies = urllib.request.getproxies()
    final_proxy = system_proxies.get('https') or system_proxies.get('http')
    
    network_retry_opts = {
        'cookiefile': 'cookies.txt', 'quiet': True, 'retries': 15, 'fragment_retries': 15, 'retry_sleep': 2, 'external_downloader': 'builtin', 'hls_use_mpegts': True,
    }
    if final_proxy:
        network_retry_opts['proxy'] = final_proxy
        
    with YoutubeDL(network_retry_opts) as ydl:
        info_dict = ydl.extract_info(video_url, download=False)
        author = info_dict.get('uploader', 'unknown_user')
        video_id = info_dict.get('id', '000000')
        title = info_dict.get('title', 'video_title')[:20]
        upload_date = info_dict.get('upload_date') or datetime.datetime.now().strftime("%Y%m%d")
            
    # 加 temp_ 前缀，方便后续自动扫描和擦除
    custom_name = safe_filename(f"temp_{upload_date}_{author}_{video_id}_{title}")
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{custom_name}.%(ext)s', 'cookiefile': 'cookies.txt', 
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
        'quiet': True, 'retries': 15, 'fragment_retries': 15, 'retry_sleep': 2, 'concurrent_fragment_downloads': 4 
    }
    if final_proxy:
        ydl_opts['proxy'] = final_proxy
        
    status_text.text("正在采用 4 线程断点续传极速下载视频...")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
        actual_filename = ydl.prepare_filename(info_dict)
        
    status_text.text("正在剥离高音质音频文件...")
    audio_file_path = actual_filename.replace(".mp4", ".mp3")
    extract_audio_pure_python(actual_filename, audio_file_path)
        
    return actual_filename

def format_short_time(seconds):
    td = datetime.timedelta(seconds=seconds)
    parts = str(td).split(".")[0].split(":")
    return f"{parts[1]}:{parts[2]}"

# ================= 🌟 统一识别核心函数 =================
def transcribe_only_en(file_path, status_text):
    model = load_whisper_model()
    status_text.text("AI 正在高精提取语音数据（支持音视频直接透传）...")
    segments, _ = model.transcribe(file_path, beam_size=5)
    
    results = []
    for i, segment in enumerate(segments, start=1):
        results.append({
            "index": i,
            "start": format_short_time(segment.start),
            "end": format_short_time(segment.end),
            "en": segment.text.strip()
        })
    return results

# ================= 状态保持核心初始化 =================
if "processed" not in st.session_state:
    st.session_state.processed = False
    st.session_state.video_path = ""
    st.session_state.audio_path = ""
    st.session_state.en_results = []
    st.session_state.mode = "🌐 链接解析"
    st.session_state.display_name = ""

# ================= 界面渲染 =================
st.title("🎬 TikTok AI 视频字幕工作台")

# 侧边栏状态检测
st.sidebar.header("🔧 系统状态")
if os.path.exists("cookies.txt"):
    st.sidebar.success("✅ cookies.txt 已就绪")
else:
    st.sidebar.error("❌ 未检测到 cookies.txt")

# --- 界面 1：输入与上传初始页 ---
if not st.session_state.processed:
    auto_cleanup_old_files()
    
    # 🌟 核心改动：顶置导航模式单选选项
    st.session_state.mode = st.radio("🔮 请选择识别模式：", ["🌐 链接解析", "📤 本地上传"], horizontal=True)
    st.markdown("---")
    
    # 模式一：链接解析
    if st.session_state.mode == "🌐 链接解析":
        url_input = st.text_input("请输入 TikTok 视频链接：", placeholder="https://www.tiktok.com/@xxx/video/xxx")
        if st.button("🚀 开始分析网络视频", type="primary"):
            if url_input:
                status_box = st.info("初始化网络任务中...")
                try:
                    auto_cleanup_old_files()
                    v_path = download_tk_video(url_input, status_box)
                    st.session_state.video_path = v_path
                    st.session_state.audio_path = v_path.replace(".mp4", ".mp3")
                    st.session_state.display_name = os.path.basename(v_path)
                    st.session_state.en_results = transcribe_only_en(st.session_state.video_path, status_box)
                    st.session_state.processed = True
                    status_box.empty()
                    st.rerun() 
                except Exception as e:
                    status_box.error(f"💥 运行出错！错误原因: {str(e)}")
            else:
                st.warning("⚠️ 链接不能为空")
                
    # 模式二：本地上传
    else:
        uploaded_file = st.file_uploader("请拖拽或选择本地视频/音频文件（支持 mp4, mp3, m4a, wav 等）：", type=["mp4", "mp3", "m4a", "wav"])
        if st.button("🚀 开始智能提取本地文件", type="primary"):
            if uploaded_file:
                status_box = st.info("正在将文件载入内存并启动 AI 核心...")
                try:
                    auto_cleanup_old_files()
                    
                    # 确定文件后缀类型
                    file_ext = uploaded_file.name.split(".")[-1]
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    clean_name = safe_filename(uploaded_file.name.split(".")[0])
                    
                    # 将上传的文件固化到本地临时目录
                    saved_path = f"temp_local_{timestamp}_{clean_name}.{file_ext}"
                    with open(saved_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                        
                    st.session_state.display_name = uploaded_file.name
                    
                    # 判断如果是视频，则同时剥离音频；如果是纯音频，则视频位留空
                    if file_ext.lower() == "mp4":
                        st.session_state.video_path = saved_path
                        st.session_state.audio_path = saved_path.replace(".mp4", ".mp3")
                        extract_audio_pure_python(saved_path, st.session_state.audio_path)
                    else:
                        st.session_state.video_path = "" # 纯音频不渲染视频播放器
                        st.session_state.audio_path = saved_path
                        
                    # 启动 AI 语音转写
                    st.session_state.en_results = transcribe_only_en(saved_path, status_box)
                    st.session_state.processed = True
                    status_box.empty()
                    st.rerun()
                except Exception as e:
                    status_box.error(f"💥 本地解析出错！原因: {str(e)}")
            else:
                st.warning("⚠️ 请先选择一个有效的本地文件！")

# --- 界面 2：结果工作台 ---
else:
    if st.button("⬅️ 返回主页（处理新任务）"):
        st.session_state.processed = False
        # 退出时彻底清空本地刚才的各类临时缓存资产
        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            try: os.remove(st.session_state.video_path)
            except: pass
        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            try: os.remove(st.session_state.audio_path)
            except: pass
        st.session_state.video_path = ""
        st.session_state.audio_path = ""
        st.session_state.en_results = []
        st.rerun()

    st.markdown("---")
    col1, col2 = st.columns([0.8, 2.5]) 
    
    with col1:
        st.subheader("📦 工具与下载")
        
        # 豆腐块微型视频播放器（只在解析网络视频或本地上传 mp4 时展示，纯音频文件自动跳过不占位）
        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            v_side1, v_mid, v_side2 = st.columns([0.1, 0.8, 0.1])
            with v_mid:
                st.video(st.session_state.video_path)
            st.markdown("<br>", unsafe_allow_html=True)
            
        st.markdown("**💾 资产一键导出**")

    with col2:
        lang_options = {
            "简体中文": "zh-CN", "English (United States)": "en", "日本語": "ja", "Tiếng Việt": "vi", "Português (Brasil)": "pt"
        }
        
        header_col, select_col, toggle_col, copy_col = st.columns([2.5, 1.5, 1.2, 1.2])
        with header_col:
            st.subheader("📄 交互式字幕工作区")
        with select_col:
            target_lang_name = st.selectbox("选择目标语言", list(lang_options.keys()), label_visibility="collapsed")
            target_lang_code = lang_options[target_lang_name]
        with toggle_col:
            is_bilingual = st.toggle("双语对照", value=True)
            
        full_text_to_copy = ""
        translator = GoogleTranslator(source='auto', target=target_lang_code)
        
        rendered_subtitles = []
        for item in st.session_state.en_results:
            if target_lang_code != "en":
                try: t_text = translator.translate(item["en"])
                except: t_text = "[翻译失败]"
            else:
                t_text = ""
                
            rendered_subtitles.append({"en": item["en"], "trans": t_text, "start": item["start"], "end": item["end"]})
            
            if is_bilingual:
                if target_lang_code != "en": full_text_to_copy += f"{item['en']}\n{t_text}\n\n"
                else: full_text_to_copy += f"{item['en']}\n\n"
            else:
                if target_lang_code == "en": full_text_to_copy += f"{item['en']}\n\n"
                else: full_text_to_copy += f"{t_text}\n\n"

        with copy_col:
            with st.popover("📋 复制文案", use_container_width=True):
                st.caption("✨ 点击代码块右上角即可一键秒拷：")
                st.code(full_text_to_copy, language="text")

        # 字幕包组装
        current_srt_output = ""
        for idx, sub in enumerate(rendered_subtitles, start=1):
            srt_start = f"00:{sub['start']},000"
            srt_end = f"00:{sub['end']},000"
            if is_bilingual: srt_text = f"{sub['en']}\n{sub['trans']}" if sub['trans'] else sub['en']
            else: srt_text = sub['en'] if target_lang_code == "en" else sub['trans']
            current_srt_output += f"{idx}\n{srt_start} --> {srt_end}\n{srt_text}\n\n"

        # 统一资产导出面板逻辑
        with col1:
            # 1. 导出视频按钮（仅在有视频源时显现）
            if st.session_state.video_path and os.path.exists(st.session_state.video_path):
                with open(st.session_state.video_path, "rb") as vf:
                    st.download_button(
                        label="📥 下载视频 (.mp4)", 
                        data=vf, 
                        file_name=st.session_state.display_name if st.session_state.display_name.endswith(".mp4") else st.session_state.display_name + ".mp4", 
                        mime="video/mp4", 
                        use_container_width=True
                    )
            
            # 2. 导出音频按钮
            if os.path.exists(st.session_state.audio_path):
                with open(st.session_state.audio_path, "rb") as af:
                    st.download_button(
                        label="🎵 下载音频 (.mp3)", 
                        data=af, 
                        file_name=st.session_state.display_name.split(".")[0] + ".mp3", 
                        mime="audio/mp3", 
                        use_container_width=True
                    )
            else:
                st.error("⚠️ 音频资产丢失")
                    
            # 3. 导出字幕按钮
            st.download_button(
                label="📄 下载字幕 (.srt)",
                data=current_srt_output,
                file_name=st.session_state.display_name.split(".")[0] + f"_{target_lang_name}.srt",
                mime="text/plain",
                use_container_width=True
            )

        st.markdown("---")
        
        # 逐行时间轴高保真对照渲染
        with st.container(height=520):
            for sub in rendered_subtitles:
                sub_col_time, sub_col_text = st.columns([1, 4])
                with sub_col_time:
                    st.markdown(f'<div class="time-badge">{sub["start"]}-{sub["end"]}</div>', unsafe_allow_html=True)
                    
                with sub_col_text:
                    if is_bilingual:
                        st.markdown(f'<div class="en-text">{sub["en"]}</div>', unsafe_allow_html=True)
                        if sub["trans"]: st.markdown(f'<div class="zh-text">{sub["trans"]}</div>', unsafe_allow_html=True)
                    else:
                        if target_lang_code == "en": st.markdown(f'<div class="en-text">{sub["en"]}</div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="en-text">{sub["trans"]}</div>', unsafe_allow_html=True)
                            
                    st.markdown('<div class="sub-divider"></div>', unsafe_allow_html=True)