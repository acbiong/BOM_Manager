# Codex项目记忆与交接记录

更新日期：2026-10-10。此文件记录可供其他开发者和新Codex会话使用的项目事实、用户约定与验证方法，不保存内部推理、账号凭证或完整聊天历史。每轮先检查真实文件，本文不能替代代码及用户最新要求。

## 接手时先做什么

1. 阅读README、本文、软件开发规格书及需求追踪审计报告。
2. 检查`git status --short`、`cat VERSION`、`git log -3 --oneline`，保留用户已有改动。
3. 使用Python 3.12+虚拟环境，确认requirements依赖及AppImage工具；项目可放在任意路径。
4. 修改前定位对应服务/UI及已有回归，完成后运行收尾流程，不止停留在方案。

## 项目与发布状态

- 软件名称：BOM管理系统；仓库：https://github.com/acbiong/BOM_Manager。
- Python/PyQt5桌面程序、SQLite本地数据库；用户已明确替换MySQL，不要恢复服务器数据库方案。
- 本轮开始基线为0.0.89，关于窗口功能提交`4c74f7e`，177项自动化测试通过。本文随之后的收尾提交发布；**当前实际版本查VERSION，提交查git log，产物查package**，不要把基线数字当成最新版本。
- 本轮补齐迁移README及此文件，并修正Pillow依赖缺漏、测试硬编码路径、全新克隆无package目录的问题。
- 原始需求曾位于旧机器桌面emmx和编程指南，这些外部文件不在仓库；跨机以docs中的规格与追踪为交接依据，需要重新审查原图时须取得原文件，不能声称已完整读取未携带的附件。

## 用户明确的工作约定

- 任意代码修改后自动执行`tools/finish_ai_change.sh --message-file .tmp/change_message.txt`，完成测试、审计、编译、补丁升版、Git提交及AppImage打包。
- 不使用常驻监控进程；不要启动watch_source.sh。自动化是AI完成编程后的收尾流程。
- 提交信息必须写实际类型、变更点、验证内容，禁止泛化“AI自动完成代码更新、测试和打包”。不自动push。
- 测试报告放test_reports且不提交；编译临时文件放.tmp；最终包在package；脚本放tools。保留忽略规则。
- 更新规格、追踪审计和相关回归；不要未经检查覆盖用户数据库。数据库选择已有文件时选用并校验，不覆盖。
- 最终中文反馈版本、主要行为、测试结果、Git提交及AppImage绝对路径链接。离屏Qt不等于真实双击/跨机验收，不虚构人工验证。
- 仅文档调整按实际影响验证；若同时修改依赖、脚本或测试，也执行完整收尾。钩子配置不随clone自动启用，详见README。

## 代码地图

- src/main.py：启动、单实例、数据库恢复、源码/冻结配置路径。
- src/database/database.py：SQLite结构、迁移与事务。
- src/services/services.py：物料、SKU、共享BOM关系、Excel导入导出、版本及变更日志。
- src/ui/main_window.py：SKU、物料库、BOM编辑、映射/反查等窗口。
- src/ui/material_search.py：非模态物料组合查找与结果定位。
- src/ui/material_clipboard.py：同库跨窗口物料身份剪贴板。
- src/ui/table_layout.py：默认列宽与宽窗口比例扩展。
- src/ui/about_dialog.py、src/infrastructure/build_info.py：关于窗口与冻结构建信息。
- src/infrastructure/events.py：窗口变更事件；single_instance.py：QLocalServer单实例。
- src/config/config_service.py：INI默认配置与可配置单位；src/version.py、VERSION：版本读取与升版。
- tools/run_tests.sh：137条追踪编号审计、unittest、源码编译并保存报告；通过不代表所有业务已被形式化证明。
- tools/finish_ai_change.sh、.githooks/post-commit、tools/build_appimage.sh：当前收尾/构建链。

## 核心业务约束与近期功能

- material_bom_items按父物料/子物料存共享关系，bom(root)递归展开，不能把SKU下的每份子BOM复制成互不关联数据。
- BOM编辑先进缓存，保存才写库；数量一位小数。切换节点、外部刷新不得丢本地修改。关闭脏窗口提供保存、不保存、取消。
- 同SKU仅一个BOM窗口，物料库也复用；反查定位需匹配父项和物料ID，展开祖先并选中，不能用旧行号直接定位。
- 共享BOM保存向关联窗口发送通知并更新相关SKU时间。通知后及刷新后禁用导出，只有保存成功恢复；不相关SKU不更新时间。
- 新增绿色、删除红字删除线、修改黄棕字且改动字段加粗；外部刷新深紫背景和临时备注不入库；移动淡粉色背景，保存清除。
- 新增/粘贴禁止同父级重复及循环引用。剪贴板复制物料身份，粘贴数量1.0、位置备注空，自动展开已保存子BOM，不复制源关系未保存属性。跨数据库剪贴板无效。
- 上下移动限同父级，首尾禁用；共享父项副本同步排序，刷新保留本地排序，纯排序不写变更明细。
- 呆滞料判断包含主料、替代料、SKU引用；仅自身有子BOM而无外部引用的非SKU仍为呆滞料。
- 物料版本更新按父BOM选择引用：全选直接改版本，部分选保留旧版本并创建新版本。SKU在物料库中的版本更新入口禁用。
- Excel导入支持sheet选择、两行表头映射、替代料映射、ROOT校验、错误汇总。BOM导入只用于无下阶节点，先进缓存；完全相同物料自动跳过。
- BOM导出含SKU根行：序号1、层级0、父项编码/版本ROOT；子孙1.1/1.1.1；工作表用SKU名称并处理Excel31字符及非法字符。最大列宽60、黑框、换行、替代料列；资料库变更页只含物料日志。
- 查找窗口五字段AND子串匹配，结果六列含制造商和MPN；双击仅定位物料库不关闭查找窗，必要时解除隐藏目标的筛选。
- 通用UI默认列宽5至25中文字符，宽窗口按比例填满，窄窗口显示横向滚动，固定勾选列保留。
- SKU底栏统计、Powered by Biong & BrainCo Inc.及版本同一行；标题为项目代码+项目名称+BOM管理系统；关于窗口读取随包提交信息。

## 构建和迁移注意

- 0.5.0起Linux采用onedir放入AppDir，外部仍为单个AppImage；Windows原生构建onefile EXE。程序资源经_MEIPASS读取。
- build_info.json在post-commit构建阶段生成，避免显示上次提交；VERSION也随包嵌入。不要把生成的JSON提交到源码。
- AppImage runtime有默认解压分支补丁；上游二进制更新可能不兼容，脚本会拒绝不识别的runtime，禁止盲目去掉校验。
- AppImage配置优先可写的软件目录，否则用户配置目录；不要写只读挂载目录。业务数据库/INI需单独备份迁移。
- 旧build.sh/release.sh只做独立ELF，不是当前发布流程。Git提交成功后必须核对实际AppImage及sha256，钩子可能因工具缺失跳过。
- 运行完整测试需要本地socket权限；沙箱导致QLocalServer失败应按权限流程处理，不能当作业务缺陷或跳过断言。
- 新电脑不带旧Codex会话/认证；从此文档交接新会话，账户自行登录。官方安装/启动来源见README。

## 每轮完成前与未完成项记录

- 查看diff，完成相关测试，更新规格/审计及本文重大事实，写详细提交说明，再执行收尾。
- 核对VERSION、git log、git status、package产物和SHA256；失败要如实报告，并区分已提交但打包失败。
- 当前无被确认但尚未实现的用户功能请求；目标新电脑上的全新系统安装、图形双击和人工业务验收仍需在该电脑执行。不要把本机隔离路径测试宣称为真实新机器验证。


## 0.5.0平台改造交接

- Windows单实例改用msvcrt非阻塞文件锁；Linux继续fcntl。Windows配置优先可写exe目录，回退LOCALAPPDATA，错误日志采用系统临时目录。
- tools/build_windows.py为Windows x64原生EXE构建；tools/run_tests.py为跨平台测试入口；Linux增加ELF/glibc<=2.38检查和发布自检。
- 新增.github/workflows/build-desktop.yml，可手动/标签触发Ubuntu24.04与Windows Server2022构建。未自动push或远程执行工作流。
- 收尾支持BOM_RELEASE_VERSION指定准确版本，本轮请求0.5.0；默认仍补丁递增。
- 当前机器没有Windows原生构建环境，Windows EXE生成及Windows10/11、Ubuntu桌面验收是明确待完成事项，不要宣称已经验证。实际Linux本轮验证看test_reports和最终产物。
- 0.5.0收尾进一步使用.tmp/package_success_commit匹配HEAD确认打包成功；post-commit失败不影响git commit返回码，必须额外检查标记。Linux ldd审计模拟bootloader的_internal库搜索路径。

## Windows10本机初始化交接（2026-10-10）

- 本轮实际机器为Windows10 x64 build19045，工作目录D:\git\BOM_Manager；接手基线c905eaf、0.5.0，工作区干净。此前“本机为deepin/无Windows构建环境”仅描述旧机器。
- 已有Python3.12.10 x64和Git for Windows，复用.venv；核验PyQt5 5.15.11、Qt5 5.15.2、openpyxl3.1.5、PyInstaller6.22.3、Pillow12.3.0，pip check通过。Git用户身份沿用本机配置，未push。
- tools/windows.ps1提供init/run/test/build/finish；README第11节有完整命令。脚本定位默认安装目录中的Git/Python，只临时配置环境，init启用本仓库.githooks。没有启动watch_source.sh或其他常驻监控。
- .gitattributes固定Shell/钩子为LF。tools/python_env.sh让测试、收尾、Windows钩子使用同一虚拟环境，避开Windows python3商店别名；run_tests.sh转交跨平台run_tests.py。
- 单实例激活测试现用有限Qt事件等待，Windows命名管道连接成功不代表一次processEvents已完成回调；六项专项通过。Qt展开状态/导出路径在沙箱内因用户注册表权限失败，获准沙箱外运行后179项测试、137/137追踪和编译均通过（test_reports/test_20261010_183317.txt）。不可跳过失败断言。
- 用户明确本轮先完成Windows环境与EXE，**不安装WSL/Linux**；AppImage构建和SHA256核验留待Linux环境。Windows11、Ubuntu/deepin跨机验收及人工完整业务验收仍待执行。
- 最终版本/提交以VERSION和git log为准；收尾调用tools/finish_ai_change.sh，报告放test_reports、EXE及SHA256放package，必须核对.tmp/package_success_commit与HEAD、EXE自检中的版本/提交信息。Windows打包自检使用临时SQLite/Excel，不覆盖业务数据库；自动化窗口自检不等同人工双击验收。
- 正式收尾前已原生构建0.5.0验证包BOM_Manager_0.5.0_20261010_183439_windows_x64.exe；SHA256复算一致，自检passed=true、qt_platform=windows，七类检查通过。其元数据为收尾前c905eaf，仅作环境验证；正式交付使用收尾后新版本/新提交的包。证据：test_reports/windows_build_initial.txt及同名_smoke.json。

## 2026-10-12共享路径问题

- 用户共享路径挂载经/proc/mounts确认cifs ro；程序不能在其中写配置/数据库，不要擅自改挂载或声称修复为可写。
- Deepin直接双击超长中文路径会生成超过255字节systemd单元名，在AppImage启动前失败；提供tools/install_desktop_launcher.py短名入口绕过，原始长路径文件仍受桌面管理器限制。
- 只读配置回退需显示实际位置；新建数据库对话框回退可写目录，使用命名文件探测兼容SMB。
- 后续用户确认database is locked发生于smb://目标，config可写并不表示SQLite锁支持。新增本地新建恢复；直接长路径双击仍是桌面管理器限制，MIME关联试验未通过已撤回。不要再次将短入口验收等同于原文件直接双击。
- runtime旧的JNE->JE补丁在环境变量存在时会逆向走FUSE，已改NOP+JMP始终解压；须分别验证变量存在/不存在。
