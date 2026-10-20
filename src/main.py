from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
import shutil
from pathlib import Path

# 引入刚装好的 OCR 和 图像处理库
import easyocr
import cv2
import numpy as np

app = FastAPI(title="智能错题本 API")

# 初始化 OCR 引擎（首次运行会自动下载识别模型，黑窗口里会显示进度）
reader = easyocr.Reader(['ch_sim', 'en'], gpu=False,download_enabled=False,
    model_storage_directory=r"C:\Users\前程似锦\.EasyOCR\model")

# 确保保存图片的文件夹存在
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.get("/")
def read_root():
    return {"message": "欢迎使用智能错题本！服务已启动。"}

class Question(BaseModel):
    text: str
    subject: str

@app.post("/api/questions")
def add_question(question: Question):
    return {
        "status": "success",
        "received_text": question.text,
        "subject": question.subject
    }

# 【全新接口】上传图片并提取文字
@app.post("/api/ocr")
async def extract_text_from_image(file: UploadFile = File(...)):
    # 1. 保存上传的图片
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 2. 使用 OpenCV 读取图片
    img = cv2.imread(str(file_path))
    if img is None:
        return {"status": "error", "message": "图片读取失败"}
        
    # 3. 使用 EasyOCR 识别文字
    results = reader.readtext(img)
    
    # 4. 提取文字并拼接
    extracted_text = " ".join([res[1] for res in results])
    
    # 5. 计算平均置信度
    avg_confidence = float(np.mean([res[2] for res in results])) if results else 0.0

    return {
        "status": "success",
        "filename": file.filename,
        "text": extracted_text,
        "confidence": round(avg_confidence, 2),
        "blocks_detected": len(results)
    }
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)