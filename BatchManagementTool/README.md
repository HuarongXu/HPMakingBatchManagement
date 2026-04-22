# HP Making Batch Management Tool

生产计划批次管理工具 —— 自动化排批、搭批、拆批。

## 快速开始（适用于没有 GitHub 账号的用户）

### 方法一：使用下载脚本（推荐）

1. 安装 [Python 3.8+](https://www.python.org/downloads/)（安装时勾选 **Add Python to PATH**）
2. 将收到的 `download_tool.py` 保存到电脑上
3. 打开命令提示符，运行：

```bash
python download_tool.py ghp_你收到的token
```

4. 下载完成后：
```bash
cd HPMakingBatchManagement\BatchManagementTool
install_and_run.bat
```

### 方法二：手动下载 ZIP

如果你有收到的 token，在浏览器中访问：
```
https://github.com/HuarongXu/HPMakingBatchManagement/archive/refs/heads/main.zip
```
（如果仓库是私有的，需要使用下载脚本方式）

---

## 目录结构

- `/data`: 存放原始数据文件（.csv, .xls）。**请将您的数据文件放在这里。**
- `/src`: 存放核心源代码。
  - `main.py`: 主程序入口。
  - `data_loader.py`: 数据加载和预处理模块。
  - `models.py`: 定义核心数据模型（类）。
  - `logic.py`: 核心业务逻辑和算法模块。
- `/output`: 存放程序生成的最终报告。
- `requirements.txt`: 项目所需的Python库。

## 手动运行

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

## 一键运行

Windows 用户可以双击 `install_and_run.bat`，自动安装依赖并运行程序。
