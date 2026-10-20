# [smart-wrongbook] 开发日志
> 港校申请专项开发记录

## 目录
- [环境配置]
- [核心开发]

---

## 环境配置
### 2024-06-13 | 安装Miniconda
|选择Miniconda的原因|
1.比Anaconda更轻量，满足开发需求
2.只包含conda和Python基础环境
3.与VScode集成效果好
|问题|
1.Miniconda下载速度慢
|解决|
1.使用清华大学开源镜像站下载
### 2024-06-14 | 安装Git
|问题|
1.Git下载速度慢
2.Git方便项目运行的选项设置
|解决|
1.使用清华大学开源镜像站下载
2.安装路径：默认（ C :\ Program Files \ Git ）
  组件：全部默认，确保勾选"Git Bash Here"和"Git GUI Here"
  默认编译器:使用 Visual Studio Code
  调整PATH环境:选择" Git from the command line and also from 3rd- party software "（这样可以在任何命令行中使用 git ）
  选择 HTTPS 传输后端：使用 OpenSSL 库
  配置行结束符：选择" Checkout Windows - style ,commit Unix - style line endings "
  配置终端模拟器：选择" Use MinTTY "
  其他选项：默认

### 2024-06-15 | VS Code专业配置
**工具链选择依据**：
| 工具 | 选择 | 原因 |
|------|------|------|
| 主题 | Dark+ | 最佳语法高亮支持 |
| 字体 | Fira Code | 连字提升可读性 |
| AI辅助 | Copilot | 教育许可激活 |

**配置代码**：
```json
// settings.json核心配置
"editor.fontFamily": "'Fira Code'",
"files.autoSave": "afterDelay"
```

**效率提升**：
```mermaid
pie
    title 时间节省分析
    “手动配置” ： 40
    “自动保存” ： 30
    “AI辅助” ： 30
```
## 核心部分开发
## 2024-06-14

**今日目标：**
1.  完成smart-wrongbook的项目架构
2.  完成scr的核心部分
3.  第一次提交代码至GitHub

**工作进展：**
*   创建了scr,docs,data,reqequirements基本项目架构
*   完成scr的main,data_manager,ocr_processor
 * main部分
 * data_manager部分
 * ocr_processor部分
**遇到的问题：**
1.  **问题：** 
    *   **排查：**
        *   
        *   
    *   **解决方案：** 
    *   **学习点：** 
**下一步计划：**
1.  
2.  
3. 