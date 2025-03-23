import time
import logging
from updata import Updater, logger

def run_main_program() -> None:
    """运行主程序的实际逻辑"""
    print("\n主程序已启动")
    print("按 Ctrl+C 退出程序")
    
    try:
        while True:
            # 这里放置你的主程序代码
            # 例如：处理业务逻辑、UI 更新等
            print(".", end="", flush=True)  # 显示程序在运行
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到退出信号")
        return

def main() -> None:
    """主程序入口"""
    try:
        print("程序启动中...")
        
        # 初始化更新器（会在后台检查更新）
        updater = Updater.initialize()
        
        # 运行主程序
        run_main_program()
        
        # 检查是否有待安装的更新
        if updater.has_update:
            print("正在安装更新，请稍候...")
            
    except KeyboardInterrupt:
        print("\n正在退出程序...")
        if updater.has_update:
            print("正在安装更新，请稍候...")
    except Exception as e:
        logger.error(f"程序运行异常: {str(e)}")
        print(f"\n程序发生错误: {str(e)}")
    finally:
        print("程序已退出")

if __name__ == "__main__":
    main() 