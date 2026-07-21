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

# ================= 🎨 注入微调 CSS 样式 =================
st.markdown("""
<style>
    .video-title-box {
        background-color: #f8f9fa;
        border-left: 4px solid #ff007f;
        padding: 8px 12px;
        border-radius: 4px;
        margin-bottom: 12px;
        font-size: 13px;
        color: #111111;
        white-space: normal !important;  
        word-break: break-word !important; 
        line-height: 1.5;
    }
    .time-badge {
        color: #666666;
        font-family: 'Courier New', Courier, monospace;
        font-weight: 500;
        font-size: 14px;
        padding-top: 2px;
    }
    .en-text {
        color: #111111;
        font-weight: 500;
        font-size: 15px;
        margin-bottom: 2px;
        word-break: break-word;
    }
    .zh-text {
        color: #666666;
        font-weight: 400;
        font-size: 13px;
        margin-bottom: 8px;
        word-break: break-word;
    }
    .sub-divider {
        border-bottom: 1px dashed #eef2f6;
        margin-bottom: 10px;
    }
    /* 横向微型数据标签样式 */
    .mini-metrics-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 12px;
        margin-top: 4px;
    }
    .mini-metric-badge {
        background-color: #f1f3f5;
        color: #495057;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 500;
        display: inline-flex;
        align-items: center;
    }
    .mini-metric-badge strong {
        color: #111111;
        margin-left: 3px;
    }
</style>
""", unsafe_allow_html=True)

# ================= 📦 云端/本地高精模型加载 =================
@st.cache_resource
def load_whisper_model():
    with st.spinner("AI 核心模型正在极速初始化中..."):
        return WhisperModel(
            "tiny", 
            device="cpu", 
            compute_type="int8",
            cpu_threads=1,
            num_workers=1
        )

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

# 数字人性化转换函数（例如：1023000 -> 1.02M）
def format_number(num):
    if num is None:
        return "0"
    num = int(num)
    if num >= 1000000:
        return f"{num / 1000000:.2f}M"
    elif num >= 1000:
        return f"{num / 1000:.1f}K"
    return str(num)

# 日期格式化处理函数
def format_date_str(date_str):
    if not date_str:
        return "未知时间"
    try:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    except:
        return date_str

# ⚡ 带缓存的高效批翻译函数
def translate_text_list(text_list, deepl_code, google_code, raw_lang):
    if deepl_code.split('-')[0] == raw_lang.lower():
        return [""] * len(text_list)
        
    try:
        translator = DeeplTranslator(source='auto', target=deepl_code, use_free_api=True)
    except:
        translator = GoogleTranslator(source='auto', target=google_code)

    translated_list = []
    for txt in text_list:
        if not txt:
            translated_list.append("")
            continue
        try:
            translated_list.append(translator.translate(txt))
        except:
            translated_list.append("[翻译超时]")
    return translated_list

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
        
        raw_title = info_dict.get('description') or info_dict.get('title') or 'video_title'
        raw_title = raw_title.replace('\n', ' ').strip()
        
        upload_date = info_dict.get('upload_date') or datetime.datetime.now().strftime("%Y%m%d")
        
        st.session_state.video_metrics = {
            "upload_date": format_date_str(upload_date),
            "view_count": format_number(info_dict.get("view_count")),
            "like_count": format_number(info_dict.get("like_count")),
            "comment_count": format_number(info_dict.get("comment_count")),
            "collect_count": format_number(info_dict.get("collect_count") or 0), 
            "repost_count": format_number(info_dict.get("repost_count") or 0)     
        }
            
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

# ================= 👥 账号权限 =================
USER_WHITE_LIST = {"george": "666888", "laowang": "888888", "xiaozhang": "abc123"}

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.current_user = ""

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

# ================= 🚀 状态与翻译缓存池初始化 =================
if "processed" not in st.session_state:
    st.session_state.processed = False
    st.session_state.video_path = ""
    st.session_state.audio_path = ""
    st.session_state.raw_results = []
    st.session_state.detected_lang = "en"
    st.session_state.mode = "🌐 链接解析"
    st.session_state.display_name = ""
    st.session_state.video_title = "" 
    st.session_state.video_metrics = {"upload_date": "-", "view_count": "-", "like_count": "-", "comment_count": "-", "collect_count": "-", "repost_count": "-"}
    st.session_state.translation_cache = {} 
    st.session_state.title_cache = {}

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
                    st.session_state.translation_cache = {} 
                    st.session_state.title_cache = {}
                    
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
                    st.session_state.video_metrics = {"upload_date": "本地文件", "view_count": "本地", "like_count": "本地", "comment_count": "本地", "collect_count": "本地", "repost_count": "本地"}
                    
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
                    st.session_state.translation_cache = {}
                    st.session_state.title_cache = {}
                    
                    st.session_state.processed = True
                    status_box.empty()
                    st.rerun()
                except Exception as e: status_box.error(f"💥 出错！原因: {str(e)}")
            else: st.warning("⚠️ 请先选择本地文件！")

# --- 界面 2：结果工作台 ---
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
        st.session_state.translation_cache = {}
        st.session_state.title_cache = {}
        st.session_state.video_metrics = {"upload_date": "-", "view_count": "-", "like_count": "-", "comment_count": "-", "collect_count": "-", "repost_count": "-"}
        st.rerun()

    st.markdown("---")
    
    col1, col2 = st.columns([1, 2]) 
    
    lang_config = {
        "简体中文": {"deepl": "zh", "google": "chinese (simplified)"},
        "English (United States)": {"deepl": "en", "google": "english"},
        "Español (Spanish)": {"deepl": "es", "google": "spanish"}, 
        "日本語": {"deepl": "ja", "google": "japanese"},
        "Tiếng Việt": {"deepl": "zh", "google": "chinese (simplified)"}, 
        "Português (Brasil)": {"deepl": "pt", "google": "portuguese"}
    }
    
    final_full_title = st.session_state.video_title

    with col2:
        header_col, select_col, toggle_col, copy_col = st.columns([2.5, 1.5, 1.2, 1.2])
        with header_col: 
            st.markdown("#### 📄 交互式字幕工作区") 
        with select_col:
            target_lang_name = st.selectbox("选择目标语言", list(lang_config.keys()), label_visibility="collapsed")
            deepl_code = lang_config[target_lang_name]["deepl"]
            google_code = lang_config[target_lang_name]["google"]
        with toggle_col: 
            is_bilingual = st.toggle("双语对照", value=True)

        # 🌟 极速读取与智能缓存逻辑
        cache_key = f"{target_lang_name}"
        
        if cache_key not in st.session_state.translation_cache:
            raw_texts = [item["raw_text"] for item in st.session_state.raw_results]
            with st.spinner(f"正在首次翻译为 {target_lang_name}..."):
                trans_results = translate_text_list(raw_texts, deepl_code, google_code, st.session_state.detected_lang)
                st.session_state.translation_cache[cache_key] = trans_results
                
                if final_full_title:
                    t_title = translate_text_list([final_full_title], deepl_code, google_code, st.session_state.detected_lang)[0]
                    st.session_state.title_cache[cache_key] = t_title

        cached_trans = st.session_state.translation_cache[cache_key]
        translated_video_title = st.session_state.title_cache.get(cache_key, "")

        rendered_subtitles = []
        full_text_to_copy = ""
        for idx, item in enumerate(st.session_state.raw_results):
            t_text = cached_trans[idx]
            rendered_subnotes = {
                "raw": item["raw_text"], 
                "trans": t_text, 
                "start": item["start"], 
                "end": item["end"]
            }
            rendered_subtitles.append(rendered_subnotes)
            
            if is_bilingual:
                full_text_to_copy += f"{item['raw_text']}\n{t_text}\n" if t_text else f"{item['raw_text']}\n"
            else:
                full_text_to_copy += f"{item['raw_text']}\n" if not t_text else f"{t_text}\n"

        with copy_col:
            with st.popover("📋 复制文案", use_container_width=True):
                st.caption("✨ 点击代码块右上角即可一键秒拷：")
                st.code(full_text_to_copy, language="text")

    with col1:
        st.subheader("📦 工具与下载")
        
        # 微型数据标签展示
        m = st.session_state.video_metrics
        st.markdown(f"""
        <div style="font-size: 14px; font-weight: bold; color: #333333; margin-bottom: 8px;">📅 发布时间：{m['upload_date']}</div>
        <div class="mini-metrics-container">
            <span class="mini-metric-badge">👀 播放 <strong>{m['view_count']}</strong></span>
            <span class="mini-metric-badge">❤️ 点赞 <strong>{m['like_count']}</strong></span>
            <span class="mini-metric-badge">💬 评论 <strong>{m['comment_count']}</strong></span>
            <span class="mini-metric-badge">⭐ 收藏 <strong>{m['collect_count']}</strong></span>
            <span class="mini-metric-badge">🔁 转发 <strong>{m['repost_count']}</strong></span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        if final_full_title:
            st.markdown(f"""
            <div class="video-title-box">
                <b>🎬 原标题:</b> {final_full_title}<br>
                {f'<b>🌍 译文:</b> {translated_video_title}' if translated_video_title and target_lang_name != "English (United States)" else ''}
            </div>
            """, unsafe_allow_html=True)

        # 🚀 原生高效视频播放器
        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            st.video(st.session_state.video_path)
            st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("**💾 资产一键导出**")

        current_srt_output = ""
        for idx, sub in enumerate(rendered_subtitles, start=1):
            srt_start = f"00:{sub['start']},000"
            srt_end = f"00:{sub['end']},000"
            if is_bilingual: srt_text = f"{sub['raw']}\n{sub['trans']}" if sub['trans'] else sub['raw']
            else: srt_text = sub['raw'] if not sub['trans'] else sub['trans']
            current_srt_output += f"{idx}\n{srt_start} --> {srt_end}\n{srt_text}\n\n"

        if st.session_state.video_path and os.path.exists(st.session_state.video_path):
            with open(st.session_state.video_path, "rb") as vf:
                st.download_button(label="📥 下载视频 (.mp4)", data=vf, file_name=st.session_state.display_name if st.session_state.display_name.endswith(".mp4") else st.session_state.display_name + ".mp4", mime="video/mp4", use_container_width=True)
        
        if os.path.exists(st.session_state.audio_path):
            with open(st.session_state.audio_path, "rb") as af:
                st.download_button(label="🎵 下载音频 (.mp3)", data=af, file_name=st.session_state.display_name.split(".")[0] + ".mp3", mime="audio/mp3", use_container_width=True)
                
        st.download_button(label="📄 下载字幕 (.srt)", data=current_srt_output, file_name=st.session_state.display_name.split(".")[0] + f"_{target_lang_name}.srt", mime="text/plain", use_container_width=True)

    # 右侧滚动字幕展示区
    with col2:
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
