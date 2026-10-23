from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
import shutil
from pathlib import Path
import sqlite3
from datetime import datetime

import easyocr
import cv2
import numpy as np

app = FastAPI(title="智能错题本 API")

# 1. 初始化 OCR (保持本地路径不变)
reader = easyocr.Reader(
    ['ch_sim', 'en'], 
    gpu=False,
    download_enabled=False,
    model_storage_directory=r"C:\Users\前程似锦\.EasyOCR\model"
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 2. 初始化数据库 (如果数据库文件不存在，会自动创建)
DB_PATH = "error_book.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 创建错题表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            subject TEXT DEFAULT '未分类',
            created_at TEXT NOT NULL,
            review_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# 启动时执行建表
init_db()

# 3. 定义数据模型
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
    cursor.execute(
        "INSERT INTO errors (text, subject, created_at) VALUES (?, ?, ?)", 
        (question.text, question.subject, now)
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return {"status": "success", "message": "错题已保存", "id": new_id}

# 接口：OCR 识别并自动存入数据库
@app.post("/api/ocr")
async def extract_text_from_image(
    file: UploadFile = File(...),
    subject: str = "未分类"  # 新增一个科目参数，前端可以传
):
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    img = cv2.imread(str(file_path))
    if img is None:
        return {"status": "error", "message": "图片读取失败"}
        
    results = reader.readtext(img)
    extracted_text = " ".join([res[1] for res in results])
    avg_confidence = float(np.mean([res[2] for res in results])) if results else 0.0

    # 存入数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO errors (text, subject, created_at) VALUES (?, ?, ?)", 
        (extracted_text, subject, now)
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

# 接口：获取所有错题（可以按科目筛选）
@app.get("/api/errors")
def get_all_errors():
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
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)