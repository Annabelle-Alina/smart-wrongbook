from ocr_processor import OCRProcessor
from data_manager import DataManager

def main():
    # 示例：处理一张图片并保存错题
    ocr = OCRProcessor()
    data = DataManager('..\\data\\wrong_questions.csv')

    image_path = '..\\data\\samples\\sample1.jpg'
    question_text = ocr.process_image(image_path)
    data.add_wrong_question(question_text)

if __name__ == "__main__":
    main()