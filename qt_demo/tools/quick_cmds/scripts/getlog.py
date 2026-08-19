import subprocess
import sys
from datetime import datetime
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import zipfile

# 隐藏子进程(adb/7z)的控制台窗口，避免 GUI 程序启动时弹黑窗
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

class AdbUtil:
    def __init__(self, device_id=None):
        """
        初始化 ADB 工具类
        :param device_id: 指定设备ID (通过 adb devices 查看)，不指定则默认第一个设备
        """
        self.device_id = device_id

    def _run(self, cmd_list):
        """
        内部方法，执行命令并返回结果
        """
        try:
            result = subprocess.run(cmd_list, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            return result.stdout.strip()
        except Exception as e:
            return f"执行失败: {e}"

    def adb(self, *args):
        """
        执行 adb 命令
        """
        cmd = ["adb"]
        if self.device_id:
            cmd += ["-s", self.device_id]
        cmd += list(args)
        return self._run(cmd)

    def shell(self, *args):
        """
        执行 adb shell 命令
        """
        cmd = ["adb"]
        if self.device_id:
            cmd += ["-s", self.device_id]
        cmd += ["shell"] + list(args)
        return self._run(cmd)
    def pull(self, remote_path, local_path):
        '''
        调用 adb pull 命令，把 Android 设备里的文件拉取到本地
        :param remote_path: 设备上的路径 (例如 /sdcard/test.txt)
        :param local_path: 本地保存路径 (例如 ./test.txt)
        :param self.device_id: 设备ID（多设备时使用 adb -s <id>）
        '''
        cmd = ["adb"]
        if self.device_id:
            cmd += ["-s", self.device_id]
        cmd += ["pull", remote_path, local_path]

        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if result.returncode == 0:
            print("拉取成功:", result.stdout.strip())
        else:
            print("拉取失败:", result.stderr.strip())
            
def unzip_with_7z(zip_path: Path, dest_dir: Path, password: str):
    """
    使用 7-Zip 解压带密码的 zip 文件
    :param zip_path: zip 文件路径
    :param dest_dir: 解压目标目录
    :param password: zip 密码
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "7z", "x",  # x 表示完整解压
        str(zip_path),
        f"-p{password}",
        f"-o{dest_dir}",  # 输出目录
        "-y"  # 自动覆盖
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        if result.returncode == 0:
            return f"解压完成: {zip_path} → {dest_dir}"
        else:
            return f"解压失败: {zip_path}, 错误: {result.stderr.strip()}"
    except FileNotFoundError:
        return "未找到 7z，请确认已安装并添加到 PATH"


def unzip_all_in_dir_multithread(root_dir: str, password: str, max_workers: int = 4):
    """
    查找 root_dir 下所有 zip 文件并多线程解压（只解压 zip，不递归解压新生成目录）
    """
    root_dir = Path(root_dir)
    if not root_dir.exists():
        print(f"目录不存在: {root_dir}")
        return

    # 只查找 root_dir 下 zip 文件（不递归解压新的目录）
    zip_files = list(root_dir.rglob("*.zip"))
    if not zip_files:
        print("没有找到 zip 文件")
        return

    print(f"找到 {len(zip_files)} 个 zip 文件，开始多线程解压...")

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_zip = {
            executor.submit(
                unzip_with_7z,
                zip_file,
                zip_file.parent / zip_file.stem,
                password
            ): zip_file
            for zip_file in zip_files
        }

        for future in as_completed(future_to_zip):
            zip_file = future_to_zip[future]
            try:
                result = future.result()
                results.append(result)
                print(result)
            except Exception as e:
                print(f"解压失败: {zip_file}, 错误: {e}")

    print("所有 zip 文件处理完成！")
    return results


# 示例
if __name__ == "__main__":
    adb = AdbUtil()  # 默认设备
    serialno = adb.shell("getprop", "ro.serialno")
    print("序列号:", serialno)
    now = datetime.now()
    pull_time = now.strftime("%Y-%m-%d-%H-%M-%S")
    logdir_name = f"{serialno}--{pull_time}"
    print(logdir_name)
    current_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"E:\PowerShell")
    current_dir.mkdir(exist_ok=True)
    log_dir = current_dir / logdir_name
    log_dir.mkdir(exist_ok=True)
    adb.pull("/sdcard/Android/data/com.nothing.logkit/files/logs/", str(log_dir))
    target_dir = log_dir
    pwd = "ADe88sWMJt8P4QCA2E^VNacbFtY6cOdB"
    unzip_all_in_dir_multithread(target_dir, pwd, max_workers=20)
    

    # 如果有多个设备
    # adb = AdbUtil(device_id="emulator-5554")
    # print(adb.shell("getprop", "ro.serialno"))
