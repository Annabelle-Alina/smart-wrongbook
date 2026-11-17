import streamlit as st
import requests
import urllib.parse

# 后端 API 地址
API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="智能错题本", page_icon="📚", layout="wide")
st.title("📚 智能错题本")

# ================= 登录状态初始化 =================
if "token" not in st.session_state:
    st.session_state["token"] = None

# 如果没登录，显示登录/注册框并拦截
if st.session_state["token"] is None:
    st.subheader("🔐 欢迎使用智能错题本")
    
    # 👇 用 Tabs 分栏：登录 / 注册
    tab1, tab2 = st.tabs(["登录", "注册新账号"])
    
    with tab1:
        st.markdown("### 登录")
        login_user = st.text_input("用户名", key="login_user")
        login_pwd = st.text_input("密码", type="password", key="login_pwd")
        
        if st.button("登录", type="primary", use_container_width=True):
            # OAuth2 登录接口接收的是表单数据（data），不是 json
            login_res = requests.post(f"{API_URL}/api/login", data={"username": login_user, "password": login_pwd})
            
            if login_res.status_code == 200:
                st.session_state["token"] = login_res.json()["access_token"]
                st.success("登录成功！")
                st.rerun()
            elif login_res.status_code == 429:
                st.error("⚠️ 错误次数过多，您的 IP 已被暂时封禁 15 分钟！")
            else:
                st.error("用户名或密码错误！")
                
    with tab2:
        st.markdown("### 注册")
        reg_user = st.text_input("设置用户名", key="reg_user")
        reg_pwd = st.text_input("设置密码", type="password", key="reg_pwd")
        reg_pwd2 = st.text_input("确认密码", type="password", key="reg_pwd2")
        
        if st.button("立即注册", type="primary", use_container_width=True):
            if not reg_user or not reg_pwd:
                st.warning("用户名和密码不能为空！")
            elif reg_pwd != reg_pwd2:
                st.warning("两次输入的密码不一致！")
            else:
                # 调用后端的注册接口
                reg_res = requests.post(f"{API_URL}/api/register", json={"username": reg_user, "password": reg_pwd})
                if reg_res.status_code == 200:
                    st.success("注册成功！请切换到左侧“登录”标签进行登录。")
                else:
                    st.error(f"注册失败: {reg_res.text}")
                    
    st.stop() # 没登录或没注册成功，代码执行到这里停下，不展示下面的功能
# ================= 如果登录成功，准备全局请求头 =================
# 以后你所有发往后端的请求，都要带上这个 headers
headers = {"Authorization": f"Bearer {st.session_state['token']}"}

# 侧边栏加个退出按钮
with st.sidebar:
    if st.button("退出登录"):
        st.session_state["token"] = None
        st.rerun()
# ================= 顶部数据统计卡片 =================
try:
    # 请求所有错题数据
    res_all = requests.get(f"{API_URL}/api/errors",headers=headers).json()
    all_errors = res_all.get("data", [])
    total_count = res_all.get("total", 0)
    
    # 请求今日复习数据
    res_today = requests.get(f"{API_URL}/api/review/today",headers=headers).json()
    today_count = res_today.get("today_count", 0)
    
    # 统计最薄弱的科目（出错最多的）
    from collections import Counter
    subjects = [e["subject"] for e in all_errors]
    if subjects:
        top_subject = Counter(subjects).most_common(1)[0][0]
    else:
        top_subject = "暂无数据"
        
    # 渲染成三列卡片
    m1, m2, m3 = st.columns(3)
    m1.metric(label="📚 总错题数", value=f"{total_count} 道")
    m2.metric(label="📅 今日待复习", value=f"{today_count} 道", delta="加油复习" if today_count>0 else "全对")
    m3.metric(label="🔥 最薄弱科目", value=top_subject)
    
    st.divider() # 画一条分割线，把卡片和下面的内容隔开
except Exception as e:
    st.error("无法加载统计数据，请确保后端服务正常。")
# ================= 侧边栏：上传区 =================
with st.sidebar:
    st.header("📸 录入新错题")
    uploaded_file = st.file_uploader("上传错题图片", type=["jpg", "png", "jpeg"])
    subject = st.selectbox("选择科目", ["🤖 AI 自动识别", "数学", "英语", "物理", "化学", "语文", "生物", "历史", "地理", "政治"])
    
    # 1. 选择识别模式
    ocr_mode = st.radio("识别模式：", ["普通文字识别", "公式/混合内容识别"])
    
    # 2. 点击按钮
    if st.button("开始识别并保存", type="primary"):
        if uploaded_file is not None:
            with st.spinner("AI 正在识别中，请稍候..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"subject": subject}
                
                try:
                    # 1. 根据用户选择，决定请求哪个接口
                    if ocr_mode == "公式/混合内容识别":
                        response = requests.post(f"{API_URL}/api/ocr_mixed", files=files, data=data, headers=headers)
                    else:
                        response = requests.post(f"{API_URL}/api/ocr", files=files, data=data, headers=headers)
                            
                    # 2. 处理接口返回结果
                    if response.status_code == 200:
                        st.success("识别并保存成功！")
                            
                        # ✨ 新增：识别成功后，立刻调用 AI 相似题接口
                        new_text = response.json().get("text", "")
                        payload = {"text": new_text, "subject": subject}
                        sim_res = requests.post(f"{API_URL}/api/find_similar", json=payload, headers=headers)
                            
                        # 保存相似题结果到状态栏，以便页面上方展示
                        if sim_res.status_code == 200:
                            sim_data = sim_res.json()
                            if sim_data.get("found"):
                                st.session_state['similar_warning'] = sim_data
                            else:
                                st.session_state['similar_warning'] = None
                                    
                        st.rerun() # 刷新页面，显示最新的错题列表
                    else:
                        st.error(f"识别失败，后端返回错误: {response.text}")
                            
                except Exception as e:
                    st.error(f"连接服务器失败: {e}")
        else:
            st.warning("请先上传一张图片哦！")
                
# ================= 主页面上方：展示相似题警告 =================
if 'similar_warning' in st.session_state and st.session_state['similar_warning']:
    sim = st.session_state['similar_warning']
    st.warning(f"⚠️ **注意！你以前做过类似的题！** (相似度: {sim['similarity']*100:.1f}%)")
    st.info(f"**历史错题内容：** {sim['similar_question']['text']}")
    
    if st.button("我知道了，关闭提示"):
        st.session_state['similar_warning'] = None
        st.rerun()

# ================= 主页面：分成两列 =================
col1, col2 = st.columns(2)

# 左侧列：今日复习计划
with col1:
    st.header("📅 今日待复习")
    try:
        res_today = requests.get(f"{API_URL}/api/review/today",headers=headers)
        if res_today.status_code == 200:
            today_data = res_today.json().get("data", [])
            if not today_data:
                st.success("🎉 太棒了！今天没有需要复习的错题，去放松一下吧！")
            else:
                st.warning(f"⚠️ 今天有 {len(today_data)} 道错题需要复习！")
                for err in today_data:
                    with st.expander(f"【{err['subject']}】{err['text'][:20]}...", expanded=True):
                        st.write(f"**原题内容：** {err['text']}")
                        st.write(f"**逾期天数：** {err['overdue_days']} 天")
                        
                        # 点击复习完成按钮
                        if st.button("✅ 标记已复习", key=f"review_today_{err['id']}"):
                            res_mark = requests.post(f"{API_URL}/api/review/{err['id']}",headers=headers)
                            if res_mark.status_code == 200:
                                st.toast("打卡成功！已顺延到下次复习。")
                                st.rerun() # 打卡后立刻刷新页面
    except Exception as e:
        st.error("无法连接到后端服务，请确保 main.py 正在运行。")

# 右侧列：所有历史错题
with col2:
    st.header("📖 全部错题本")
    
    # ================= 1. 展示错题列表 =================
    try:
        res_all = requests.get(f"{API_URL}/api/errors", headers=headers)
        if res_all.status_code == 200:
            all_data = res_all.json().get("data", [])
            if not all_data:
                st.info("还没有错题，快去左侧上传吧！")
            else:
                for err in all_data:
                    with st.expander(f"【{err['subject']}】{err['text'][:20]}..."):
                        st.write(f"**完整内容：** {err['text']}")
                        st.write(f"**录入时间：** {err['created_at']}")
                        st.write(f"**已复习次数：** {err['review_count']} 次")
                        
                        # 表单提问区
                        with st.form(key=f"doubt_form_{err['id']}"):
                            user_doubt = st.text_input("复习时有什么疑惑？向 AI 提问：", key=f"doubt_input_{err['id']}")
                            submit_doubt = st.form_submit_button("发送给 AI", key=f"submit_ai_{err['id']}")
                            
                            if submit_doubt and user_doubt:
                                with st.spinner("AI 正在解答你的疑惑..."):
                                    try:
                                        res = requests.post(
                                            f"{API_URL}/api/ask_ai", 
                                            json={"error_id": err['id'], "doubt": user_doubt}, 
                                            headers=headers,
                                            timeout=60
                                        )
                                        if res.status_code == 200:
                                            reply_data = res.json()
                                            if "error" in reply_data:
                                                st.error(f"❌ {reply_data['error']}")
                                            elif "ai_reply" in reply_data:
                                                st.session_state[f"ai_reply_{err['id']}"] = reply_data["ai_reply"]
                                                st.rerun()
                                            else:
                                                st.error(f"未知格式：{reply_data}")
                                        elif res.status_code == 429:
                                            st.error("⚠️ 提问太快了，被限流拦截了！请等 1 分钟后再试。")
                                        else:
                                            st.error(f"后端报错 ({res.status_code}): {res.text}")
                                    except Exception as e:
                                        st.error(f"网络连接彻底失败: {str(e)}")

                        # 展示 AI 回答和摘录框
                        if f"ai_reply_{err['id']}" in st.session_state:
                            st.success("💡 AI 解答：")
                            full_reply = st.session_state[f"ai_reply_{err['id']}"]
                            st.markdown(full_reply)
                            
                            st.markdown("---")
                            
                            # 选择模式
                            print_mode = st.radio(
                                "打印时，这道题的解答部分怎么处理？",
                                ["打印完整 AI 解答", "只打印我写的摘录"],
                                key=f"mode_{err['id']}"
                            )
                            
                            if print_mode == "只打印我写的摘录":
                                user_excerpt = st.text_area(
                                    "摘录打印内容（点击下方按钮保存）：", 
                                    value=st.session_state.get(f"excerpt_saved_{err['id']}", ""),
                                    key=f"excerpt_text_{err['id']}",
                                    height=100
                                )
                                # 加一个显式的保存按钮，保存后提醒用户
                                if st.button("💾 保存摘录", key=f"save_ex_{err['id']}"):
                                    st.session_state[f"excerpt_saved_{err['id']}"] = user_excerpt
                                    st.toast("✅ 摘录已保存！请滑到页面底部生成打印版。")
                                    st.rerun()
                                    
                                if st.session_state.get(f"excerpt_saved_{err['id']}"):
                                    st.success(f"当前已保存的摘录：{st.session_state[f'excerpt_saved_{err['id']}']}")
                            else:
                                st.session_state[f"excerpt_saved_{err['id']}"] = ""
                                st.info("ℹ️ 已选择：将打印完整 AI 解答。")
                                st.success("💡 解答部分将只打印摘录")
                                with st.expander("查看完整 AI 解答"):
                                    st.markdown(full_reply)
                            
                            st.markdown("---")
                        # 删除按钮
                        if st.button("🗑️ 删除这道错题", key=f"delete_{err['id']}"):
                            res_del = requests.delete(f"{API_URL}/api/errors/{err['id']}", headers=headers)
                            if res_del.status_code == 200:
                                st.toast("已成功删除！")
                                st.rerun()
    except Exception as e:
        st.error("无法连接到后端服务，请确保 main.py 正在运行。")
        all_data = [] # 兜底防止下面报错

    # ================= 2. 导出功能 =================
    st.markdown("---")

    if 'all_data' in locals() and all_data:
        excerpts_list = []
        # 检查是否有没保存的情况
        has_missing_save = False
        
        for err in all_data:
            mode = st.session_state.get(f"mode_{err['id']}", "打印完整 AI 解答")
            saved_excerpt = st.session_state.get(f"excerpt_saved_{err['id']}", "")
            
            if mode == "只打印我写的摘录":
                if not saved_excerpt:
                    has_missing_save = True # 选了摘录模式，但没保存内容
                else:
                    excerpts_list.append(f"{err['id']}:{saved_excerpt}")

        if has_missing_save:
            st.error("⚠️ 你选择了【只打印摘录】，但还没有点击保存。请先在上面点击【💾 保存摘录】按钮！")
        else:
            excerpts_str = "||".join(excerpts_list)
            import urllib.parse
            safe_excerpts = urllib.parse.quote(excerpts_str)
            export_url = f"{API_URL}/api/export?excerpts={safe_excerpts}"
            
            st.link_button("📥 点击此处在新标签页查看打印版", export_url, use_container_width=True, type="primary")