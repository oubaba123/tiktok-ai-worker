import streamlit as st
import os
import datetime
import re
import glob
import urllib.request
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from deep_translator import DeeplTranslator, GoogleTranslator  

# 设置宽屏模式
st.set_page_config(page_title="TikTok AI 视频字幕工作台", page_icon="🎬", layout="wide")

# ================= 🎨 还原并注入第二张图的高保真 CSS 样式 =================
st.markdown("""
<style>
    /* 左侧视频上方小看板：完全还原第二张图的外观与不截断无省略号换行 */
    .video-title-box {
        background-color: #f8f9fa;
        border-left: 4px solid #ff007f;
        padding: 6px 10px;
        border-radius: 4px;
        margin-bottom: 12px;
        font-size: 13px;
        color: #111111;
        white-space: normal !important;  /* 允许自然换行 */
        word-break: break-all !important; /* 遇到长文本强制折行，拒绝三个点 */
    }
    
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

# 全盘自动大扫除函数
def auto_cleanup_old_files(current_video_path=""):
    all_temp_files = glob.glob("temp_*.mp4") + glob.glob("temp_*.mp3")
    current_audio_path = current_video_path.replace(".mp4", ".mp3") if current_video_path else ""
    for file in all_temp_files:
        if file != current_video_path and file != current_audio_path:
            try: os.remove(file)
            except: pass

# 纯 Python 极速音频分离函数
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

# 防断流多线程自适应链接下载函数
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
        raw_title = info_dict.get('title', 'video_title')
        upload_date = info_dict.get('upload_date') or datetime.datetime.now().strftime("%Y%m%d")
            
    # 文件名与系统存储保持最初完美的纯英文/纯数字规范命名
    custom_name = safe_filename(f"temp_{upload_date}_{author}_{video_id}_{raw_title[:15]}")
    
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
        
    return actual_filename, raw_title

def format_short_time(seconds):
    td = datetime.timedelta(seconds=seconds)
    parts = str(td).split(".")[0].split(":")
    return f"{parts[1]}:{parts[2]}"

def transcribe_any_audio(file_path, status_text):
    model = load_whisper_model()
    status_text.text("AI 正在高精提取语音数据...")
    segments, info = model.transcribe(file_path, beam_size=5, language=None)
    
    detected_lang = info.language
    
    results = []
    for i, segment in enumerate(segments, start=1):
        results.append({
            "index": i,
            "start": format_short_time(segment.start),
            "end": format_short_time(segment.end),
            "raw_text": segment.text.strip()
        })
    return results, detected_lang

# ================= 👥 独立账号权限白名单管理 =================
USER_WHITE_LIST = {
    "george": "666888",
    "laowang": "888888",
    "xiaozhang": "abc123"
}

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.current_user = ""

# 拦截门禁
if not st.session_state.authenticated:
    _, login_col, _ = st.columns([1, 1.5, 1])
    with login_col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.subheader("🔒 视频智能字幕工作台 · 内部登录")
        st.caption("仅供内部人员使用，支持换电脑访问。")
        st.markdown("---")
        input_user = st.text_input("👤 用户名账号：", placeholder="请输入您的账号")
        input_pwd = st.text_input("🔑 登录密码：", type="password", placeholder="请输入您的密码")
        if st.button("安全登录 ➔", type="primary", use_container_width=True):
            if input_user in USER_WHITE_LIST and input_pwd == USER_WHITE_LIST[input_user]:
                st.session_state.authenticated = True
                st.session_state.current_user = input_user
                st.rerun()
            else:
                st.error("❌ 账号或密码不正确！")
    st.stop()

# ================= 状态保持初始化 =================
if "processed" not in st.session_state:
    st.session_state.processed = False
    st.session_state.video_path = ""
    st.session_state.audio_path = ""
    st.session_state.raw_results = []
    st.session_state.detected_lang = "en"
    st.session_state.mode = "🌐 链接解析"
    st.session_state.display_name = ""
    st.session_state.video_title = "" 

# 侧边栏登出
st.sidebar.markdown(f"**👤 当前登录：{st.session_state.current_user}**")
if st.sidebar.button("🚪 退出当前登录"):
    st.session_state.authenticated = False
    st.session_state.current_user = ""
    st.session_state.processed = False
    st.rerun()

st.sidebar.header("🔧 系统状态")
if os.path.exists("cookies.txt"): st.sidebar.success("✅ cookies.txt 已就绪")
else: st.sidebar.error("❌ 未检测到 cookies.txt")

# --- 界面 1：输入与上传页 ---
if not st.session_state.processed:
    auto_cleanup_old_files()
    st.session_state.mode = st.radio("🔮 请选择识别模式：", ["🌐 链接解析", "📤 本地上传"], horizontal=True)
    st.markdown("---")
    
    if st.session_state.mode == "🌐 链接解析":
        url_input = st.text_input("请输入 TikTok 视频链接：", placeholder="https://www.tiktok.com/@xxx/video/xxx")
        if st.button("🚀 开始分析网络视频", type="primary"):
            if url_input:
                status_box = st.info("初始化网络任务中...")
                try:
                    auto_cleanup_old_files()
                    v_path, r_title = download_tk_video(url_input, status_box)
                    st.session_state.video_path = v_path
                    st.session_state.audio_path = v_path.replace(".mp4", ".mp3")
                    st.session_state.display_name = os.path.basename(v_path)
                    st.session_state.video_title = r_title 
                    
                    res, lang = transcribe_any_audio(st.session_state.video_path, status_box)
                    st.session_state.raw_results = res
                    st.session_state.detected_lang = lang
                    
                    st.session_state.processed = True
                    status_box.empty()
                    st.rerun() 
                except Exception as e: status_box.error(f"💥 运行出错！原因: {str(e)}")
            else: st.warning("⚠️ 链接不能为空")
                
    else:
        uploaded_file = st.file_uploader("请选择本地视频/音频文件：", type=["mp4", "mp3", "m4a", "wav"])
        if st.button("🚀 开始智能提取本地文件", type="primary"):
            if uploaded_file:
                status_box = st.info("正在将文件载入内存...")
                try:
                    auto_cleanup_old_files()
                    file_ext = uploaded_file.name.split(".")[-1]
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    clean_name = safe_filename(uploaded_file.name.split(".")[0])
                    saved_path = f"temp_local_{timestamp}_{clean_name}.{file_ext}"
                    with open(saved_path, "wb") as f: f.write(uploaded_file.getbuffer())
                        
                    st.session_state.display_name = uploaded_file.name
                    st.session_state.video_title = uploaded_file.name 
                    
                    if file_ext.lower() == "mp4":
                        st.session_state.video_path = saved_path
                        st.session_state.audio_path = saved_path.replace(".mp4", ".mp3")
                        extract_audio_pure_python(saved_path, st.session_state.audio_path)
                    else:
                        st.session_state.video_path = "" 
                        st.session_state.audio_path = saved_path
                        
                    res, lang = transcribe_any_audio(saved_path, status_box)
                    st.session_state.raw_results = res
                    st.session_state.detected_lang = lang
                    
                    st.session_state.processed = True
                    status_box.empty()
                    st.rerun()
                except Exception as e: status_box.error(f"💥 出错！原因: {str(e)}")
            else: st.warning("⚠️ 请先选择本地文件！")

# --- 界面 2：结果工作台（完全按照第二张图的完美外观和比例布局） ---
else:
    if st.button("⬅️ 返回主页（处理新任务）"):
        st.session_state.processed = False
        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            try: os.remove(st.session_state.video_path)
            except: pass
        if st.session_state.audio_path and os.path.exists(st.session_state.audio_path):
            try: os.remove(st.session_state.audio_path)
            except: pass
        st.session_state.video_path = ""
        st.session_state.audio_path = ""
        st.session_state.raw_results = []
        st.session_state.video_title = ""
        st.rerun()

    st.markdown("---")
    
    # 🌟 完美对齐第二张图的视觉排版：左边 0.8 放视频盒，右边 2.5 放交互面板
    col1, col2 = st.columns([0.8, 2.5]) 
    
    with col2:
        lang_config = {
            "简体中文": {"deepl": "zh", "google": "chinese (simplified)"},
            "English (United States)": {"deepl": "en", "google": "english"},
            "Español (Spanish)": {"deepl": "es", "google": "spanish"}, 
            "日本語": {"deepl": "ja", "google": "japanese"},
            "Tiếng Việt": {"deepl": "zh", "google": "chinese (simplified)"}, 
            "Português (Brasil)": {"deepl": "pt", "google": "portuguese"}
        }
        
        # 🌟【智能修补三个点机制】：如果 yt_dlp 抓回来的标题带有省略号，我们直接用 AI 高清语音转写出来的第一句文案作为真正的完整全量长标题！
        final_full_title = st.session_state.video_title
        if "..." in final_full_title and st.session_state.raw_results:
            # 智能拼接 AI 识别出的全量纯净第一句，彻底干掉省略号
            final_full_title = st.session_state.raw_results[0]["raw_text"] + " " + st.session_state.raw_results[1]["raw_text"]
        
        # 还原第二张图：右侧头部一行，完美渲染大标题
        header_col, select_col, toggle_col, copy_col = st.columns([2.5, 1.5, 1.2, 1.2])
        with header_col: 
            st.markdown(f"#### 📄 交互式字幕工作区 - {final_full_title}")
        with select_col:
            target_lang_name = st.selectbox("选择目标语言", list(lang_config.keys()), label_visibility="collapsed")
            deepl_code = lang_config[target_lang_name]["deepl"]
            google_code = lang_config[target_lang_name]["google"]
        with toggle_col: 
            is_bilingual = st.toggle("双语对照", value=True)
            
        full_text_to_copy = ""
        
        use_google_fallback = False
        try:
            translator = DeeplTranslator(source='auto', target=deepl_code, use_free_api=True)
        except:
            translator = GoogleTranslator(source='auto', target=google_code)
            use_google_fallback = True

        translated_video_title = ""
        if final_full_title:
            try:
                translated_video_title = translator.translate(final_full_title)
            except:
                try:
                    emergency_title_trans = GoogleTranslator(source='auto', target=google_code)
                    translated_video_title = emergency_title_trans.translate(final_full_title)
                except:
                    translated_video_title = "[标题翻译超时]"

        # 还原第二张图顶部的地球仪小译文行
        if translated_video_title and target_lang_name != "English (United States)":
            st.markdown(f"🌍 译文标题: {translated_video_title}")

        rendered_subtitles = []
        for item in st.session_state.raw_results:
            current_raw_lang = st.session_state.detected_lang.lower()
            
            if deepl_code.split('-')[0] == current_raw_lang:
                t_text = ""
            else:
                if item["raw_text"]:
                    try:
                        t_text = translator.translate(item["raw_text"])
                    except:
                        try:
                            emergency_trans = GoogleTranslator(source='auto', target=google_code)
                            t_text = emergency_trans.translate(item["raw_text"])
                        except:
                            t_text = "[翻译超时，请稍后重试]"
                else:
                    t_text = ""
                
            rendered_subtitles.append({"raw": item["raw_text"], "trans": t_text, "start": item["start"], "end": item["end"]})
            
            if is_bilingual:
                full_text_to_copy += f"{item['raw_text']}\n{t_text}\n" if t_text else f"{item['raw_text']}\n"
            else:
                full_text_to_copy += f"{item['raw_text']}\n" if not t_text else f"{t_text}\n"

    with col1:
        st.subheader("📦 工具与下载")
        
        # 还原第二张图：左侧视频正上方的小字粉红边框看板，完美无缝展示完整长标题
        if final_full_title:
            st.markdown(f"""
            <div class="video-title-box">
                <b>🎬 原标题:</b> {final_full_title}<br>
                {f'<b>🌍 译文:</b> {translated_video_title}' if translated_video_title and target_lang_name != "English (United States)" else ''}
            </div>
            """, unsafe_allow_html=True)
            
        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            v_side1, v_mid, v_side2 = st.columns([0.05, 0.9, 0.05])
            with v_mid: st.video(st.session_state.video_path)
            st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**💾 资产一键导出**")

    with col2:
        with copy_col:
            with st.popover("📋 复制文案", use_container_width=True):
                st.caption("✨ 点击代码块右上角即可一键秒拷：")
                st.code(full_text_to_copy, language="text")

        current_srt_output = ""
        for idx, sub in enumerate(rendered_subtitles, start=1):
            srt_start = f"00:{sub['start']},000"
            srt_end = f"00:{sub['end']},000"
            if is_bilingual: srt_text = f"{sub['raw']}\n{sub['trans']}" if sub['trans'] else sub['raw']
            else: srt_text = sub['raw'] if not sub['trans'] else sub['trans']
            current_srt_output += f"{idx}\n{srt_start} --> {srt_end}\n{srt_text}\n\n"

        with col1:
            if st.session_state.video_path and os.path.exists(st.session_state.video_path):
                with open(st.session_state.video_path, "rb") as vf:
                    st.download_button(label="📥 下载视频 (.mp4)", data=vf, file_name=st.session_state.display_name if st.session_state.display_name.endswith(".mp4") else st.session_state.display_name + ".mp4", mime="video/mp4", use_container_width=True)
            
            if os.path.exists(st.session_state.audio_path):
                with open(st.session_state.audio_path, "rb") as af:
                    st.download_button(label="🎵 下载音频 (.mp3)", data=af, file_name=st.session_state.display_name.split(".")[0] + ".mp3", mime="audio/mp3", use_container_width=True)
                    
            st.download_button(label="📄 下载字幕 (.srt)", data=current_srt_output, file_name=st.session_state.display_name.split(".")[0] + f"_{target_lang_name}.srt", mime="text/plain", use_container_width=True)

        st.markdown("---")
        
        with st.container(height=520):
            for sub in rendered_subtitles:
                sub_col_time, sub_col_text = st.columns([1, 4])
                with sub_col_time: st.markdown(f'<div class="time-badge">{sub["start"]}-{sub["end"]}</div>', unsafe_allow_html=True)
                with sub_col_text:
                    if is_bilingual:
                        st.markdown(f'<div class="en-text">{sub["raw"]}</div>', unsafe_allow_html=True)
                        if sub["trans"]: st.markdown(f'<div class="zh-text">{sub["trans"]}</div>', unsafe_allow_html=True)
                    else:
                        if not sub["trans"]: st.markdown(f'<div class="en-text">{sub["raw"]}</div>', unsafe_allow_html=True)
                        else: st.markdown(f'<div class="en-text">{sub["trans"]}</div>', unsafe_allow_html=True)
                    st.markdown('<div class="sub-divider"></div>', unsafe_allow_html=True)