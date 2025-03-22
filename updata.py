import httpx
import hashlib
import os
import sys
import zipfile
import subprocess
import atexit
import tempfile
import logging
import shutil
import time
import socket
import getpass
from typing import Optional, Dict, Tuple, List, Callable
import json
from pathlib import Path
from packaging import version
from tqdm import tqdm
from datetime import datetime, timedelta
import re
import threading

# 全局配置
APP_NAME = "YourAppName"  # 应用程序名称
DEBUG = True

# 获取应用数据目录
def get_app_data_dir() -> Path:
    """获取应用数据目录"""
    if DEBUG:
        return Path.cwd()
    else:
        app_data = Path(os.getenv('APPDATA', '')) / APP_NAME
        app_data.mkdir(parents=True, exist_ok=True)
        return app_data

# 应用数据目录
APP_DATA_DIR = get_app_data_dir()

# 创建日志目录
LOG_DIR = APP_DATA_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 配置日志
def setup_logging():
    """配置日志系统"""
    # 获取系统和用户信息
    computer_name = socket.gethostname()
    username = getpass.getuser()
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 创建更新专用日志文件
    update_log_file = LOG_DIR / f'update_{current_time}_{computer_name}.log'
    
    # 配置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(message)s'
    )
    
    # 文件处理器
    file_handler = logging.FileHandler(update_log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 记录启动信息
    logger.info("=" * 50)
    logger.info(f"更新程序启动")
    logger.info(f"计算机名称: {computer_name}")
    logger.info(f"用户名: {username}")
    logger.info(f"操作系统: {sys.platform}")
    logger.info(f"Python版本: {sys.version}")
    logger.info("=" * 50)
    
    return logger

# 初始化日志系统
logger = setup_logging()

def is_valid_version(ver_str: str) -> bool:
    """验证版本号格式是否有效"""
    try:
        version.parse(ver_str)
        return True
    except version.InvalidVersion:
        logger.error(f"无效的版本号格式: {ver_str}")
        return False

def validate_config(config: Dict) -> bool:
    """验证配置是否有效"""
    try:
        # 验证必需字段
        required_fields = {
            "VERSION_URL": (str, "https://"),
            "UPDATE_URL": (str, "https://"),
            "CURRENT_VERSION": (str, None),
            "MAX_DOWNLOAD_SIZE": (int, lambda x: x > 0),
            "TIMEOUT": (int, lambda x: x > 0),
            "MAX_RETRY": (int, lambda x: x > 0),
            "RETRY_DELAY": (int, lambda x: x > 0)
        }
        
        for field, (field_type, validator) in required_fields.items():
            # 检查字段是否存在
            if field not in config:
                raise ValueError(f"缺少必要配置项: {field}")
                
            # 检查类型
            if not isinstance(config[field], field_type):
                raise ValueError(f"配置项类型错误: {field}")
                
            # 执行自定义验证
            if validator:
                if isinstance(validator, str) and isinstance(config[field], str):
                    if not config[field].startswith(validator):
                        raise ValueError(f"{field} 必须以 {validator} 开头")
                elif callable(validator) and not validator(config[field]):
                    raise ValueError(f"{field} 值无效")
        
        # 验证版本号
        if not is_valid_version(config["CURRENT_VERSION"]):
            raise ValueError("当前版本号格式无效")
            
        return True
        
    except Exception as e:
        logger.error(f"配置验证失败: {e}")
        return False

def load_config() -> Dict:
    """从配置文件加载配置"""
    config_path = APP_DATA_DIR / 'update_config.json' if not DEBUG else Path('update_config.json')
    logger.info(f"配置文件路径: {config_path.absolute()}")
    
    default_config = {
        "VERSION_URL": "https://your-version-url/version.json",
        "UPDATE_URL": "https://your-update-url/update.zip",
        "CURRENT_VERSION": "1.0.0",
        "MAX_DOWNLOAD_SIZE": 104857600,
        "TIMEOUT": 30,
        "MAX_RETRY": 3,
        "RETRY_DELAY": 5
    }
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = {**default_config, **json.load(f)}
                if validate_config(config):
                    logger.info("成功加载配置文件")
                    return config
                logger.warning("配置验证失败，使用默认配置")
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}，使用默认配置")
    else:
        # 如果配置文件不存在，创建默认配置文件
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            logger.info(f"已创建默认配置文件: {config_path}")
        except Exception as e:
            logger.warning(f"创建默认配置文件失败: {e}")
    
    return default_config

CONFIG = load_config()

def retry_operation(operation, max_retries: int = None, delay: int = None):
    """重试装饰器"""
    if max_retries is None:
        max_retries = CONFIG["MAX_RETRY"]
    if delay is None:
        delay = CONFIG["RETRY_DELAY"]
        
    def wrapper(*args, **kwargs):
        last_error = None
        for i in range(max_retries):
            try:
                result = operation(*args, **kwargs)
                if result is not None:
                    return result
                # 如果返回None但没有异常，说明是预期的失败，不需要重试
                return None
            except httpx.RequestError as e:
                # 只对网络错误进行重试
                last_error = e
                if i < max_retries - 1:
                    logger.warning(f"{operation.__name__} 失败，{delay}秒后重试: {e}")
                    time.sleep(delay)
                continue
            except Exception as e:
                # 其他错误直接返回None
                logger.error(f"{operation.__name__} 失败: {e}")
                return None
                
        if last_error:
            logger.error(f"{operation.__name__} 重试{max_retries}次后仍然失败: {last_error}")
        return None
    return wrapper

@retry_operation
def check_update() -> Optional[Dict]:
    """检查更新并返回更新信息"""
    try:
        response = httpx.get(
            CONFIG["VERSION_URL"],
            timeout=CONFIG["TIMEOUT"],
            verify=True,
            follow_redirects=True
        )
        response.raise_for_status()
        data = response.json()
        
        if not is_valid_version(data.get("version", "")):
            logger.error("无效的版本号格式")
            return None
            
        if version.parse(data["version"]) > version.parse(CONFIG["CURRENT_VERSION"]):
            return data
        logger.info("当前已是最新版本")
        return None
    except httpx.TimeoutException:
        logger.error("更新检查超时")
    except httpx.HTTPStatusError as e:
        if e.response.status_code in [301, 302, 307, 308]:
            logger.error(f"重定向错误: {e.response.headers.get('location', '未知目标')}")
        else:
            logger.error(f"服务器错误: HTTP {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"网络请求失败: {e}")
    except json.JSONDecodeError:
        logger.error("版本信息格式错误")
    except Exception as e:
        logger.error(f"更新检查失败: {e}")
        return None

@retry_operation
def download_update(update_info: Dict) -> Optional[str]:
    """下载并验证更新包"""
    tmp_path = None
    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip', mode='wb') as tmp_file:
            tmp_path = tmp_file.name
            
            # 下载文件
            with httpx.Client(
                timeout=CONFIG["TIMEOUT"],
                verify=True,
                follow_redirects=True
            ) as client:
                # 先获取文件大小
                with client.stream('GET', CONFIG["UPDATE_URL"]) as response:
                    response.raise_for_status()
                    
                    # 获取文件大小
                    total_size = int(response.headers.get("content-length", 0))
                    if total_size > CONFIG["MAX_DOWNLOAD_SIZE"]:
                        raise ValueError(f"更新包过大: {total_size/1024/1024:.1f}MB")
                    
                    logger.info(f"更新包大小: {total_size/1024/1024:.1f}MB")
                    
                    # 使用tqdm显示下载进度
                    with tqdm(
                        total=total_size,
                        unit='B',
                        unit_scale=True,
                        desc="下载进度"
                    ) as pbar:
                        # 分块下载
                        for chunk in response.iter_bytes(chunk_size=8192):
                            if chunk:
                                tmp_file.write(chunk)
                                pbar.update(len(chunk))
                
        logger.info("下载完成，正在验证文件...")
                
        # 基本验证
        if not zipfile.is_zipfile(tmp_path):
            raise ValueError("无效的ZIP文件")
            
        logger.info("文件验证通过")
        return tmp_path
        
    except httpx.TimeoutException:
        logger.error("下载超时")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP错误: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"网络请求失败: {e}")
    except Exception as e:
        logger.error(f"下载更新失败: {e}")
        
    # 清理临时文件
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception as del_err:
            logger.error(f"清理临时文件失败: {del_err}")
    return None

def update_version(new_version: str) -> bool:
    """更新配置文件中的版本号"""
    try:
        config_path = APP_DATA_DIR / 'update_config.json' if not DEBUG else Path('update_config.json')
        
        # 读取当前配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 更新版本号
        config['CURRENT_VERSION'] = new_version
        
        # 写回配置文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
            
        logger.info(f"版本号已更新: {new_version}")
        return True
        
    except Exception as e:
        logger.error(f"更新版本号失败: {e}")
        return False

def apply_update(zip_path: str, new_version: str):
    """应用更新"""
    try:
        # 验证路径安全性
        abs_zip_path = Path(zip_path).resolve()
        abs_cwd = Path.cwd().resolve()
        
        if not abs_zip_path.exists():
            raise FileNotFoundError("更新包不存在")
        
        # 创建临时解压目录
        with tempfile.TemporaryDirectory(prefix='update_') as temp_dir:
            abs_temp_dir = Path(temp_dir).resolve()
            
            # 生成更新脚本
            update_script = f"""
@echo off
chcp 65001 >nul
title 正在更新程序...

echo 正在解压更新包...
powershell -Command "Expand-Archive -Path '{abs_zip_path}' -DestinationPath '{abs_temp_dir}' -Force"
if %ERRORLEVEL% neq 0 (
    echo 解压失败
    goto :CLEANUP
)

echo 正在应用更新...
xcopy "{abs_temp_dir}\\*" "{abs_cwd}" /E /Y /I
if %ERRORLEVEL% neq 0 (
    echo 更新失败
    goto :CLEANUP
)

:CLEANUP
del "{abs_zip_path}" 2>nul
rmdir /S /Q "{abs_temp_dir}" 2>nul
echo 更新完成
timeout /t 3 >nul
(goto) 2>nul & del "%~f0"
"""
            
            # 写入并执行更新脚本
            script_path = Path(tempfile.mktemp(suffix='.bat'))
            script_path.write_text(update_script, encoding='utf-8')
            
            # 更新版本号
            update_version(new_version)
            
            # 执行更新脚本
            subprocess.Popen(
                [str(script_path)],
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            logger.info("更新脚本已启动")
            
    except Exception as e:
        logger.error(f"应用更新失败: {e}")

# 添加更新进度回调
class UpdateProgress:
    def __init__(self):
        self._callbacks = []
        
    def register(self, callback):
        self._callbacks.append(callback)
        
    def notify(self, status: str, progress: float):
        for callback in self._callbacks:
            try:
                callback(status, progress)
            except Exception as e:
                logger.error(f"进度回调执行失败: {e}")

# 添加代理支持
def get_proxy_settings() -> Optional[str]:
    """获取代理设置"""
    try:
        proxy_config = CONFIG.get("PROXY", {})
        if proxy_config.get("enabled", False):
            # 返回 https 代理地址，如果没有则返回 http 代理地址
            return proxy_config.get("https") or proxy_config.get("http")
    except Exception as e:
        logger.warning(f"获取代理设置失败: {e}")
    return None

class Updater:
    def __init__(self, on_complete: Callable[[bool], None] = None):
        """
        初始化更新器
        Args:
            on_complete: 更新完成的回调函数，参数为更新是否成功
        """
        self.on_complete = on_complete
        self._update_thread = None
        self._is_updating = False
        self._update_info = None
        self._update_file = None
        
        # 注册退出时的更新
        atexit.register(self._apply_pending_update)

    def check_and_update(self) -> bool:
        """检查更新（非阻塞）"""
        if self._is_updating:
            logger.warning("更新检查已在进行中")
            return False
            
        self._update_thread = threading.Thread(
            target=self._check_and_download,
            daemon=True
        )
        self._is_updating = True
        self._update_thread.start()
        return True
        
    def _check_and_download(self):
        """检查并下载更新"""
        try:
            logger.info(f"当前版本: {CONFIG['CURRENT_VERSION']}")
            
            if update_info := check_update():
                new_version = update_info['version']
                logger.info(f"发现新版本: {new_version}")
                logger.info(f"更新说明: {update_info.get('description', '无')}")
                
                if zip_file := download_update(update_info):
                    # 保存更新信息，等待程序退出时更新
                    self._update_info = update_info
                    self._update_file = zip_file
                    logger.info("更新已下载，退出程序后将自动安装")
                    if self.on_complete:
                        self.on_complete(True)
                else:
                    logger.error("下载更新失败")
                    if self.on_complete:
                        self.on_complete(False)
            else:
                logger.info("当前已是最新版本")
                if self.on_complete:
                    self.on_complete(True)
                
        except Exception as e:
            logger.error(f"更新检查异常: {e}")
            if self.on_complete:
                self.on_complete(False)
            
        finally:
            self._is_updating = False

    def _apply_pending_update(self):
        """在程序退出时应用更新"""
        if self._update_file and self._update_info:
            try:
                new_version = self._update_info['version']
                apply_update(self._update_file, new_version)
            except Exception as e:
                logger.error(f"应用更新失败: {e}")

    @property
    def is_updating(self) -> bool:
        """是否正在检查或下载更新"""
        return self._is_updating

    @property
    def has_update(self) -> bool:
        """是否有待安装的更新"""
        return bool(self._update_file and self._update_info)

    def get_update_info(self) -> Optional[Dict]:
        """获取更新信息"""
        return self._update_info

# 示例用法
if __name__ == "__main__":
    def update_complete(success: bool):
        if success:
            print("\n更新完成")
        else:
            print("\n更新失败")
    
    updater = Updater(on_complete=update_complete)
    updater.check_and_update()
    
    # 主程序继续运行
    while updater.is_updating:
        print("程序运行中...")
        time.sleep(1)

"""
from updata import Updater

def on_update_complete(success: bool):
    if success:
        print("更新成功，需要重启程序")
    else:
        print("更新失败，请稍后重试")

# 创建更新器实例
updater = Updater(on_complete=on_update_complete)

# 开始检查更新（非阻塞）
updater.check_and_update()

# 主程序继续运行
while True:
    # 你的主程序逻辑
    if updater.is_updating:
        print("正在更新中...")
    time.sleep(1)
"""