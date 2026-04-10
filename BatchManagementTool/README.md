# 生产计划管理工具

这是一个根据需求文档开发的生产计划管理工具。

## 目录结构

- `/data`: 存放原始数据文件（.csv, .xls）。**请将您的数据文件放在这里。**
- `/src`: 存放核心源代码。
  - `main.py`: 主程序入口。
  - `data_loader.py`: 数据加载和预处理模块。
  - `models.py`: 定义核心数据模型（类）。
  - `logic.py`: 核心业务逻辑和算法模块。
- `/output`: 存放程序生成的最终报告。
- `requirements.txt`: 项目所需的Python库。

## 如何运行

1.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **准备数据**:
    将 `ZCPRS`, `ZC228`, `Parameter`, `Making Capacity` 等数据文件放入 `/data` 文件夹。

3.  **运行程序**:
    ```bash
    python src/main.py
    ```

4.  **查看结果**:
    程序运行成功后，将在 `/output` 文件夹中生成结果报告Excel文件。
