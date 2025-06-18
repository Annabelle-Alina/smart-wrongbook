class OCRProcessor:
    def __init__(self):
        # 初始化OCR模型（如有需要）
        pass

    def process_image(self, image_path: str) -> str:
        # 这里应集成OCR库（如pytesseract），这里只做示例
        print(f"正在处理图片: {image_path}")
        # 假设返回识别到的题目文本
        return "示例错题内容"