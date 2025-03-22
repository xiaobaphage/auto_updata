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
from typing import Optional, Dict, Tuple, List
import json
from pathlib import Path
from packaging import version
from tqdm import tqdm
from datetime import datetime, timedelta

# 全局配置
APP_NAME = "YourAppName"  # 应用程序名称
DEBUG = False

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

# 获取备份目录
def get_backup_dir() -> Path:
    """获取备份目录路径"""
    backup_base = Path(tempfile.gettempdir()) / APP_NAME
    backup_base.mkdir(parents=True, exist_ok=True)
    return backup_base

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
    required_fields = {
        "VERSION_URL": str,
        "UPDATE_URL": str,
        "CURRENT_VERSION": str,
        "MAX_DOWNLOAD_SIZE": int,
        "TIMEOUT": int,
        "BACKUP_DIR": str,
        "MAX_RETRY": int,
        "RETRY_DELAY": int,
        "MAX_BACKUP_COUNT": int
    }
    
    try:
        for field, field_type in required_fields.items():
            if field not in config:
                logger.error(f"缺少必要配置项: {field}")
                return False
            if not isinstance(config[field], field_type):
                logger.error(f"配置项类型错误: {field}")
                return False
        
        if not is_valid_version(config["CURRENT_VERSION"]):
            logger.error("当前版本号格式无效")
            return False
            
        if not config["VERSION_URL"].startswith("https://"):
            logger.error("版本检查URL必须使用HTTPS")
            return False
            
        if not config["UPDATE_URL"].startswith("https://"):
            logger.error("更新包URL必须使用HTTPS")
            return False
            
        return True
    except Exception as e:
        logger.error(f"配置验证失败: {e}")
        return False

# 从配置文件加载配置
def load_config() -> Dict:
    config_path = APP_DATA_DIR / 'update_config.json' if not DEBUG else Path('update_config.json')
    default_config = {
        "VERSION_URL": "https://your-version-url/version.json",
        "UPDATE_URL": "https://your-update-url/update.zip",
        "CURRENT_VERSION": "1.0.0",
        "MAX_DOWNLOAD_SIZE": 104857600,
        "TIMEOUT": 30,
        "BACKUP_DIR": str(get_backup_dir()),  # 使用临时目录
        "MAX_RETRY": 3,
        "RETRY_DELAY": 5,
        "MAX_BACKUP_COUNT": 5
    }
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = {**default_config, **json.load(f)}
                if validate_config(config):
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

def clean_old_backups():
    """清理旧的备份文件"""
    try:
        backup_dir = Path(CONFIG["BACKUP_DIR"])
        if not backup_dir.exists():
            return
            
        # 获取所有备份，包括可能存在的其他进程创建的备份
        backups = sorted(
            [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        # 清理超过最大数量的备份
        for backup in backups[CONFIG["MAX_BACKUP_COUNT"]:]:
            try:
                shutil.rmtree(backup, ignore_errors=True)
                logger.info(f"已清理旧备份: {backup}")
            except Exception as e:
                logger.warning(f"清理备份失败: {backup}, 错误: {e}")
                
        # 清理超过24小时的备份
        current_time = time.time()
        for backup in backups[:CONFIG["MAX_BACKUP_COUNT"]]:
            try:
                if current_time - backup.stat().st_mtime > 86400:  # 24小时 = 86400秒
                    shutil.rmtree(backup, ignore_errors=True)
                    logger.info(f"已清理过期备份: {backup}")
            except Exception as e:
                logger.warning(f"清理过期备份失败: {backup}, 错误: {e}")
                
    except Exception as e:
        logger.warning(f"清理旧备份失败: {e}")

def calculate_dir_hash(path: Path, exclude_dirs: List[str] = None) -> str:
    """计算目录的哈希值
    
    Args:
        path: 要计算哈希的目录路径
        exclude_dirs: 要排除的目录列表
    """
    if exclude_dirs is None:
        exclude_dirs = ['.git', '__pycache__']
        
    hasher = hashlib.sha256()
    try:
        for file in sorted(path.rglob('*')):
            if file.is_file() and not any(p in file.parts for p in exclude_dirs):
                rel_path = str(file.relative_to(path))
                hasher.update(rel_path.encode())
                hasher.update(file.read_bytes())
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"计算目录哈希值失败: {e}")
        return ""

def backup_current_version() -> Optional[str]:
    """备份当前版本"""
    backup_dir = Path(CONFIG["BACKUP_DIR"])
    backup_dir.mkdir(exist_ok=True)
    
    # 创建带时间戳和进程ID的备份目录，确保唯一性
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid()
    version_backup_dir = backup_dir / f"backup_{CONFIG['CURRENT_VERSION']}_{timestamp}_{pid}"
    version_backup_dir.mkdir(exist_ok=True)
    
    try:
        # 计算原始目录的哈希值（排除备份目录）
        exclude_dirs = ['.git', '__pycache__', CONFIG["BACKUP_DIR"]]
        original_hash = calculate_dir_hash(Path(), exclude_dirs)
        
        # 复制文件
        for file in Path().glob('**/*'):
            if file.is_file() and not any(p in file.parts for p in exclude_dirs):
                dest = version_backup_dir / file.relative_to(Path())
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, dest)
        
        # 验证备份
        backup_hash = calculate_dir_hash(version_backup_dir)
        if not original_hash or not backup_hash or backup_hash != original_hash:
            raise ValueError(f"备份验证失败\n原始哈希: {original_hash}\n备份哈希: {backup_hash}")
        
        logger.info(f"已备份当前版本到: {version_backup_dir}")
        clean_old_backups()
        return str(version_backup_dir)
    except Exception as e:
        logger.error(f"备份失败: {e}")
        if version_backup_dir.exists():
            shutil.rmtree(version_backup_dir)
        return None

def verify_zip_contents(zip_path: str) -> bool:
    """验证更新包内容的安全性"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # 检查是否包含可执行文件或危险文件
            dangerous_extensions = {'.exe', '.dll', '.bat', '.cmd', '.sh', '.vbs', '.js'}
            for file in zf.namelist():
                ext = Path(file).suffix.lower()
                if ext in dangerous_extensions:
                    logger.error(f"更新包含危险文件: {file}")
                    return False
                if '../' in file or file.startswith('/'):
                    logger.error(f"更新包含危险路径: {file}")
                    return False
        return True
    except Exception as e:
        logger.error(f"验证更新包内容失败: {e}")
        return False

def retry_operation(operation, max_retries: int = None, delay: int = None):
    """重试装饰器"""
    if max_retries is None:
        max_retries = CONFIG["MAX_RETRY"]
    if delay is None:
        delay = CONFIG["RETRY_DELAY"]
        
    def wrapper(*args, **kwargs):
        for i in range(max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                if i == max_retries - 1:
                    raise
                logger.warning(f"{operation.__name__} 失败，{delay}秒后重试: {e}")
                time.sleep(delay)
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
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip', mode='wb') as tmp_file:
            tmp_path = tmp_file.name
    
        client = httpx.Client(timeout=CONFIG["TIMEOUT"], verify=True, follow_redirects=True)
        with client.stream("GET", CONFIG["UPDATE_URL"]) as res:
            res.raise_for_status()
            file_size = int(res.headers.get("content-length", 0))
            if file_size > CONFIG["MAX_DOWNLOAD_SIZE"]:
                raise ValueError(f"更新包过大: {file_size/1024/1024:.1f}MB")
            
            content_type = res.headers.get("content-type", "").lower()
            valid_zip_types = [
                'application/zip',
                'application/x-zip-compressed',
                'application/zip-compressed',
                'application/octet-stream'
            ]
            if not any(content_type.startswith(t) for t in valid_zip_types):
                logger.warning(f"警告：内容类型 {content_type} 可能不是zip文件")
            
        hasher = hashlib.sha256()
        downloaded_size = 0
        with open(tmp_path, "wb") as f:
            with tqdm(total=file_size, unit='B', unit_scale=True, desc="下载进度") as pbar:
                for chunk in res.iter_bytes(chunk_size=8192):
                    downloaded_size += len(chunk)
                    if downloaded_size > CONFIG["MAX_DOWNLOAD_SIZE"]:
                        raise ValueError("文件大小超过限制")
                hasher.update(chunk)
                f.write(chunk)
                pbar.update(len(chunk))
        
        calculated_hash = hasher.hexdigest().upper()
        expected_hash = update_info["sha256"].upper()
        if calculated_hash != expected_hash:
            logger.error(f"文件校验失败:")
            logger.error(f"预期哈希值: {expected_hash}")
            logger.error(f"实际哈希值: {calculated_hash}")
            raise ValueError("文件校验失败")
            
        if not zipfile.is_zipfile(tmp_path):
            raise ValueError("无效的ZIP文件")
            
        if not verify_zip_contents(tmp_path):
            raise ValueError("更新包内容验证失败")
            
        # 设置临时文件的权限
        os.chmod(tmp_path, 0o600)
            
        return tmp_path
    except Exception as e:
        logger.error(f"下载更新失败: {e}")
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

def apply_update(zip_path: str):
    """应用更新"""
    script_path = Path(tempfile.mktemp(suffix='.bat'))
    backup_path = backup_current_version()
    
    if not backup_path:
        logger.error("备份失败，取消更新")
        return
    
    abs_zip_path = Path(zip_path).resolve()
    abs_cwd = Path.cwd().resolve()
    abs_backup = Path(backup_path).resolve()
    
    # 创建临时解压目录
    temp_extract_dir = Path(tempfile.mkdtemp(prefix='update_'))
    abs_temp_dir = temp_extract_dir.resolve()

    update_script = f"""
@echo off
chcp 65001 >nul
title 正在更新程序...
echo 正在等待程序关闭...
timeout /t 5 /nobreak >nul

REM 验证文件是否存在
if not exist "{abs_zip_path}" (
    echo 更新包不存在，正在恢复备份...
    xcopy /E /Y /I "{abs_backup}" "{abs_cwd}"
    echo 更新失败，已恢复备份
    rmdir /S /Q "{abs_temp_dir}" 2>nul
    timeout /t 5 >nul
    exit /b 1
)

REM 解压到临时目录
echo 正在解压更新包...
powershell -Command "$progressPreference = 'Continue'; Expand-Archive -Path '{abs_zip_path}' -DestinationPath '{abs_temp_dir}' -Force -ErrorAction Stop"
if %ERRORLEVEL% neq 0 (
    echo 解压失败，正在恢复备份...
    xcopy /E /Y /I "{abs_backup}" "{abs_cwd}"
    echo 已恢复备份
    rmdir /S /Q "{abs_temp_dir}" 2>nul
    timeout /t 5 >nul
    exit /b 1
)

REM 复制更新文件
echo 正在应用更新...
xcopy /E /Y /I "{abs_temp_dir}\\*" "{abs_cwd}"
if %ERRORLEVEL% neq 0 (
    echo 更新失败，正在恢复备份...
    xcopy /E /Y /I "{abs_backup}" "{abs_cwd}"
    echo 已恢复备份
    rmdir /S /Q "{abs_temp_dir}" 2>nul
    timeout /t 5 >nul
    exit /b 1
)

REM 清理文件
del "{abs_zip_path}" 2>nul
rmdir /S /Q "{abs_backup}" 2>nul
rmdir /S /Q "{abs_temp_dir}" 2>nul

echo 更新完成
timeout /t 5 >nul
(goto) 2>nul & del "%~f0"
"""
    try:
        # 设置更新脚本的权限
        script_path.write_text(update_script, encoding='utf-8')
        os.chmod(script_path, 0o700)
        logger.info("开始执行更新脚本")
        
        # 直接执行批处理文件
        subprocess.Popen(
            [str(script_path)],
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        logger.info("更新脚本已启动")
        
    except Exception as e:
        logger.error(f"创建更新脚本失败: {e}")
        if script_path.exists():
            script_path.unlink()
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

if __name__ == "__main__":
    try:
        @atexit.register
        def on_exit():
            if hasattr(sys, "update_pending"):
                apply_update(sys.update_pending)

        logger.info(f"当前版本: {CONFIG['CURRENT_VERSION']}")
        
        if update_info := check_update():
            logger.info(f"发现新版本: {update_info['version']}")
            logger.info(f"更新说明: {update_info.get('description', '无')}")
            logger.info(f"发布时间: {update_info.get('release_date', '未知')}")
            
            # 自动下载并安装更新
            logger.info("开始下载更新...")
            if zip_file := download_update(update_info):
                sys.update_pending = zip_file
                logger.info("更新已下载，退出程序后自动安装...")
        else:
            logger.info("未发现新版本")

        print("\n程序运行中...")
        input("按回车退出程序")
        
    except Exception as e:
        logger.error(f"程序异常: {e}")
        input("程序发生错误，按回车退出...")