# BOM管理系统

Python + PyQt5 桌面 BOM 管理工具，使用本地 SQLite，无需 MySQL 服务。支持 SKU 整树独立历史版本、物料子 BOM、替代料、Excel 导入导出、物料查找、版本和变更记录管理。

- 源码仓库：<https://github.com/acbiong/BOM_Manager>
- 软件版本以 [`VERSION`](VERSION) 为准；关于窗口显示随包保存的 Git 提交信息。
- 开发要求：[软件开发规格书](docs/软件开发规格书.md)、[需求追踪审计](docs/需求追踪审计报告.md)。
- 继续开发前必读：[Codex项目记忆](docs/CODEX_MEMORY.md)。这是可迁移的项目交接记录，不是 Codex 内部状态或完整聊天记录。

## 1. 获取源码与适用环境

Linux 推荐在 **deepin 25 / Ubuntu 24.04 x86_64、Python 3.12** 上构建；新增 Windows 10/11 x64 原生构建入口。当前源码含 Python 3.12 的语法，Python 3.11 及更早版本不适用。AppImage 脚本面向 Linux x86_64；不承诺跨架构或在更旧 glibc 系统上运行。

```bash
git clone https://github.com/acbiong/BOM_Manager.git
cd BOM_Manager
```

也可复制完整源码目录或解压源码 ZIP，路径可自行选择，包含中文和空格时需加引号。不要复制旧电脑的 `.venv`、`.tmp`；应重新安装依赖。建议 clone 保留提交历史。ZIP 不含 `.git` 时可直接运行/手动构建，但关于窗口无法提供原提交详情，自动提交流程需先初始化仓库：

```bash
git init
git config user.name "你的姓名"
git config user.email "你的邮箱"
git add .
git commit -m "初始化导入的BOM管理系统源码"
```

## 2. 安装系统和 Python 依赖

以下命令适用于 deepin/Debian 系列，需 sudo 权限和网络。其他发行版需安装同类 Qt/X11 动态库。

```bash
sudo apt update
sudo apt install -y git curl ca-certificates python3 python3-venv python3-pip \
  build-essential binutils file squashfs-tools patchelf fonts-dejavu-core \
  libgl1 libegl1 libxkbcommon-x11-0 libxcb-xinerama0 libxcb-cursor0 \
  libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
  libxcb-randr0 libxcb-shape0 libxcb-xfixes0 libdbus-1-3 libfontconfig1
python3 --version
```

确认 Python 为 3.12 或更新的兼容版本，再创建独立环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip check
```

依赖含 PyQt5（界面）、openpyxl（.xlsx）、xlrd（.xls）、PyInstaller（打包）、Pillow（生成打包图标）；SQLite 属于 Python 标准库。当前开发环境已使用 PyQt5 5.15.10、openpyxl 3.1.5、PyInstaller 6.22.3、Pillow 11.3.0。`requirements.txt` 使用最低版本约束，并非锁定环境；升级依赖后须重新测试。

Linux每次开启新终端可先进入项目并执行 `. .venv/bin/activate`。测试与收尾脚本优先使用项目 `.venv`，也可通过 `BOM_PYTHON` 指定解释器；Windows统一入口见第11节。

## 3. 运行源码

在有桌面显示服务的终端中执行：

```bash
python3 src/main.py
```

首次启动选择“新建数据库”并指定文件名，或选用现有本软件 SQLite 数据库。源码模式的 `config.ini` 位于项目根目录，数据库位置保存在其中；数据库及导入目录以相对config.ini的路径保存，使用统一的`/`分隔符；保持目录相对位置一起复制即可跨Windows、Deepin和Ubuntu读取。旧的本机绝对路径会自动迁移；无法识别的异系统绝对路径需重新选择数据库。同一软件目录只能运行一个实例。

配置与业务数据库被 Git 忽略，不随 clone 迁移。需要迁移业务数据时，先关闭软件，再单独复制数据库和配置，并在新机核对路径。界面主题、导出路径等部分偏好保存在 Qt 的 `Biong/BOMManager` 用户设置中，不属于源码。

## 4. 测试和检查

```bash
mkdir -p test_reports .tmp package
tools/run_tests.sh
```

流程包含 137 项需求追踪编号审计、unittest 回归、源码编译校验。报告写入 `test_reports/`，编译临时文件在 `.tmp/`；两者均不提交 Git。Qt 测试使用离屏模式，无需真实桌面，但单实例测试需要本地 socket 权限；若 Codex 沙箱阻止 QLocalServer，允许该测试命令使用适当权限重跑，不要删掉测试。

回归通过不等于真实桌面验收：仍需在目标电脑双击 AppImage，检查数据库选择、Excel 导入导出和窗口交互。

## 5. 安装 AppImage 打包工具

```bash
mkdir -p "$HOME/.local/bin"
curl -fL https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
  -o "$HOME/.local/bin/appimagetool"
curl -fL https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
  -o "$HOME/.local/bin/runtime-x86_64"
chmod +x "$HOME/.local/bin/appimagetool" "$HOME/.local/bin/runtime-x86_64"
export PATH="$HOME/.local/bin:$PATH"
```

下载的是官方 continuous 构建，会随上游更新。2026-10-10 校验的 runtime SHA256 为 `156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074`，与当前脚本所需提取分支匹配。脚本会检查该分支；若提示“无法定位 AppImage runtime 的提取分支”，须适配或使用已验证的 runtime，不能跳过校验。可用 `APPIMAGE_RUNTIME` 指定其他路径，保留已验证工具和 SHA256 有助于后续复现。

当前包默认采用解压运行策略，目标机器通常不需要 FUSE；工具本身通过 `APPIMAGE_EXTRACT_AND_RUN=1` 运行。仍需要同架构 Linux 的基础图形系统及可写临时目录。

## 6. 手动构建 AppImage（不提交、不升版）

```bash
. .venv/bin/activate
export PATH="$HOME/.local/bin:$PATH"
APPIMAGE_EXTRACT_AND_RUN=1 APPIMAGE_RUNTIME="$HOME/.local/bin/runtime-x86_64" \
  tools/build_appimage.sh
```

脚本执行测试、生成 Git 构建信息、PyInstaller 编译、图标和 AppDir 构建，输出：

- `package/BOM_Manager_<版本>_<日期时间>.AppImage`
- 同名 `.AppImage.sha256`
- 临时目录 `.tmp/build`、`.tmp/dist`、`.tmp/spec`、`.tmp/AppDir` 及 `.tmp/build_info.json`

检查并运行生成的具体文件（替换示例路径）：

```bash
sha256sum -c package/BOM_Manager_版本_日期时间.AppImage.sha256
chmod +x package/BOM_Manager_版本_日期时间.AppImage
./package/BOM_Manager_版本_日期时间.AppImage
```

AppImage 可复制到另一台 deepin 25 x86_64 电脑，目标机无需安装 Python。可写的 AppImage 所在目录用于便携配置，否则回退用户配置目录。建议先从终端运行一次检查输出，再验证双击。

`tools/build.sh`、`tools/release.sh` 是旧的独立 ELF 构建入口，不能替代当前 AppImage 流程。不要使用 `watch_source.sh` 启动常驻源码监控。

## 7. 开发收尾：测试、升版、提交、打包

首次 clone/复制后需重新启用钩子，Git 配置不会随源码自动安装：

```bash
git config user.name "你的姓名"
git config user.email "你的邮箱"
sh tools/enable_auto_packaging.sh
```

若复制丢失执行权限，可执行 `chmod +x tools/*.sh .githooks/*`。源码每次修改完成后，先检查 `git diff`，确认没有混入无关修改，再填写本次实际变更说明：

```bash
mkdir -p .tmp
cat > .tmp/change_message.txt <<'MESSAGE'
修复(模块)：具体问题及修复行为

- 本次变更点。
- 测试内容及验证结果。
MESSAGE
tools/finish_ai_change.sh --message-file .tmp/change_message.txt
```

可用 `BOM_RELEASE_VERSION=0.5.0 tools/finish_ai_change.sh --message-file .tmp/change_message.txt` 指定本次准确版本；不指定时仍自动升补丁号。

流程：测试/审计/编译 → 版本升级 → `git add -A` → Git 提交 → post-commit 按平台生成AppImage或Windows EXE。不要再单独升版或重复提交；不要只填“AI自动完成更新”等泛化描述。Git 提交不会自动 push。

若提交后打包失败，提交可能已经完成；先看 `git log -1`、日志和 `package/`，修复构建环境后运行手动 AppImage 构建，不要为了重试打包再次升版。缺少 appimagetool/runtime 时钩子可能跳过打包，须确认实际产物，不能仅凭提交成功宣称已打包。

## 8. 在另一台电脑继续使用 Codex

先完成源码、虚拟环境和构建工具安装。按 [OpenAI 官方 Codex CLI 文档](https://developers.openai.com/codex/cli/) 安装和登录（核对日期：2026-10-10）：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh -o /tmp/codex-install.sh
# 阅读安装脚本后执行：
sh /tmp/codex-install.sh
```

按安装输出配置 PATH，重新打开终端后进入项目：

```bash
cd /你的路径/BOM_Manager
. .venv/bin/activate
export PATH="$HOME/.local/bin:$PATH"
codex
```

首次启动按提示登录自己的 ChatGPT 账户或其他可用认证方式。Codex 账户、登录凭证、权限审批与旧机器的聊天记录不会随 Git 仓库迁移；不要将密钥、登录文件提交到项目。`codex resume` 用于恢复当前机器已有会话，不会自动恢复另一台机器的历史。

给新会话发送以下交接提示，并附上你的新需求：

> 请先阅读 docs/CODEX_MEMORY.md、README.md、docs/软件开发规格书.md、docs/需求追踪审计报告.md，检查 git status、VERSION 和最近提交。按照项目约定继续开发：SQLite/PyQt5、保留未保存的BOM缓存、修改后执行测试与需求审计，使用详细提交说明运行 tools/finish_ai_change.sh，核验 AppImage 和 SHA256；不得启动常驻监控。将本轮重要结论和未完成事项更新到 docs/CODEX_MEMORY.md。我的新需求是：……

跨机恢复以项目文件和当前 Git 状态为准，不依赖旧会话隐藏状态。无需为本项目迁移旧电脑的 Codex 私有配置或技能；遇到环境和权限差异应根据本机实际状态处理。

## 9. 常见问题

- `SyntaxError`：检查 Python 是否为 3.12+，虚拟环境是否激活。
- `No module named PIL/PyQt5/...`：使用当前虚拟环境的 `python3 -m pip install -r requirements.txt`。
- Qt `xcb` 插件无法加载：确认图形桌面及上述系统库，必要时用 `QT_DEBUG_PLUGINS=1 python3 src/main.py` 查看缺失库。不要把 `QT_QPA_PLATFORM=offscreen` 用于正常桌面运行。
- 新电脑测试路径错误：测试应使用仓库相对路径，禁止写死旧机器 `/home/biong` 路径。
- 打包慢：PyInstaller 和 AppImage 压缩耗时正常；临时文件均在 `.tmp/`，构建期间不要删除。
- Git 不自动打包：检查 `git config core.hooksPath` 是否为 `.githooks`、工具是否安装、虚拟环境和 PATH 是否正确；无常驻监控进程。


## 10. 0.5.0 跨平台发布

### Linux：deepin 25 / Ubuntu 24.04 及更新系统（x86_64）

AppImage内部改用PyInstaller目录模式，外部仍只有一个AppImage文件，避免AppImage与onefile双重解压。构建会检查所有ELF的x86_64架构、缺失动态库及所需glibc符号不高于2.38（deepin25基线；Ubuntu24.04为2.39）。这不是对所有未来Ubuntu版本/驱动组合的保证。Ubuntu Wayland桌面通常通过XWayland运行Qt xcb；需保留系统图形栈，不在包内替换glibc和图形驱动。

新增 `test_reports/linux_bundle_audit.json` 和包自检报告。自检使用临时数据库，检查Qt主窗口/物料库/BOM/关于、SQLite、Excel及单实例。构建结束会自动运行离屏自检；目标桌面仍需验收。

### Windows：生成单个EXE

须在 **Windows 10/11 x64 + 64位Python 3.12** 原生构建，Linux上的PyInstaller不能直接生成Windows EXE。安装Python时启用PATH，在PowerShell中：

```powershell
cd C:\你的路径\BOM_Manager
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\build_windows.py
```

脚本执行全量测试、版本/提交信息嵌入、ICO图标生成、`--onefile --windowed`编译、EXE启动自检和SHA256生成。产物为`package/BOM_Manager_版本_日期时间_windows_x64.exe`，无需目标机安装Python，相关Qt/VC运行库由PyInstaller依赖收集处理。构建失败或自检失败不能作为有效发布。

```powershell
Get-FileHash .\package\BOM_Manager_版本_日期时间_windows_x64.exe -Algorithm SHA256
.\package\BOM_Manager_版本_日期时间_windows_x64.exe
```

EXE优先使用可写同目录配置；安装目录不可写时回退`%LOCALAPPDATA%\BOM管理系统`。单实例使用Windows文件锁和Qt本地通信；无需管理员身份运行。发行EXE暂未配置代码签名证书，下载文件可能触发Windows SmartScreen/杀毒软件信誉提示，不能保证所有设备均无提示双击启动，不应关闭系统防护规避。

### CI及目标系统验证状态

`.github/workflows/build-desktop.yml`提供Ubuntu24.04与Windows Server2022构建任务，可在GitHub Actions手动触发，或推送`v*`标签触发。运行结束下载各job的artifact包和测试报告；workflow本身不发布Release、不自动push源码。Windows Server构建自检不能替代Windows10/11的人工桌面验证。

0.5.0原始开发主机为deepin；2026-10-10已迁移到Windows10 x64并初始化原生构建环境。各轮实际测试与产物以test_reports、package及CODEX_MEMORY为准；不能把新增脚本/工作流误认为已经完成所有目标系统验收。

发布前在deepin25、Ubuntu24.04、Windows10、Windows11逐项确认：新用户无Python环境双击、中文/空格安装路径、只读安装目录回退、首次新建/选择数据库、重复启动激活、Excel导入导出、共享BOM保存刷新、退出重开及关于中的版本/提交匹配。验收记录保存test_reports，不提交业务数据库。

## 11. Windows本机开发入口

安装Git for Windows及64位Python 3.12后，在项目根目录用PowerShell执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/windows.ps1 init
powershell -NoProfile -ExecutionPolicy Bypass -File tools/windows.ps1 run
powershell -NoProfile -ExecutionPolicy Bypass -File tools/windows.ps1 test
powershell -NoProfile -ExecutionPolicy Bypass -File tools/windows.ps1 build
# 编写本轮详细提交说明后执行，自动升补丁版、提交和打包：
powershell -NoProfile -ExecutionPolicy Bypass -File tools/windows.ps1 finish -MessageFile .tmp/change_message.txt
```

`init`复用或新建`.venv`，安装requirements、检查依赖，配置本仓库`.githooks`并执行全量测试。可用`-PythonPath C:\路径\python.exe`指定新建虚拟环境的解释器。脚本能发现默认目录中已安装但尚未出现在当前PATH的Git/Python；只调整本次调用的环境，不修改全局PATH，不启动监控，也不改变全局PowerShell执行策略。

`run`打开正常桌面软件，首次启动由用户新建或选择SQLite数据库。`build`手动生成EXE及SHA256，不升版、不提交；`finish`通过Git Bash调用既定的`tools/finish_ai_change.sh`并核对当前提交打包成功标记。Shell脚本和Git钩子由`.gitattributes`固定为LF，避免Windows检出CRLF导致无法执行。Git提交身份沿用现有配置。

Qt在Windows通过用户注册表保存设置，沙箱禁止写入时，展开状态和导出目录测试可能失败；按权限流程在沙箱外复核，不能跳过测试或将权限失败误判为业务缺陷。完整测试会写入测试用的Qt偏好，建议在专用测试账户执行；发布自检数据库及Excel使用临时目录。

本机暂未配置WSL/Linux；用户已明确本轮优先完成Windows环境与EXE。AppImage需另行在Linux x86_64构建并验证SHA256，不应将Windows EXE当作AppImage。

## Deepin 长路径直接启动修复（不使用快捷方式）

Deepin 25 的 dde-application-manager 1.2.59 将完整可执行路径转换为 systemd 服务名，长中文共享路径可能超过 255 字节。失败发生在 AppImage 执行前，不能仅通过重打包 Python 软件修复。此前的桌面入口方案已撤回，安装脚本已删除；不创建桌面快捷方式或 MIME 关联。

`tools/patches/deepin-am-1.2.59-long-path.patch` 修复系统启动逻辑：过长的服务标识使用 SHA256 摘要，实际程序路径、参数和工作目录保持不变；同时将 systemd 请求错误返回给文件管理器，避免静默失败。补丁对应上游 LGPL-3.0-or-later 项目 https://github.com/linuxdeepin/dde-application-manager 的 1.2.59 标签。

可复现编译（仅构建，不自动安装/重启系统服务）：

```bash
sudo apt-get install --no-install-recommends cmake g++ libsystemd-dev qt6-base-dev libdtk6core-dev libdtkcommon-dev treeland-protocols qt6-wayland-dev qt6-base-private-dev qt6-wayland-private-dev
./tools/build_deepin_launch_fix.sh
```

源码归档有 SHA256 校验，源码及编译输出放在 `.tmp/deepin-launch-fix/`。本机通过用户级服务覆盖启用修复：可执行文件 `~/.local/lib/bom-manager/deepin/dde-application-manager-1.2.59`，配置 `~/.config/systemd/user/org.desktopspec.ApplicationManager1.service.d/90-bom-long-path.conf`。不替换 `/usr/bin/dde-application-manager`。这是本机桌面兼容补丁，不随 AppImage 在其他电脑上自动生效。系统启动管理器升级后应撤销此覆盖，再检查新版是否已修复，避免长期覆盖发行版更新。

撤销补丁、恢复发行版程序：

```bash
rm ~/.config/systemd/user/org.desktopspec.ApplicationManager1.service.d/90-bom-long-path.conf
systemctl --user daemon-reload
systemctl --user restart org.desktopspec.ApplicationManager1.service
```

验证原生启动接口（测试长中文路径、临界长度、短路径、systemd 错误传播；只使用临时数据库）：

```bash
python3 tools/verify_deepin_launch.py package/BOM_Manager_版本_日期时间.AppImage
```

结果记录在 `test_reports/deepin_direct_launch.json`。接口自检不能替代文件管理器实际双击验收。文件管理器的“是否运行”安全确认仍由桌面环境控制，补丁不关闭此确认。

### SMB 数据库限制

共享目录能写 config.ini 不代表支持 SQLite 字节范围锁。`smb://` 本身也不是 SQLite 文件路径。出现 `database is locked` 时，软件说明占用/共享锁原因并将下一次新建默认转到本地用户数据目录。使用共享数据库前仍需验证挂载写权限及锁支持；不关闭 SQLite 锁、不擅自修改共享挂载。只读目录下软件会提示实际使用的本地配置位置。


## 可迁移的配置路径

```ini
[database]
driver = sqlite
path = 数据库/bom.db
last_import_dir = 导入资料
```

路径相对于 **config.ini所在目录**，与启动时工作目录无关。默认数据库为`bom.db`；父级目录使用`../`。读取兼容Windows反斜杠路径，保存统一为`/`。中文、空格和`%`均按文件名原样处理。复制配置和数据库时应保留目录相对位置；已有本机绝对路径会自动转换，异系统旧盘符或挂载路径不会被猜测为同名文件。

Windows跨盘符/不同UNC共享根目录没有相对路径，选择数据库时会提示调整位置，建议数据库与config.ini同目录。跨盘符的上次导入目录不持久保存，下一次回到桌面选择。相对路径并不能自动映射不同机器上任意外部挂载点，也不改变SQLite共享文件锁要求。此轮在Linux执行Windows路径语义测试；真实Windows GUI验收需在Windows上进行。


## 采购BOM导出

SKU右键菜单或BOM编辑工具栏选择“采购BOM导出”。统计根SKU全部下阶物料（包含中间组件，不包含根SKU），数量逐层相乘后按物料编码及版本汇总；不同版本分开统计，替代料单列展示，不增加采购总量。表格包含物料等级、M/P及动态替代料列，格式沿用BOM导出。编辑窗口有未保存内容或外部更新待确认时，需保存后再导出。


物料导入模板包含可选的“物料等级”和“M/P”列。新建物料未映射这两项时默认等级为空、M/P为M；覆盖已有物料时未映射字段保留原值。已映射M/P支持m/p自动转换为M/P，其他值会明确报错。


BOM导入遇到已有子BOM不一致时，会列出系统与导入结构差异，可停止、保留系统子BOM或采用新导入子BOM。继续后先进入编辑缓存，检查并保存后才更新数据库及共享该结构的其他SKU；关闭差异窗口视为停止导入。


物料和BOM导入会分别记忆已确认的表头映射，保存在config.ini的`[import_mappings]`中。按源列名恢复，列重排不影响；新文件缺少对应列则显示“未映射”。BOM替代料映射组和可选字段的未映射选择也会保留，取消不会改写历史映射。


### 窗口布局恢复

窗口尺寸和位置自动记录在 `config.ini` 的 `[window_geometry]` 中。若需恢复默认布局，将配置改为：

```ini
[ui]
reset_window_geometry = true
```

开启后每次启动清除原窗口布局，使用默认尺寸和位置；恢复正常记忆时改回 `false`（默认值）。此开关不重置数据库、BOM展开状态或SKU列勾选。
SKU清单与物料库分别支持 `Ctrl+N` 新建SKU、新建物料，仅在当前活动窗口生效。

物料库及BOM编辑窗口支持 `Ctrl+F`，打开当前窗口对应的物料查找窗口；已打开的查找窗口直接复用。


### SKU历史版本

SKU清单的“版本号”是BOM历史版本，与物料编码中的SKU版本不同。现有和新建SKU默认历史版本100；右键“复制BOM”生成编号递增的独立历史版本，结构、数量、位置、备注和替代料完整复制。修改或删除某个历史版本不影响其他历史版本；物料库基础信息仍统一维护。若源窗口有未保存内容，先保存再复制。菜单栏“筛选”可按版本等字段筛选SKU。

首次升级旧数据库会自动在数据库旁生成 `.pre-mirrors-时间戳.db` 备份。历史版本库需使用支持历史版本的新程序读写；如需回退旧程序，请使用迁移前备份。新变更日志按当前电脑本地时间记录，秒后两位；旧UTC日志首次升级时转换，后续不重复转换。

BOM对比支持通过“载入其他BOM”选择 .xlsx/.xls，选择工作表并映射字段，仅在内存中比较，不导入物料库。外部文件没有ROOT声明时，只有唯一缺失父项可作为推断根节点；建议提供完整ROOT行以显示根物料名称。


### 旧历史版本数据库迁移为公共子BOM

仅SKU自身的直接下阶关系保留历史版本差异，普通物料子BOM统一共享。首次打开旧库时，若普通物料的公共结构与历史版本结构不同，程序会要求逐项选择保留来源，提供子项和属性预览；取消不会迁移。确认后先在数据库旁保存 `.pre-shared-bom-时间.db` 备份，再以事务迁移，并归档所有候选结构。迁移后的数据库请使用新版软件打开；需要回到旧版时请使用迁移前备份。

## 整树历史版本存储升级

首次打开旧数据库时，程序先在数据库旁生成 `.pre-whole-tree-时间.db` 备份，再将每个 SKU 历史版本的完整 BOM 树转为独立存储。需要数据库目录可写并有足够备份空间。当前可读的历史结构全部保留；以前共享编辑已覆盖的内容只能从旧备份恢复。

非 SKU 父项的直接子料基础编码集合发生变化且还被其他 SKU 或其他历史版本引用时，保存需要用户选择父项新版本；仅当前历史版本引用时可直接保存；仅子料版本改变不要求父项升版。**SKU版本始终手动控制，不受下阶变化限制。** 物料库保留历史物料，并标注是否被最新历史版本使用。

## 公共子BOM与最新历史版本同步

新增、替换和版本更新从公共物料目录读取最新子BOM。保存最新历史版本时，如果子BOM被其他SKU最新历史版本使用，会列出变化和受影响BOM供勾选；全部勾选同步，未全部勾选需要父物料升版，未勾选的BOM保留原版本。历史历史版本不参与自动同步。

已有业务数据的数据库首次启用此模式会先创建 `.pre-latest-catalog-时间.db` 备份，再按最近保存的最新历史版本统一现有公共结构。全新空库只初始化结构，不创建此备份；首次新建及重新打开后，数据库目录只保留所选数据库文件。删除分支自动清理当前历史版本的不可达结构与缓存；物料主资料和其他历史数据保留。SQLite空闲页复用，轻量索引统计维护不等同于文件体积立即缩小。

## 孤立BOM自动维护

打开数据库时检查所有SKU及历史历史版本的可达关系，清理真正孤立的结构和缓存，保留物料资料及历史记录。清理前生成 `.pre-orphan-cleanup-时间.db` 备份；实际删除结构后尝试VACUUM缩小主数据库文件。备份本身保留并占用额外空间，维护结果存储在 `app_metadata.last_orphan_cleanup`。无孤立数据时不重复压缩。

## Windows签名发布与SmartScreen

“Windows已保护你的电脑 / 无法识别的应用”属于SmartScreen信誉提示。数字签名验证发布者身份和文件完整性，但新文件仍可能因信誉不足触发提醒，不能承诺签名后立即在所有Windows电脑无提示。微软说明与发行选择见[SmartScreen应用信誉](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)。本项目目前没有受信任代码签名证书，本轮输出为未签名包。

Windows构建现在嵌入产品名称及版本资源，并支持从Windows证书存储区精确选取证书，通过SDK的SignTool完成SHA256签名、RFC3161时间戳及Authenticode信任链验证，之后执行包内自检，最后计算签名后的SHA256。配置不完整、签名/时间戳/验证失败或自检失败时中止，不能回退为未签名的成功发布。

取得受信任的代码签名证书（私钥由证书提供方/硬件令牌保管，证书可通过Windows存储区使用）并安装Windows SDK的SignTool后，在PowerShell中配置：

```powershell
$env:BOM_SIGN_CERT_SHA1 = '证书的40位十六进制指纹'
$env:BOM_SIGN_TIMESTAMP_URL = 'https://证书提供方的RFC3161时间戳地址'
$env:BOM_REQUIRE_SIGNED = '1'
# 默认CurrentUser\My；证书在LocalMachine\My时才设置：
# $env:BOM_SIGN_MACHINE_STORE = '1'
# SignTool不在PATH或标准Windows SDK目录时指定完整路径：
# $env:BOM_SIGNTOOL = 'C:\路径\signtool.exe'
powershell -NoProfile -ExecutionPolicy Bypass -File tools/windows.ps1 build
```

指纹中的SHA1仅用于选择证书，实际文件签名和时间戳摘要均为SHA256。不要在Git、配置文件或聊天中保存私钥及密码。`build`和`finish`使用相同环境变量；CI需由组织另行配置受保护的签名凭据及SDK，当前GitHub工作流不会自动获得证书。

未配置签名时允许本地开发构建，控制台输出`UNSIGNED`，`test_reports/<包名>_signing.json`明确记录`unsigned`；已配置并验证成功时记录`verified`、证书指纹和最终SHA256。正式要求签名时设置`BOM_REQUIRE_SIGNED=1`，缺少证书即在构建前拒绝。自签证书和版本资源不能替代受信任签名，也不会用于关闭SmartScreen、修改防病毒策略或移除下载来源标记。

后续需实际接入证书完成签名构建，并从真实下载渠道在干净目标Windows环境验收首次启动；受SmartScreen信誉影响仍可能有提示。若要求广泛分发时尽量避免这类首次下载警告，可另行评估Microsoft Store分发，账号及审核发布不属于本轮已完成事项。

Windows测试入口按`tests/test_*.py`逐文件启用独立Python/Qt进程，避免整套测试的残留窗口状态影响后续用例；保留全部用例、原有性能阈值和完整日志。各文件经tools/run_test_module.py执行，在Python退出前显式释放残留Qt窗口和QApplication，清理失败仍判失败。每个文件超时180秒或进程异常退出均记为失败；`TEST_STEPS`包含需求审计，不是业务用例数。

“无法成功完成操作，因为文件包含病毒或潜在的垃圾软件”是防病毒拦截提示，与SmartScreen的“无法识别的应用”不同。即使第二次可打开，也不足以确认第一次是误报；需要原始文件、SHA256及保护历史中的威胁名称核对。可对原文件执行一次Defender自定义扫描并保留报告，不通过改名重打包、关闭实时防护或添加排除项处理。确认疑似误报后，使用[微软开发者文件提交入口](https://www.microsoft.com/en-us/wdsi/filesubmission)申请复核；需用户确认后才上传文件。签名不能替代防病毒检测。


### 多项目管理

- **项目 → 新增项目**：填写项目代码、名称等资料，再指定新数据库位置和名称；不会覆盖同名文件。取消数据库选择时保留项目资料草稿。
- **项目 → 导入项目**：选择旧版本的config.ini，复制项目信息及导入设置到当前config，并接管其数据库。导入成功后无需继续保留旧config；数据库文件仍需保留。
- **文件 → 导入项目数据库**：直接选择已有SQLite项目数据库，校验成功后加入历史项目并打开。
- **项目 → 打开历史项目**：按“项目代码 项目名称”选择项目。数据库移动后可重新指定路径；右键删除仅移除历史记录，不删除文件。
- 当前项目下“修改项目信息”同步更新历史列表。切换时未保存BOM仍会询问保存/放弃/取消。
- 多项目清单保存在软件当前使用的config.ini中，数据库路径使用相对路径；迁移电脑时应一起复制config和数据库并保持目录关系。导入旧配置后，不要同时使用旧软件编辑同一数据库。
