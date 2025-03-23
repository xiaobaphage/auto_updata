# Auto Updata

一个简单的自动更新模块，支持 Windows 系统下的软件自动更新功能。

## 特性

- 自动检查更新
- 后台下载更新
- 退出时自动安装
- 支持开发和生产环境
- 配置文件管理
- 日志记录
- 进度显示

## 安装

```bash
pip install auto_updata
```

## 使用示例

```python
from auto_updata import Updater

def main():
    # 初始化更新器（会在后台检查更新）
    updater = Updater.initialize()
    
    # 运行你的主程序
    run_your_program()
    
    # 程序退出时会自动安装更新

if __name__ == "__main__":
    main()
```

## 配置文件

在 `update_config.json` 中配置：

```json
{
    "VERSION_URL": "https://your-version-url/version.json",
    "UPDATE_URL": "https://your-update-url/update.zip",
    "CURRENT_VERSION": "1.0.0",
    "MAX_DOWNLOAD_SIZE": 104857600,
    "TIMEOUT": 30,
    "MAX_RETRY": 3,
    "RETRY_DELAY": 5
}
```

在 `update_config.json` 中配置：

```json
{
    "version": "1.0.0",
    "sha256": "更新包的SHA256值",
    "description": "更新说明",
    "release_date": "2024-03-20",
    "min_required": "1.0.0"
}
```

## 许可证

MIT License 

## 更新日志

### 1.0.1 (2024-03-xx)

#### 新特性
- 添加了后台更新线程，不再阻塞主程序运行
- 增加了更新检查超时机制，最多等待5秒
- 自动识别开发/生产环境，动态调整配置路径

#### 改进
- 优化了日志输出，添加了更多状态提示
- 改进了配置文件管理，支持多环境配置
- 完善了包的安装配置和文档

#### 修复
- 修复了更新过程中可能的路径问题
- 解决了在生产环境下的文件访问权限问题 