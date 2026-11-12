from torch import embedding

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
import shutil
from pathlib import Path
import sqlite3
from datetime import datetime

import easyocr
import cv2
import numpy as np

from sentence_transformers import SentenceTransformer
import json
from datetime import timedelta


from fastapi.responses import PlainTextResponse, HTMLResponse, FileResponse

from openai import OpenAI
import os

from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from dotenv import load_dotenv

from fastapi import Request

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from pix2text import Pix2Text

# 加载 .env 文件中的环境变量
load_dotenv()
# 读取密钥，如果读不到就用一个默认值（防止直接报错）
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-for-dev-only")

app = FastAPI(title="智能错题本 API")
# 加载 Pix2Text 模型（放在 app 初始化后面、接口定义前面）
print("正在加载 Pix2Text 一体化识别模型...")
p2t = Pix2Text.from_config()

# 初始化限流器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# ================= 智能科目判断工具 =================
def detect_subject_by_text(text: str) -> str:
    text_lower = text.lower()
    
    # 关键词字典（你可以随时补充）
    rules = {
        "数学": ["函数", "方程", "导数", "积分", "几何", "sin", "cos", "计算", "解方程"],
        "英语": ["english", "academic", "the", "is", "reading", "grammar", "choose", "单选", "完形"],
        "物理": ["力", "速度", "加速度", "电压", "电流", "牛顿", "引力", "电路"],
        "化学": ["化学", "反应", "元素", "分子", "氧化", "酸", "碱", "方程式"],
        "语文": ["作者", "诗句", "文言文", "阅读", "拼音", "作文", "修辞"],
        "生物": ["细胞", "基因", "遗传", "蛋白", "光合作用", "生态"],
        "历史": ["朝代", "皇帝", "历史", "革命", "战争"],
        "地理": ["经纬", "气候", "地形", "板块", "气压"]
    }
    
    # 遍历字典，如果文字里出现了该科目的关键词，就直接返回该科目
    for subject, keywords in rules.items():
        for keyword in keywords:
            if keyword in text_lower:
                return subject
    return "未分类"
# 1. 初始化 OCR (保持本地路径不变)
reader = easyocr.Reader(
    ['ch_sim', 'en'], 
    gpu=False,
    download_enabled=False,
    model_storage_directory=r"C:\Users\前程似锦\.EasyOCR\model"
)
print("正在加载 AI 相似题推荐模型...")
st_model = SentenceTransformer(r"D:\AI_Models\paraphrase-multilingual-MiniLM-L12-v2")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 2. 初始化数据库 (如果数据库文件不存在，会自动创建)
DB_PATH = "error_book.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            subject TEXT DEFAULT '未分类',
            created_at TEXT NOT NULL,
            review_count INTEGER DEFAULT 0,
            embedding TEXT,
            answer TEXT DEFAULT '',
            doubt TEXT DEFAULT '',
            ai_reply TEXT DEFAULT ''
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    ''')
    # ✨ 新增：安全审计与防爆破日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            attempt_time TEXT NOT NULL,
            status TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
# 启动时执行建表
init_db()

# 3. 安全配置与密码加密工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# 4. 定义数据模型
# ================= 安全认证接口 =================
class UserAuth(BaseModel):
    username: str
    password: str

def check_brute_force(request: Request):
    client_ip = request.client.host
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fifteen_mins_ago = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "SELECT COUNT(*) FROM login_logs WHERE ip_address = ? AND status = 'failed' AND attempt_time > ?", 
        (client_ip, fifteen_mins_ago)
    )
    fail_count = cursor.fetchone()[0]
    conn.close()
    if fail_count >= 3:
        raise HTTPException(
            status_code=429, 
            detail="检测到多次错误尝试，您的 IP 已被暂时封禁 15 分钟！"
        )

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="身份验证失败，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise credentials_exception
    return user[1]
# 1. 注册接口
@app.post("/api/register")
def register(user: UserAuth):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查用户名是否已经存在
    cursor.execute("SELECT id FROM users WHERE username = ?", (user.username,))
    if cursor.fetchone():
        conn.close()
        return {"error": "用户名已存在"}
        
    # 密码加盐哈希加密
    hashed_pwd = get_password_hash(user.password)
    cursor.execute("INSERT INTO users (username, hashed_password) VALUES (?, ?)", (user.username, hashed_pwd))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "注册成功！"}
# 1.先定义生成Token的工具函数（顶格写）
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
# 2. 登录接口
@app.post("/api/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    # 1. 进门先查黑名单
    check_brute_force(request)
    client_ip = request.client.host
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT hashed_password FROM users WHERE username = ?", (form_data.username,))
    user = cursor.fetchone()
    
    # 2. 如果用户不存在，或者密码验证失败
    if not user or not verify_password(form_data.password, user[0]):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO login_logs (ip_address, attempt_time, status) VALUES (?, ?, 'failed')", 
            (client_ip, now_str)
        )
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 3. 验证成功，记录成功日志
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO login_logs (ip_address, attempt_time, status) VALUES (?, ?, 'success')", 
        (client_ip, now_str)
    )
    conn.commit()
    conn.close()
        
    # 4. 验证通过，生成 JWT 令牌
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
# ================= 以下为独立工具函数，必须完全顶格写 =================

class Question(BaseModel):
    text: str
    subject: str

@app.get("/")
def read_root():
    return {"message": "欢迎使用智能错题本！数据库已连接。"}

# 接口：手动添加错题
@app.post("/api/questions")
def add_question(question: Question):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 直接保存文本，不需要处理图片
    cursor.execute(
        "INSERT INTO errors (text, subject, created_at) VALUES (?, ?, ?)", 
        (question.text, question.subject, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    return {"status": "success", "message": "错题已保存", "id": new_id}
# 接口：获取所有错题（可以按科目筛选）
@app.get("/api/errors")
def get_all_errors(current_user: str = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 让结果以字典形式返回
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM errors ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    # 转换为字典列表
    errors = [dict(row) for row in rows]
    return {"total": len(errors), "data": errors}
from datetime import datetime, timedelta

# 接口：获取今日需要复习的错题
@app.get("/api/review/today")
def get_today_reviews():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 艾宾浩斯复习间隔（天）
    intervals = [1, 2, 4, 7, 15, 30]
    
    # 获取所有错题
    cursor.execute("SELECT * FROM errors")
    all_errors = cursor.fetchall()
    conn.close()
    
    today_reviews = []
    today_date = datetime.now().date()

    for row in all_errors:
        err = dict(row)
        created_date = datetime.strptime(err["created_at"], "%Y-%m-%d %H:%M:%S").date()
        review_count = err["review_count"]
        
        # 如果已经复习完所有阶段，跳过
        if review_count >= len(intervals):
            continue
            
        # 计算下一次应该复习的日期
        next_review_date = created_date + timedelta(days=intervals[review_count])
        
        # 如果今天到了复习日期，或者已经逾期了，加入今日计划
        if next_review_date <= today_date:
            # 计算逾期天数
            overdue = (today_date - next_review_date).days
            err["overdue_days"] = overdue
            today_reviews.append(err)

    return {"today_count": len(today_reviews), "data": today_reviews}
    # 3. 验证成功，记录成功日志
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO login_logs (ip_address, attempt_time, status) VALUES (?, ?, 'success')", 
        (client_ip, now_str)
    )
    conn.commit()
    conn.close()
        
    # 4. 验证通过，生成 JWT 令牌
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
# ================= 门卫函数 =================
def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="身份验证失败，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user is None:
        raise credentials_exception
    return user[1]
# 接口：标记复习完成（复习次数+1）
@app.post("/api/review/{error_id}")
def mark_reviewed(error_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 查询该错题是否存在
    cursor.execute("SELECT review_count FROM errors WHERE id = ?", (error_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return {"status": "error", "message": "未找到该错题"}
        
    # 复习次数 + 1
    cursor.execute("UPDATE errors SET review_count = review_count + 1 WHERE id = ?", (error_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"错题 {error_id} 已标记为复习，下次复习时间将自动顺延！"}
# 接口：删除指定的错题
@app.delete("/api/errors/{error_id}")
def delete_error(error_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 先查一下有没有这道题
    cursor.execute("SELECT id FROM errors WHERE id = ?", (error_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "error", "message": "错题不存在"}
    
    # 执行删除
    cursor.execute("DELETE FROM errors WHERE id = ?", (error_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"错题 {error_id} 已成功删除"}
# 新增接口：查找相似题
@app.post("/api/find_similar")
def find_similar(question: Question):
    # 1. 算出新题目的向量
    new_embedding = st_model.encode(question.text).tolist()
    
    # 2. 从数据库取出所有错题的向量
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, subject, embedding FROM errors WHERE embedding IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {"message": "数据库里还没有题目"}
        
    # 3. 用数学公式计算相似度（余弦相似度）
    import numpy as np
    new_vec = np.array(new_embedding)
    best_match = None
    highest_score = -1.0
    
    for row in rows:
        old_vec = np.array(json.loads(row[3]))
        # 计算两个向量夹角的余弦值
        score = np.dot(new_vec, old_vec) / (np.linalg.norm(new_vec) * np.linalg.norm(old_vec))
        if score > highest_score:
            highest_score = score
            best_match = {"id": row[0], "text": row[1], "subject": row[2]}
            
    # 如果相似度大于 0.6，就认为它们是相似题
    if highest_score > 0.6:
        return {
            "status": "success",
            "found": True,
            "similarity": round(float(highest_score), 2),
            "similar_question": best_match
        }
    else:
        return {"status": "success", "found": False, "message": "没有找到相似题"}

# ================= 接口：OCR 识别并自动存入数据库 =================
@app.post("/api/ocr_formula")
async def extract_formula_from_image(
    file: UploadFile = File(...),
    subject: str = "数学",
    current_user: str = Depends(get_current_user) # 保留门禁
):
    # 1. 保存图片
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 2. 调用 Pix2Text 识别（返回的是 Markdown 格式，公式用 $ 包裹）
        result_markdown = p2t.recognize_text_formula(str(file_path), return_text=True)
        
        # 3. 计算向量并存入数据库
        embedding = st_model.encode(result_markdown).tolist()
        embedding_str = json.dumps(embedding)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO errors (text, subject, created_at, embedding) VALUES (?, ?, ?, ?)", 
            (result_markdown, subject, now, embedding_str)
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        
        return {"status": "success", "id": new_id, "text": result_markdown}
    except Exception as e:
        return {"status": "error", "message": f"公式识别失败: {str(e)}"}
@app.post("/api/ocr")
async def extract_text_from_image(
    file: UploadFile = File(...),
    subject: str = "未分类" 
):
    # 1. 保存上传的图片
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 2. 读取图片并使用 OCR 识别
    img = cv2.imread(str(file_path))
    if img is None:
        return {"status": "error", "message": "图片读取失败"}
        
    results = reader.readtext(img)
    extracted_text = " ".join([res[1] for res in results])
    avg_confidence = float(np.mean([res[2] for res in results])) if results else 0.0

    # 3. AI 自动判断科目
    if "AI" in subject or "自动" in subject:
        subject = detect_subject_by_text(extracted_text)

    # 4. 存入数据库（包含计算向量）
    embedding = st_model.encode(extracted_text).tolist()
    embedding_str = json.dumps(embedding)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO errors (text, subject, created_at, embedding) VALUES (?, ?, ?, ?)", 
        (extracted_text, subject, now, embedding_str)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {
        "status": "success",
        "id": new_id,
        "text": extracted_text,
        "subject": subject,
        "confidence": round(avg_confidence, 2)
    }

@app.post("/api/ocr_mixed")
async def ocr_mixed_content(
    file: UploadFile = File(...),
    subject: str = "未分类",
    current_user: str = Depends(get_current_user) # 保留你的安全门禁
):
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 调用 P2T 进行一体化识别（文字+公式+表格）
        # return_text=True 会直接返回 Markdown 字符串
        result_markdown = p2t.recognize_text_formula(str(file_path), return_text=True)
        
        # 存入数据库（你的 embedding 字段依然可以存这个 Markdown 的向量）
        embedding = st_model.encode(result_markdown).tolist()
        embedding_str = json.dumps(embedding)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO errors (text, subject, created_at, embedding) VALUES (?, ?, ?, ?)", 
            (result_markdown, subject, now, embedding_str)
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        
        return {"status": "success", "id": new_id, "text": result_markdown}
    except Exception as e:
        return {"status": "error", "message": str(e)}
# ================= 接口：一键导出错题集 =================
@app.get("/api/export", response_class=HTMLResponse)
def export_errors_html():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM errors ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "<h2>暂无错题可以导出！</h2>"

    # 基础 HTML 模板
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>智能错题本导出</title>
        <style>
            body { font-family: "Microsoft YaHei", sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }
            h1 { text-align: center; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            .error-card { background: #f9f9f9; border-left: 5px solid #e74c3c; padding: 15px; margin-bottom: 20px; border-radius: 4px; }
            .error-header { font-weight: bold; color: #e74c3c; margin-bottom: 10px; }
            .error-content { font-size: 16px; }
            .error-meta { font-size: 12px; color: #7f8c8d; margin-top: 10px; text-align: right; }
        </style>
    </head>
    <body>
        <h1>📚 我的智能错题本</h1>
    """
    
    # 循环遍历所有错题
    for idx, row in enumerate(rows, 1):
        err_id = row[0]
        text = row[1]
        sub = row[2]
        created_at = row[3]
        review_count = row[4]
        doubt = row[7] if len(row) > 7 else ""
        ai_reply = row[8] if len(row) > 8 else ""

        # 1. 先输出题目卡片的基础信息
        html_content += f"""
        <div class="error-card">
            <div class="error-header">第 {idx} 题 【{sub}】</div>
            <div class="error-content"><strong>题目：</strong>{text}</div>
        """
        
        # 2. 如果有 AI 答疑，加到题目下面
        if doubt and ai_reply:
            html_content += f"""
            <div style="margin-top: 15px; padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px;">
                <div style="color: #856404; font-weight: bold; margin-bottom: 5px;">❓ 我的疑惑：</div>
                <div style="color: #555;">{doubt}</div>
            </div>
            <div style="margin-top: 10px; padding: 10px; background: #d1ecf1; border-left: 4px solid #17a2b8; border-radius: 4px;">
                <div style="color: #0c5460; font-weight: bold; margin-bottom: 5px;">💡 AI 解答：</div>
                <div style="color: #333; white-space: pre-wrap;">{ai_reply}</div>
            </div>
            """
            
        # 3. 结束当前题目卡片
        html_content += f"""
            <div class="error-meta">录入时间: {created_at} | 已复习: {review_count} 次</div>
        </div>
        """
        
    # 收尾 HTML
    html_content += """
        <div style="text-align: center; margin-top: 40px; color: #bdc3c7; font-size: 12px;">
            由智能错题本生成 - 按 Ctrl+P 可直接打印为 PDF
        </div>
    </body>
    </html>
    """
    return html_content
# 初始化千问客户端（替换成你的 API Key）
qwen_client = OpenAI(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

class DoubtRequest(BaseModel):
    error_id: int
    doubt: str

@app.post("/api/ask_ai")
@limiter.limit("5/minute")  # ✨ 核心：同一个 IP 每分钟最多 5 次
def ask_ai(request: Request, doubt_req: DoubtRequest): 
    # 注意：上面的参数名如果你的叫 request 可能会重名，建议把原来的请求体参数改名叫 doubt_req
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT text FROM errors WHERE id = ?", (doubt_req.error_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "找不到该错题"}
    
    question_text = row[0]
    prompt = f"我有一道错题：{question_text}\n我的疑惑是：{doubt_req.doubt}\n请用高中生能听懂的语言，详细解答我的疑惑。"
    
    try:
        # 调用千问模型（推荐使用 qwen-plus，性价比高[citation:3]）
        completion = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8
        )
        ai_reply = completion.choices[0].message.content
    except Exception as e:
        conn.close()
        return {"error": f"千问调用失败: {str(e)}"}
        
    cursor.execute("UPDATE errors SET doubt = ?, ai_reply = ? WHERE id = ?", (doubt_req.doubt, ai_reply, doubt_req.error_id))
    conn.commit()
    conn.close()
    
    return {"status": "success", "ai_reply": ai_reply} 
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"


@app.post("/api/qwen-plus")
def ask_ai(request: Request, doubt_req: DoubtRequest): 
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT text FROM errors WHERE id = ?", (doubt_req.error_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "找不到该错题"}
    
    question_text = row[0]
    prompt = f"我有一道错题：{question_text}\n我的疑惑是：{doubt_req.doubt}\n请用高中生能听懂的语言，详细解答我的疑惑。"
    
    try:
        # 调用千问模型（推荐使用 qwen-plus，性价比高[citation:3]）
        completion = qwen_client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8
        )
        ai_reply = completion.choices[0].message.content
    except Exception as e:
        conn.close()
        return {"error": f"千问调用失败: {str(e)}"}
        
    cursor.execute("UPDATE errors SET doubt = ?, ai_reply = ? WHERE id = ?", (request.doubt, ai_reply, request.error_id))
    conn.commit()
    conn.close()
    s
    return {"status": "success", "ai_reply": ai_reply}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)