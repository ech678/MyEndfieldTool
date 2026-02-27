# -*- coding: utf-8 -*-
import ctypes
import sys
import threading
import time
import logging
import atexit
import psutil
import keyboard
from pydivert import WinDivert
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

# ================= 配置与版本 (保持原样) =================
VERSION = "20260227"
TARGET_PROCESS = "endfield.exe"
DEFAULT_BPS = 100
DEFAULT_HOTKEY = "alt+d"
LOG_FILE = "limiter.log"

# ================= 管理员权限检查 =================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()

# ================= 日志系统 =================
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)

def log(msg):
    logging.info(msg)
    if 'log_box' in globals() and log_box:
        log_box.insert(tk.END, msg + "\n")
        log_box.see(tk.END)

# ================= 获取目标进程端口 =================
def get_target_ports():
    ports = set()
    for p in psutil.process_iter(['pid', 'name']):
        try:
            if p.info['name'] and TARGET_PROCESS.lower() in p.info['name'].lower():
                for conn in p.connections(kind='inet'):
                    if conn.laddr and conn.laddr.port:
                        ports.add(conn.laddr.port)
        except:
            pass
    return ports

# ================= 限速核心 (严格保持你提供的逻辑) =================
class Limiter:
    def __init__(self):
        self.running = False
        self.thread = None
        self.driver = None
        self._lock = threading.Lock()

    def start(self, bps):
        with self._lock:
            if self.running or (self.thread and self.thread.is_alive()):
                log("系统忙：正在清理旧连接...")
                return
            
            self.running = True
            self.thread = threading.Thread(
                target=self.run, args=(bps,), daemon=True
            )
            self.thread.start()
            log(f"限速启动：{bps} bps")

    def stop(self):
        with self._lock:
            if not self.running:
                return
            self.running = False
            if self.driver:
                try:
                    self.driver.close()
                except:
                    pass
                self.driver = None
            log("正在断开内核拦截...")

    def run(self, bps):
        log("扫描游戏网络端口...")
        ports = set()
        
        while self.running and not ports:
            ports = get_target_ports()
            for _ in range(5):
                if not self.running: return
                time.sleep(0.1)

        if not self.running:
            return

        log(f"成功锁定端口: {ports}")
        
        tokens_up = bps
        tokens_down = bps
        last_time = time.time()

        w = None
        try:
            w = WinDivert("tcp or udp")
            w.open()
            self.driver = w

            while self.running:
                try:
                    pkt = w.recv()
                except:
                    break

                if not pkt: continue

                if pkt.tcp or pkt.udp:
                    if pkt.src_port not in ports and pkt.dst_port not in ports:
                        w.send(pkt)
                        continue

                    now = time.time()
                    elapsed = now - last_time
                    last_time = now

                    tokens_up = min(bps, tokens_up + elapsed * bps)
                    tokens_down = min(bps, tokens_down + elapsed * bps)
                    size_bits = len(pkt.payload) * 8

                    if pkt.is_outbound:
                        if size_bits > tokens_up:
                            sleep_time = (size_bits - tokens_up) / bps
                            time.sleep(min(sleep_time, 0.3)) 
                            tokens_up = 0
                        else:
                            tokens_up -= size_bits
                    else:
                        if size_bits > tokens_down:
                            sleep_time = (size_bits - tokens_down) / bps
                            time.sleep(min(sleep_time, 0.3))
                            tokens_down = 0
                        else:
                            tokens_down -= size_bits
                    
                    try:
                        w.send(pkt)
                    except:
                        if not self.running: break
                else:
                    w.send(pkt)

        except Exception as e:
            if self.running:
                log(f"内核异常: {e}")
        finally:
            if w:
                try: w.close()
                except: pass
            with self._lock:
                self.driver = None
            log(">>> 限速线程已完全释放")

limiter = Limiter()

# ================= UI 界面 (当前完美版布局) =================
root = tk.Tk()
root.title(f"Endfield 内核限速器 v{VERSION}")
root.geometry("560x680")
root.minsize(500, 620)

style = ttk.Style(root)
if 'clam' in style.theme_names():
    style.theme_use('clam')

font_title = ("Microsoft YaHei", 14, "bold")
font_normal = ("Microsoft YaHei", 10)
font_link = ("Microsoft YaHei", 10, "underline")

style.configure("TFrame", background="#f5f6f7")
style.configure("TLabel", background="#f5f6f7", font=font_normal, foreground="#333333")
style.configure("TButton", font=font_normal, padding=6)
style.configure("Title.TLabel", font=font_title, foreground="#1f2329")
style.configure("Desc.TLabel", font=("Microsoft YaHei", 9), foreground="#5c5f66")
style.configure("Link.TLabel", font=font_link, foreground="#00a1d6", background="#f5f6f7")
style.configure("TLabelframe", background="#f5f6f7")
style.configure("TLabelframe.Label", font=("Microsoft YaHei", 10, "bold"), background="#f5f6f7", foreground="#333333")

root.config(bg="#f5f6f7")
main_frame = ttk.Frame(root, padding=20)
main_frame.pack(fill="both", expand=True)

# 头部：标题与介绍
header_frame = ttk.Frame(main_frame)
header_frame.pack(fill="x", pady=(0, 10))
ttk.Label(header_frame, text=f"Endfield 内核限速器 {VERSION}", style="Title.TLabel").pack(anchor="w", pady=(0, 5))
desc_text = "本软件旨在利用联网同步时滑索状态不同步的 BUG 实现滑索自由下车。"
ttk.Label(header_frame, text=desc_text, style="Desc.TLabel", wraplength=520, justify="left").pack(anchor="w")

# B站链接
link_frame = ttk.Frame(header_frame)
link_frame.pack(anchor="w", pady=(5, 0))
ttk.Label(link_frame, text="作者: Echoes678 的 B站主页: ", style="Desc.TLabel").pack(side="left")
bili_link = ttk.Label(link_frame, text="https://space.bilibili.com/1292466375", style="Link.TLabel", cursor="hand2")
bili_link.pack(side="left")
bili_link.bind("<Button-1>", lambda e: webbrowser.open("https://space.bilibili.com/1292466375"))

# TIPS 区域
tips_frame = ttk.Frame(main_frame)
tips_frame.pack(fill="x", pady=(10, 15))
ttk.Label(tips_frame, text="网络异常急救指令 (管理员权限):", font=("Microsoft YaHei", 9, "bold")).pack(anchor="w")
cmd_text = "netsh winsock reset; netsh int ip reset; ipconfig /flushdns"
cmd_box = tk.Text(tips_frame, height=2, font=("Consolas", 9), bg="#ebecee", fg="#444", relief="flat", padx=10, pady=8)
cmd_box.insert("1.0", cmd_text)
cmd_box.config(state="disabled")
cmd_box.pack(fill="x", pady=5)

# 配置面板
settings_frame = ttk.LabelFrame(main_frame, text=" ⚙️ 配置选项 ", padding=15)
settings_frame.pack(fill="x", pady=(0, 15))

# 限速值
bps_frame = ttk.Frame(settings_frame)
bps_frame.pack(fill="x", pady=(0, 10))
ttk.Label(bps_frame, text="限速值 (bps):", width=12).pack(side="left")
bps_var = tk.IntVar(value=DEFAULT_BPS)
ttk.Entry(bps_frame, textvariable=bps_var, font=font_normal).pack(side="left", fill="x", expand=True)

# 热键
hk_frame = ttk.Frame(settings_frame)
hk_frame.pack(fill="x")
ttk.Label(hk_frame, text="全局热键:", width=12).pack(side="left")
hotkey_var = tk.StringVar(value=DEFAULT_HOTKEY)
ttk.Entry(hk_frame, textvariable=hotkey_var, font=font_normal).pack(side="left", fill="x", expand=True, padx=(0, 10))

# 热键应用逻辑
current_hotkey = None
def toggle():
    btn.config(state="disabled")
    if limiter.running:
        limiter.stop()
        btn.config(text="▶ 开始限速")
    else:
        limiter.start(bps_var.get())
        btn.config(text="⏹ 停止限速")
    root.after(400, lambda: btn.config(state="normal"))

def update_hotkey():
    global current_hotkey
    try:
        if current_hotkey: keyboard.remove_hotkey(current_hotkey)
        current_hotkey = keyboard.add_hotkey(hotkey_var.get(), toggle)
        log(f"热键生效: {hotkey_var.get()}")
    except:
        log("热键设置无效！")

ttk.Button(hk_frame, text="应用热键", command=update_hotkey, width=10).pack(side="right")

# 置顶选项
topmost_var = tk.BooleanVar(value=False)
ttk.Checkbutton(settings_frame, text="窗口始终置顶", variable=topmost_var, command=lambda: root.attributes("-topmost", topmost_var.get())).pack(anchor="w", pady=(10, 0))

# 主控制按钮
btn = ttk.Button(main_frame, text="▶ 开始限速", command=toggle)
btn.pack(fill="x", pady=(0, 15), ipady=8)

# 日志区域
log_frame = ttk.LabelFrame(main_frame, text=" 📝 运行日志 ", padding=10)
log_frame.pack(fill="both", expand=True)
log_scroll = ttk.Scrollbar(log_frame)
log_scroll.pack(side="right", fill="y")
log_box = tk.Text(log_frame, height=8, font=("Consolas", 9), bg="white", relief="flat", yscrollcommand=log_scroll.set)
log_box.pack(fill="both", expand=True)
log_scroll.config(command=log_box.yview)

# 初始化
update_hotkey()

def on_close():
    if messagebox.askyesno("退出", "确定要退出限速器吗？"):
        limiter.stop()
        root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
atexit.register(limiter.stop)

log(f"程序启动成功 - Version {VERSION}")
root.mainloop()