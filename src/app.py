import streamlit as st
import requests

# 后端 API 地址
API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="智能错题本", page_icon="📚", layout="wide")
st.title("📚 智能错题本")

# ================= 顶部数据统计卡片 =================
try:
    # 请求所有错题数据
    res_all = requests.get(f"{API_URL}/api/errors").json()
    all_errors = res_all.get("data", [])
    total_count = res_all.get("total", 0)
    
    # 请求今日复习数据
    res_today = requests.get(f"{API_URL}/api/review/today").json()
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
    if st.button("开始识别并保存", type="primary"):
        if uploaded_file is not None:
            with st.spinner("AI 正在识别中，请稍候..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"subject": subject}
                try:
                    # 1. 发送图片进行 OCR 识别
                    response = requests.post(f"{API_URL}/api/ocr", files=files, data=data)
                    if response.status_code == 200:
                        st.success("识别并保存成功！")
                        
                        # 2. 识别成功后，立刻调用 AI 相似题接口
                        new_text = response.json().get("text", "")
                        payload = {"text": new_text, "subject": subject}
                        sim_res = requests.post(f"{API_URL}/api/find_similar", json=payload)
                        
                        # 3. 保存相似题结果到状态栏，以便页面上方展示
                        if sim_res.status_code == 200:
                            sim_data = sim_res.json()
                            if sim_data.get("found"):
                                st.session_state['similar_warning'] = sim_data
                            else:
                                st.session_state['similar_warning'] = None
                        
                        st.rerun() # 刷新页面
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
        res_today = requests.get(f"{API_URL}/api/review/today")
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
                            res_mark = requests.post(f"{API_URL}/api/review/{err['id']}")
                            if res_mark.status_code == 200:
                                st.toast("打卡成功！已顺延到下次复习。")
                                st.rerun() # 打卡后立刻刷新页面
    except Exception as e:
        st.error("无法连接到后端服务，请确保 main.py 正在运行。")

# 右侧列：所有历史错题
with col2:
    st.header("📖 全部错题本")
    # ✨ 新增：导出功能
    if st.button("📥 一键生成错题集(打印版)"):
        st.markdown(f'<meta http-equiv="refresh" content="0; url={API_URL}/api/export">', unsafe_allow_html=True)
    try:
        res_all = requests.get(f"{API_URL}/api/errors")
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
                        # 增加删除按钮
                        if st.button("🗑️ 删除这道错题", key=f"delete_{err['id']}"):
                            res_del = requests.delete(f"{API_URL}/api/errors/{err['id']}")
                            if res_del.status_code == 200:
                                st.toast("已成功删除！")
                                st.rerun() # 删完立刻刷新页面
    except Exception as e:
        pass # 左侧已经报错了，这里就不重复报了