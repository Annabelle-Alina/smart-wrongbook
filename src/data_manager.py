import csv
import os

class DataManager:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        # 如果文件不存在，创建并写入表头
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['question'])

    def add_wrong_question(self, question: str):
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([question])
        print(f"已添加错题: {question}")