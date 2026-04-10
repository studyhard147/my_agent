import streamlit as st
import os
import uuid
from io import StringIO
from PIL import Image
from pypdf import PdfReader
from dotenv import load_dotenv
from graph_system import create_rag_graph, set_model

# 设置页面配置
st.set_page_config(
    page_title="智能问答系统",
    page_icon="🤖",
    layout="wide"
)

# 加载环境变量
load_dotenv()

# --- 登录认证逻辑 ---
def check_password():
    """如果密码正确则返回 True，否则显示输入框并返回 False"""
    
    def password_entered():
        """检查输入的密码是否正确"""
        if (
            st.session_state["username"] == os.getenv("LOGIN_USERNAME", "admin")
            and st.session_state["password"] == os.getenv("LOGIN_PASSWORD", "admin123")
        ):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 验证后删除密码以防泄露
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 还没输入过密码，显示登录界面
        st.title("🔐 欢迎访问智能问答系统")
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input("用户名", key="username")
            st.text_input("密码", type="password", key="password", on_change=password_entered)
            st.button("登录", on_click=password_entered)
            if "password_correct" in st.session_state and not st.session_state["password_correct"]:
                st.error("😕 用户名或密码错误，请重试。")
        return False
    elif not st.session_state["password_correct"]:
        # 密码错误，重新显示
        st.title("🔐 欢迎访问智能问答系统")
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.text_input("用户名", key="username")
            st.text_input("密码", type="password", key="password", on_change=password_entered)
            st.button("登录", on_click=password_entered)
            st.error("😕 用户名或密码错误，请重试。")
        return False
    else:
        # 密码正确
        return True

# 只有通过密码检查才运行后续逻辑
if check_password():
    # 初始化 Session State
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "history" not in st.session_state:
        st.session_state.history = []
    if "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = None
    if "app" not in st.session_state:
        st.session_state.app = None
    if "uploaded_context" not in st.session_state:
        st.session_state.uploaded_context = None
    if "mode" not in st.session_state:
        st.session_state.mode = "chat" # chat, voice, imagine
    if "is_generating" not in st.session_state:
        st.session_state.is_generating = False
    if "abort_generation" not in st.session_state:
        st.session_state.abort_generation = False
    if "current_request_id" not in st.session_state:
        st.session_state.current_request_id = None

    # 定义解析文件的函数
    def parse_uploaded_file(uploaded_file):
        if uploaded_file.type == "text/plain":
            # 解析文本文件
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            return stringio.read()
        elif uploaded_file.type == "application/pdf":
            # 解析 PDF 文件
            pdf_reader = PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            return text
        return None

    # 定义保存/更新当前对话到历史记录的函数
    def sync_current_to_history():
        if not st.session_state.messages:
            return
        
        first_user_msg = next((m["content"] for m in st.session_state.messages if m["role"] == "user"), "新对话")
        title = first_user_msg[:20] + "..." if len(first_user_msg) > 20 else first_user_msg
        
        if st.session_state.current_chat_id is None:
            new_id = str(uuid.uuid4())
            st.session_state.current_chat_id = new_id
            st.session_state.history.append({
                "id": new_id,
                "title": title,
                "messages": st.session_state.messages.copy(),
                "context": st.session_state.uploaded_context
            })
        else:
            for chat in st.session_state.history:
                if chat["id"] == st.session_state.current_chat_id:
                    chat["messages"] = st.session_state.messages.copy()
                    chat["title"] = title
                    chat["context"] = st.session_state.uploaded_context
                    break

    # 侧边栏配置
    with st.sidebar:
        # 1. 顶部 Logo 和搜索
        col_logo, col_collapse = st.columns([0.8, 0.2])
        with col_logo:
            st.markdown("# 🧭") # 模拟 Logo
        
        search_query = st.text_input("🔍 搜索", placeholder="搜索历史对话...", label_visibility="collapsed")
        
        st.markdown("---")

        # 2. 核心功能按钮
        if st.button("📝 新建聊天", use_container_width=True, type="primary"):
            st.session_state.messages = []
            st.session_state.current_chat_id = None
            st.session_state.uploaded_context = None
            st.session_state.mode = "chat"
            st.rerun()
        
        if st.button("🎙️ 语音对话", use_container_width=True, type="secondary" if st.session_state.mode != "voice" else "primary"):
            st.session_state.mode = "voice"
            st.rerun()
        
        col_imagine, col_dot = st.columns([0.9, 0.1])
        with col_imagine:
            if st.button("🖼️ Imagine 绘图", use_container_width=True, type="secondary" if st.session_state.mode != "imagine" else "primary"):
                st.session_state.mode = "imagine"
                st.rerun()
        with col_dot:
            st.markdown("<span style='color: #5865f2; font-size: 20px;'>●</span>", unsafe_allow_html=True)

        st.markdown("---")

        # 3. 项目 (文件上传)
        with st.expander("📁 项目", expanded=True):
            st.markdown("##### 📂 上传文件 (增强知识库)")
            uploaded_files = st.file_uploader("支持 .txt, .pdf", type=["txt", "pdf"], accept_multiple_files=True, label_visibility="collapsed")
            if uploaded_files:
                combined_text = ""
                for file in uploaded_files:
                    content = parse_uploaded_file(file)
                    if content:
                        combined_text += f"\n--- 来自文件: {file.name} ---\n{content}\n"
                st.session_state.uploaded_context = combined_text
                st.success(f"已加载 {len(uploaded_files)} 个文件")

            st.markdown("##### 🖼️ 上传图片 (仅展示)")
            uploaded_image = st.file_uploader("支持 .png, .jpg, .jpeg", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
            if uploaded_image:
                img = Image.open(uploaded_image)
                st.image(img, caption="已上传预览", use_container_width=True)

        # 4. 历史记录 (对话列表)
        with st.expander("🕒 历史记录", expanded=True):
            if st.session_state.history:
                # 根据搜索过滤历史
                filtered_history = [
                    chat for chat in st.session_state.history 
                    if search_query.lower() in chat["title"].lower()
                ] if search_query else st.session_state.history

                for i, chat in enumerate(reversed(filtered_history)):
                    col_h1, col_h2 = st.columns([0.8, 0.2])
                    with col_h1:
                        if st.button(f"🗨️ {chat['title']}", key=f"load_{chat['id']}", use_container_width=True):
                            st.session_state.messages = chat["messages"].copy()
                            st.session_state.current_chat_id = chat["id"]
                            st.session_state.uploaded_context = chat.get("context")
                            st.rerun()
                    with col_h2:
                        if st.button("🗑️", key=f"del_{chat['id']}", help="删除此对话"):
                            st.session_state.history = [c for c in st.session_state.history if c["id"] != chat["id"]]
                            if st.session_state.current_chat_id == chat["id"]:
                                st.session_state.messages = []
                                st.session_state.current_chat_id = None
                                st.session_state.uploaded_context = None
                            st.rerun()
            else:
                st.caption("暂无历史记录")

        st.markdown("---")
        
        # 5. 模型与系统设置
        with st.expander("⚙️ 系统设置"):
            model_option = st.selectbox(
                "选择 DeepSeek 模型",
                ("deepseek-chat (V3)", "deepseek-reasoner (R1)"),
                index=0
            )
            model_name = "deepseek-reasoner" if "R1" in model_option else "deepseek-chat"
        
        # 6. 登出按钮
        if st.button("🚪 退出登录", use_container_width=True):
            del st.session_state["password_correct"]
            st.rerun()

    # 主界面
    st.title("💬 智能问答系统")
    st.caption(f"当前模式: {st.session_state.mode.upper()} | 基于 LangGraph 和 DeepSeek")

    # 模式特定的 UI
    if st.session_state.mode == "voice":
        st.info("🎙️ 语音模式已激活。点击下方按钮录制语音，系统将为您解答。")
        audio_value = st.audio_input("录制你的问题")
        if audio_value:
            st.audio(audio_value)
            st.warning("提示：DeepSeek 目前主要支持文本输入。语音已录制，请在下方输入框配合文字描述以获得最佳回答。")

    elif st.session_state.mode == "imagine":
        st.info("🖼️ Imagine 绘图模式已激活。输入描述，DeepSeek 将为您提供绘画灵感和详细描述。")

    # 初始化或更新模型
    if st.session_state.app is None or st.session_state.get("last_model") != model_name:
        set_model(model_name)
        st.session_state.app = create_rag_graph()
        st.session_state.last_model = model_name

    # 显示对话历史
    if not st.session_state.messages:
        st.info("👋 你好！我是你的智能助手。你可以问我关于知识库中的内容，也可以上传文件让我学习。")
        if st.button("🚀 开始新对话"):
            st.session_state.messages.append({"role": "assistant", "content": "你好！请问今天有什么我可以帮你的吗？"})
            sync_current_to_history()
            st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if isinstance(message["content"], dict) and "image" in message["content"]:
                st.image(message["content"]["image"])
                if "text" in message["content"]:
                    st.markdown(message["content"]["text"])
            else:
                st.markdown(message["content"])

    # 用户输入
    if prompt := st.chat_input("在当前模式下输入内容..."):
        # 检查是否有图片需要一同发送
        message_content = prompt
        if uploaded_image:
            message_content = {"text": prompt, "image": uploaded_image.getvalue()}

        # 针对 Imagine 模式优化提示词
        final_prompt = prompt
        if st.session_state.mode == "imagine":
            final_prompt = f"作为一个绘画专家，请根据以下描述生成一段详细的 Midjourney/Stable Diffusion 提示词，并描述画面细节: {prompt}"

        # 添加用户消息
        st.session_state.messages.append({"role": "user", "content": message_content})
        with st.chat_message("user"):
            if uploaded_image:
                st.image(uploaded_image)
            st.markdown(prompt)

        # 生成回答
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("🤔 正在思考中...")
            request_id = str(uuid.uuid4())
            st.session_state.current_request_id = request_id
            st.session_state.is_generating = True
            st.session_state.abort_generation = False
            stop_area = st.container()
            with stop_area:
                if st.button("⏹ 停止生成", key=f"stop_{request_id}"):
                    st.session_state.abort_generation = True
                    st.info("已请求停止生成")
                    st.rerun()
            
            try:
                # 构建输入状态
                inputs = {"question": final_prompt}
                # 如果上传了文件，将其作为 context 传入
                if st.session_state.uploaded_context:
                    inputs["context"] = st.session_state.uploaded_context
                
                final_output = ""
                for output in st.session_state.app.stream(inputs):
                    if st.session_state.abort_generation and st.session_state.current_request_id == request_id:
                        message_placeholder.markdown("⏹ 已手动终止生成")
                        break
                    for key, value in output.items():
                        if key == "generate":
                            final_output = value["generation"]
                
                message_placeholder.markdown(final_output)
                st.session_state.messages.append({"role": "assistant", "content": final_output})
                sync_current_to_history()
                
            except Exception as e:
                st.error(f"执行出错: {e}")
                message_placeholder.empty()
            finally:
                if st.session_state.current_request_id == request_id:
                    st.session_state.is_generating = False
