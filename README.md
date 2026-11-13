# 校园网 eLearning 自动认证（Windows 11）

面向兰州大学校园网的 Windows 后台工具：按信号选择已保存的 `iLZU` / `LZU`，并在需要时进行 eLearning 网页认证。使用本机 Microsoft Edge，不下载 Chromium。

要求：Windows 11、Python 3.13（含 tkinter）、已安装的 Edge，以及 Windows 中已保存的校园 Wi-Fi 配置。源码位于 `outputs/`，虚拟环境位于仓库根目录 `.venv/`。

## 安装

下载或克隆仓库，在根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r outputs\requirements.txt
```

不要执行 `playwright install`，程序使用本机 Edge。

## 首次使用

在项目根目录打开 PowerShell：

```powershell
.\outputs\campus.cmd setup
```

在本机窗口输入账号、密码，点击“保存凭据并启动”。账号填写 eLearning 账号，不需要加 `@study`。凭据只写入当前 Windows 用户的凭据管理器，目标名称为 `CampusAutoAuth/10.10.0.166/eLearning/v1`。不通过命令行参数、环境变量、配置文件或日志传递密码。更新密码也使用此命令。

## 启动、查看、停止及卸载

```powershell
# 无窗口后台启动
.\outputs\campus.cmd start
# 查看监控进程状态
.\outputs\campus.cmd status
# 立即检测互联网
.\outputs\campus.cmd check
# 停止监控（会等待正在进行的浏览器操作结束，最多 90 秒）
.\outputs\campus.cmd stop
# 开启当前 Windows 用户登录后自启动，无需管理员权限
.\outputs\campus.cmd install-startup
# 仅取消自启动
.\outputs\campus.cmd remove-startup
# 卸载：停止进程，删除本工具的自启动项和凭据
.\outputs\campus.cmd uninstall
```

`stop` 不取消下次 Windows 登录自启动。`uninstall` 保留项目文件和日志，不会删除其他文件；卸载后可自行删除本项目生成的文件。自启动使用当前用户 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 下的 `CampusAutoAuth-eLearning` 值，移动项目后需要重新安装自启动。工具仅在断网恢复时连接已保存的校园 Wi-Fi，不修改其他启动项、代理或防火墙设置。

## 工作方式

- 断网恢复时先通过 Windows WLAN API 扫描 `iLZU` 和 `LZU`，从可连接且已保存的配置中选信号较强者；同强度优先保持当前网络。连接请求完成后等待 Wi-Fi 关联及地址分配，再检测互联网，必要时才进行网页认证。即使候选仍是当前 SSID，也会请求重新连接，处理需要手动点击 Wi-Fi 的情况。
- 正常联网时不切换；已连接其他非校园 Wi-Fi 的接口不改动。不会创建 Wi-Fi 配置或读取 Wi-Fi 密码。如果扫描受 Windows 权限限制，尝试使用系统缓存；没有校园候选或 WLAN API 不可用时，保留原有连接并继续网页恢复流程。Wi-Fi 恢复同样遵循下述退避间隔。

- 每 15 秒并行访问 Microsoft、华为、Cloudflare 三个 HTTPS 检测端点，校验状态码及预期响应内容，拒绝跳转。任意一个成功即视为联网，连续两轮全部失败才尝试认证。单次网络请求超时为 4 秒；DNS 或系统网络栈异常时实际周期可能延长。
- 认证运行在独立线程，监控继续检测网络；同一时间只有一次认证。使用用户级全局命名互斥量防止跨会话重复运行，停止通过 Windows 事件通知，不按进程名批量杀进程。
- 已检查真实入口和脚本：账号认证标签 `.tab-item[data="account"]`，eLearning 选项 `[data-value="@study"]`，输入框 `#username`、`#password`，提交按钮 `#login-account`。选择后验证底层 select 值，取消记住密码，勾选页面服务协议。若出现验证码，跳过自动提交，需要手动打开校园网页面完成认证。
- 登录后多次检查外网恢复，失败按 60、120、240、480、900 秒退避，之后最多每 15 分钟重试。已联网时不会主动注销或重新登录。只有检测失败并且能操作到认证表单时才提交凭据。
- 每次使用临时 Edge 上下文，不保存浏览器配置、Cookie、截图、追踪或 HAR；限制该上下文请求到指定认证主机。日志不记录用户名、密码、网页正文或可能包含密码的异常信息。
- 日志在 `logs/monitor.log`，每份最多 1 MiB，保留 5 份备份。常用事件：`INTERNET_ONLINE`、`RECOVERY_ATTEMPT`、`WIFI_CONNECT`、`WIFI_CONNECTED`、`RECOVERY_VERIFIED`、`LOGIN_VERIFIED`、`CREDENTIALS_MISSING`、`CAPTCHA_REQUIRED`、`LOGIN_ERROR`。

所有外部探测端点都不可达并不必然代表认证失效，因此只有真实登录表单可用时才会尝试提交。学校入口使用 HTTP，本工具遵循该入口，不能为学校的传输协议增加 HTTPS 安全保障。自动认证包含勾选学校页面服务协议。

## 测试与维护

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s outputs -p test_*.py -v
```

依赖重建（不下载浏览器）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r outputs\requirements.txt
```

每位使用者都需要在本机录入自己的凭据。本项目已通过 19 项单元测试及本机 Windows 接口检查；不同网络环境下仍需验证完整重连效果。当前已联网时不强制断开现有认证。若学校修改网页结构，程序会记录失败并退避，需要重新检查页面更新选择器。
