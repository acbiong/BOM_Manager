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


## 2026-10-12 撤回快捷方式，修复 Deepin 原生启动

此前短名 desktop 入口方案已按用户要求撤回；桌面和应用菜单的 bom-manager.desktop 均已清理，安装器删除。历史章节提及的快捷方式方案不再适用。

直接启动失败定位在 dde-application-manager 1.2.59：路径派生单元名称过长，以及 systemd 异步错误未返回。补丁在名称超过255字节时采用SHA256摘要，并返回systemd错误；原执行路径不变。使用相同上游版本构建，通过用户级90-bom-long-path.conf覆盖启用，不改系统原二进制、不使用MIME关联、不改变文件管理器安全确认。系统包升级后需要撤销/重新评估覆盖；其他电脑需要单独修复桌面环境，AppImage本身不会安装系统补丁。

复现构建：tools/build_deepin_launch_fix.sh；原生启动验证：tools/verify_deepin_launch.py；报告：test_reports/deepin_direct_launch.json。SMB写配置成功不等同SQLite锁支持，此次不声称共享数据库锁问题已解决。原共享目录0.5.2安装包复测时已不存在，改用本地更长中文路径进行回归，须区分接口自检与人工双击验收。

验证结果：原生executeCommand接口六项检查通过（长中文路径AppImage真实xcb窗口自检、短标识、255字节边界及超界、长Unicode标识、systemd错误返回）。报告test_reports/deepin_direct_launch.json。人工文件管理器双击验收尚未完成，不据此宣称共享目录双击已完全验收。


## 物料导入单位大小写归一化（2026-10-12）

物料Excel导入忽略单位大小写，按当前config.ini的materials.units标准写法保存；未配置时沿用内置默认单位。配置中同一单位存在多个大小写写法时，以首次出现的写法为准（默认m/M统一为m）。归一化在重复物料比较、覆盖提示与入库前执行，因此与现有标准单位仅大小写不同的相同物料自动跳过。未知单位仍失败，空单位仍明确报必填项缺失。不批量修改已有物料。

回归：tests/test_material_units.py新增默认大小写/空白、相同重复自动跳过/覆盖入库、自定义单位优先/无效及空单位三项测试；完整验证与发布记录由收尾脚本生成至test_reports。


## config.ini跨平台相对路径（2026-10-12）

数据库path及last_import_dir保存为相对config.ini所在目录的路径，统一`/`；默认bom.db。解析独立于工作目录，兼容反斜杠，支持中文/空格/百分号。旧本机绝对路径自动迁移；异系统绝对路径保留供数据库恢复流程提示，不尝试同名文件猜测。整套文件跨系统复制时须保持目录相对布局。

选择数据库先验证相对路径可表示并成功保存配置，再切换连接，失败关闭候选连接并保留旧连接。Windows跨盘符或UNC不同共享根无法表示相对路径，提示用户调整数据库位置；不可迁移的导入历史目录清除并回退桌面。该限制不是SQLite共享锁的修复。

tests/test_config_paths.py覆盖默认/绝对路径迁移、复制项目后打开正确数据库、Windows/POSIX/UNC语义和分隔符、非法/跨盘符/异系统路径、异系统旧配置不误选本地同名数据库。已有启动选择测试更新为验证相对保存；全量报告在test_reports。Windows路径语义在Linux验证，未宣称完成Windows GUI实机测试。


## 采购BOM导出（2026-10-12）

SKU窗口右键菜单、BOM编辑窗口工具栏新增“采购BOM导出”，入口及导出路径记忆遵循现有导出BOM功能。BOM编辑窗口未保存、收到外部更新、刷新后待保存及保存失败时禁用；保存成功后启用，避免导出编辑缓存。SKU窗口沿用原有导出BOM的已保存数据库导出逻辑。默认文件名“物料编码 SKU名称 采购BOM.xlsx”，物料编码直接拼接基础编码与版本。

用户已确认统计所有下阶物料，包含中间组件、不含根SKU。以根数量1递归展开，每条路径逐层相乘，同一物料版本跨路径累加，不同版本分别统计。使用Decimal完成乘算汇总，仅最终总量四舍五入到小数点后一位。替代料不作为额外采购数量。

列依次为：序号、物料编码、物料名称、规格、用量、单位、物料等级、M/P、制造商、MPN；按最大替代料数量动态增加替代料n物料编码、替代料n物料名称、替代料n规格、替代料n制造商、替代料nMPN；最后备注。替代料按身份去重、原备注去重换行合并；不同位置替代关系不同时，备注说明各位置适用的替代料（包含无替代料的位置）。

沿用BOM表格格式：黑色细边框、表头加粗、自适应列宽最大60字符、自动换行、冻结表头，用量一位小数；序号、用量、单位、物料等级、M/P居中。空BOM输出表头；物料BOM编辑窗口也可导出该物料的全部下阶采购清单。

验证：tests/test_purchase_export.py五项回归覆盖真实Excel读回、三层共享物料及版本隔离、Decimal累加后舍入、动态替代料/备注/格式/M/P、空BOM/非SKU根、窗口保存与联动刷新状态、SKU右键入口及取消。报告存放test_reports/purchase_export.txt，全量验证与版本提交打包由收尾脚本执行。


## 物料等级与M/P可选导入（2026-10-12）

物料导入统一字段定义，模板和表头映射均包含“物料等级”“M/P”，二者为可选字段，不参与必需表头校验。自动识别同名列；手动映射可明确选择未映射，不因Excel存在同名列而重新启用。新建未映射或映射单元格为空时，等级默认为空、M/P默认为M。覆盖已有物料时未映射字段不导入，保持原值；已映射空值使用默认值。

M/P去除两端空白并转大写，仅允许M/P；非法值在导入结果中明确说明失败，继续扫描其他行。物料等级及M/P共同参与重复物料比较、差异表展示及覆盖保存。导出模板两处入口共用相同表头定义，避免模板与导入字段不一致。

验证：tests/test_material_optional_import.py五项回归覆盖自动/自定义映射、未映射/缺列/空单元格默认值、覆盖保留未映射字段、M/P单独变化识别及差异展示、非法M/P和错误映射、两个模板导出入口。test_reports/material_optional_import.txt记录专项测试，全量测试及新版本打包由收尾脚本执行。


## BOM导入子结构差异确认（2026-10-12）

BOM文件完成全表扫描和基础合法性校验后，按父物料身份比较所有明确提供子项且系统也已有子项的BOM，包含导入根物料。按子物料编码及版本比较子项增删、数量、位置、备注及替代关系；顺序变化不单独视为结构冲突。未提供下阶定义的物料延用已有系统结构。

发现不一致弹出可滚动的五列表：父项物料、子项物料、不一致项、系统子BOM、新导入子BOM。一次列全差异，用户选择“停止导入”“继续导入并以系统子BOM为准”“继续导入并以新导入子BOM为准”，窗口关闭默认停止。无差异不弹窗。

以系统为准保留冲突物料的完整系统子树（包括备注、替代关系和叶子定义），排除被替换分支留下的孤立导入定义；以导入为准采用文件中明确提供的子项定义。由于下阶定义由同一父物料共享，同一物料在不同位置统一处理。选择完成后再次检查最终组合结构的循环引用；非法组合禁止导入。

UI两种继续方案均只更新编辑缓存，不写库，不发送联动刷新；点击保存后由既有保存机制写库并通知所有受影响SKU。停止/校验失败保留原缓存及数据库。直接调用服务存在差异且未提供conflict_resolver时默认停止，不能静默覆盖。

验证：tests/test_bom_import_conflicts.py覆盖一致免提示、差异列表、停止不写、系统完整子树及孤立数据排除、导入缓存及保存后共享SKU通知、关闭弹窗、替代料/备注、组合循环、导入根冲突；既有BOM导入测试中的主动替换场景更新为显式选择新导入结构。专项及全量报告存放test_reports。


## 导入映射记忆（2026-10-12）

config.ini的import_mappings节分别以materials和bom保存已确认的需求字段→源列名JSON，随配置跨平台携带。映射通过校验并点击确定后保存；取消或校验失败不覆盖历史。无历史时沿用同名表头自动匹配。

物料两处导入入口优先使用记忆映射，避免标准同名列覆盖用户选择；历史源列不存在时进入映射对话框，该项恢复未映射，不能按位置或自动同名猜测。其他仍存在的列保留选择，主动未映射的可选字段也保持未映射。

BOM窗口自动恢复基本字段及动态替代料映射组（含非连续编号），源列缺失时置空让用户补选或删除该组；组的删除在确认后更新记忆。物料与BOM记录隔离，取消不写入，损坏JSON忽略并恢复初始匹配。

验证：tests/test_import_mapping_memory.py覆盖重新实例化/列重排恢复、缺列不回退同名、取消/校验失败不保存、BOM替代料组恢复删除与类型隔离、两个物料UI入口优先记忆、损坏配置容错。专项报告test_reports/import_mapping_memory.txt，全量报告和发布由收尾流程生成。


## BOM导入目录记忆修复（2026-10-12）

BOM文件选择器不再每次传入空初始路径。选择文件后立即将其目录写入config.ini的database.last_bom_import_dir，相对配置目录保存并与物料导入路径独立；即使后续映射取消/文件不合法也保留选定目录，取消文件选择不覆盖记录。重启及其他BOM窗口均读取同一记录；目录暂不可用回退桌面，保留历史以便重新挂载后恢复。

支持file://解码和smb://映射至已挂载CIFS/GVFS本机路径，Windows使用UNC；不将SMB地址直接交给openpyxl或Path作为普通文件名。不自动挂载共享、不写共享测试数据，找不到挂载/文件时明确提示。

本机只读验证用户指定MFH1目录：smb://192.168.77.143/!项目文件夹/Mobius Foot（脚踝）/02 研发设计资料/90BOM/MFH1正确解析为/media/biong/smbmounts下对应目录，is_dir=True。未读取/导入业务BOM。tests/test_bom_import_paths.py覆盖相对路径持久化、file URI、SMB挂载映射、目录失效/恢复记录、未挂载不覆盖历史、真实UI第二次文件选择初始路径。测试报告test_reports/bom_import_paths.txt。


## SKU排序、悬停反馈与必选映射标记（2026-10-12）

SKU窗口支持点击SKU编码、SKU名称、修改日期时间表头升降序切换并显示排序箭头。刷新后保留当前窗口排序状态，按完整行排序确保打开按钮及隐藏SKU ID对应一致；其他列不响应排序，表格禁止直接编辑。

应用级主题样式为启用的QPushButton、QToolButton添加悬停和按下颜色，并为菜单栏/菜单提供选择高亮，浅色和深色主题分别配置对比色。禁用按钮不使用可点击悬停样式。

物料/BOM表头映射中所有必选字段显示“字段名 *”，物料等级和M/P等可选字段不加星号；BOM动态替代料编码/版本号也标注。星号仅作用于界面，不修改真实映射键、Excel表头或已保存映射。提示栏说明星号含义。

tests/test_sku_sort_hover_required.py覆盖三列双向排序、刷新保持、排序后按钮身份、非排序列、映射星号与数据键、浅/深主题鼠标悬停实际图像变化；专项报告test_reports/sku_sort_hover_required.txt。全量测试、提交与打包走统一收尾流程。


## 删除仍被引用的SKU（2026-10-12）

删除SKU时在事务内检查该物料是否作为任意BOM的子项或替代料被引用，不限于其他SKU根。若被引用，仅移除SKU身份及该SKU自身历史，保留物料、根BOM和子孙结构、数量/位置/备注、替代关系、has_bom及共享BOM历史。SKU历史重建边界继续保留，避免重新创建SKU继承旧SKU历史；不清理共享BOM日志归属。仅发送sku_changed，不发虚假的bom_changed。

未被引用时沿用原删除BOM及历史清理逻辑。UI确认提示随引用情况明确显示仅移除标记或删除SKU及BOM。tests/test_delete_referenced_sku.py覆盖主料引用和仅替代料引用、非SKU父物料、结构与替代关系/日志原样保留、提示文案、事件类型、重开数据库持久性。原无引用清理测试继续纳入全量回归。
