"""BOM管理系统帮助中心：快捷键、页面说明、操作指引、技巧和问答。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QScrollArea, QTextBrowser, QFrame)
from ui.interactive_windows import QDialog

class HelpDialog(QDialog):
    """独立帮助窗口；截图来自当前运行中的实际页面。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('帮助 - BOM管理系统')
        self.resize(1050, 760)
        self.setMinimumSize(760, 540)
        layout = QVBoxLayout(self)
        intro = QLabel('BOM管理系统帮助中心  ·  内容会根据当前打开的页面提供实际截图')
        intro.setStyleSheet('font-size:16px;font-weight:bold;padding:6px 2px;')
        layout.addWidget(intro)
        tabs = QTabWidget(); layout.addWidget(tabs)
        tabs.addTab(self._text_page(self._shortcuts()), '快捷键')
        tabs.addTab(self._feature_page(), '页面与功能')
        tabs.addTab(self._guide_page(), '操作指引')
        tabs.addTab(self._tips_page(), '操作技巧')
        tabs.addTab(self._text_page(self._qa()), 'Q&A')

    def _text_page(self, html):
        area = QScrollArea(); area.setWidgetResizable(True)
        browser = QTextBrowser(); browser.setOpenExternalLinks(True); browser.setHtml(html)
        browser.setStyleSheet('QTextBrowser{font-size:14px;line-height:1.5;padding:12px;}')
        area.setWidget(browser); return area

    def _shortcuts(self):
        return '''<h2>快捷键</h2><p>快捷键只在对应窗口获得焦点时生效；输入框中优先保留文字输入行为。</p>
        <table cellspacing="8"><tr><th align="left">快捷键</th><th align="left">作用</th><th align="left">适用页面</th></tr>
        <tr><td><b>Ctrl+N</b></td><td>新建SKU或新建物料</td><td>SKU清单、物料库</td></tr>
        <tr><td><b>Ctrl+F</b></td><td>打开当前页面的物料查找</td><td>物料库、BOM编辑/浏览</td></tr>
        <tr><td><b>Ctrl+S</b></td><td>保存当前编辑内容</td><td>物料、SKU、BOM及各保存窗口</td></tr>
        <tr><td><b>Delete</b></td><td>删除当前选中的BOM物料，随后按回车确认</td><td>BOM编辑</td></tr>
        <tr><td><b>Ctrl/Shift + 鼠标点击</b></td><td>多选同级物料或SKU行</td><td>SKU清单、BOM树</td></tr>
        <tr><td><b>Enter</b></td><td>确认首个筛选候选项或确认当前对话框</td><td>物料选择、查找、导入映射</td></tr></table>
        <h3>窗口操作</h3><p>所有主要交互窗口均可独立移动、切换和置顶。关闭有未保存内容的窗口时，请选择保存并退出、不保存退出或取消。</p>'''

    def _feature_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(self._section('SKU清单窗口', '管理项目下全部SKU及其历史版本。可按编码、名称、版本号和修改时间排序；右键可打开/浏览BOM、导出BOM、导出采购BOM、锁定、复制历史版本和编辑变更描述。底部显示SKU与BOM数量，勾选“只显示最新BOM”可隐藏旧历史版本。', self._grab(self.parentWidget(), 'SKU清单实际界面')))
        layout.addWidget(self._section('物料库窗口', '维护物料基础信息、版本、单位、等级、制造商、MPN和M/P。支持导入、导出、筛选、查找、版本更新、物料反查、复制物料、编辑公共BOM结构以及按SKU显示用量。呆滞料和BOM状态会在表格中直接标识。', self._grab(getattr(self.parentWidget(), '_materials', None), '物料库实际界面')))
        layout.addWidget(self._section('BOM编辑/浏览窗口', '左侧树显示从根物料递归展开的BOM，右侧显示当前物料属性。数量、位置和备注可编辑；右键提供新增同级/子级、复制、剪切、粘贴、替换、版本更新、替代料、颜色和导出等操作。锁定的SKU以浏览模式打开。', self._grab(self._first_bom(), 'BOM窗口实际界面')))
        return self._scroll(page)

    def _guide_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        sections = [
          ('1. 打开项目', '首次打开或配置缺少当前项目时，在项目选择窗口选择项目；系统会校验SQLite数据库并加载SKU。项目菜单可新增项目、导入项目、切换历史项目或关闭当前项目。'),
          ('2. 新建物料和SKU', '在物料库按Ctrl+N新建物料，单位和M/P从下拉菜单选择；保存后列表自动刷新。回到SKU窗口按Ctrl+N，输入编码、版本号或名称筛选可用物料；已有BOM结构或已经是SKU的物料不能重复建立SKU。'),
          ('3. 编辑BOM', '双击SKU或右键选择编辑BOM。左键树节点查看属性，修改数量/位置/备注后点击保存。新增物料只能从树的右键菜单进入；系统检查重复、循环引用和父级共享影响。保存前新增为绿色、删除为红色删除线、属性修改为黄棕色；刷新导入其他BOM变更时显示深紫色。'),
          ('4. 导入与导出', '导入物料或BOM时先选择文件和Sheet，再将目标表头映射到需求表头；必填项带星号。映射成功后按进度条导入，结果窗口分别列出跳过和失败条目及原因。导出BOM、采购BOM、物料库和资料库会记住上次路径，并按要求格式化Excel。'),
          ('5. 历史版本与锁定', 'SKU历史版本用于保存同一SKU的独立BOM历史。复制BOM会增加历史版本号；锁定后只能浏览，其他BOM的联动修改会提示先解除锁定。')]
        for title,body in sections:
            layout.addWidget(self._section(title,body,None))
        layout.addWidget(self._section('操作流程截图', '下图为当前运行中的主窗口截图，实际操作时菜单和表格会根据项目数据变化。', self._grab(self.parentWidget(), '操作流程实际界面')))
        return self._scroll(page)

    def _tips_page(self):
        return self._text_page('''<h2>操作技巧</h2>
        <h3>快速定位</h3><p>在物料库或BOM窗口按<b>Ctrl+F</b>，输入编码、名称、规格、制造商或MPN；输入回车会选中首个候选项。物料反查结果双击后会定位到对应SKU及树节点。</p>
        <h3>批量处理</h3><p>SKU清单可用Ctrl/Shift多选，再右键批量打开、浏览、导出或锁定。BOM树可多选同级物料复制/剪切，粘贴时保留数量、位置、备注和替代料，并按原顺序插入。</p>
        <h3>安全编辑</h3><p>编辑过程中所有内容先进入缓存；刷新不会丢失未保存修改。保存前可通过颜色和删除线检查变化，关闭窗口时可取消退出继续编辑。父级共享物料发生子BOM变化时，系统会列出受影响SKU供确认。</p>
        <h3>主题与显示</h3><p>右上角太阳/月亮按钮切换主题。BOM树层级背景会自动适配浅色和深色模式，越靠近根节点对比度越高。窗口尺寸、导入导出路径和列显示选择会自动记忆。</p>
        <h3>故障排查</h3><p>如果数据库不存在或损坏，选择项目数据库重新定位；不要直接复制正在使用的数据库。AppImage在网络共享目录不可写时会把配置回退到用户目录，SQLite数据库建议放在支持文件锁的本地磁盘。</p>''')

    def _qa(self):
        return '''<h2>常见问题</h2><h3>Q：启动后SKU清单为空怎么办？</h3><p>A：检查项目菜单中的当前项目；没有当前项目时选择历史项目。若数据库路径失效，选择“指定数据库”重新关联，系统会先做完整性和结构校验。</p>
        <h3>Q：为什么BOM保存按钮不可用？</h3><p>A：没有未保存修改时保存按钮会禁用；受到其他BOM联动更新时先点击刷新，确认缓存内容后再保存。</p>
        <h3>Q：为什么物料不能加入BOM？</h3><p>A：可能是同一父级已有相同物料、会形成循环引用、物料被锁定或物料存在不允许嵌套的BOM结构。请查看弹窗列出的具体原因。</p>
        <h3>Q：导入表格提示映射失败？</h3><p>A：必填表头必须各自映射一次，空表头列会忽略；检查目标表头是否选择了正确Sheet，并确认没有重复映射。</p>
        <h3>Q：如何恢复误删的BOM物料？</h3><p>A：保存前右键删除线物料，选择“取消删除”；已经保存的删除需要从物料库重新新增到对应父级。</p>
        <h3>Q：如何获得帮助？</h3><p>A：保留软件版本号、项目名称、操作步骤和弹窗内容；同时查看关于窗口中的Git提交信息，便于定位对应版本。</p>'''

    def _first_bom(self):
        parent=self.parentWidget()
        return next(iter(getattr(parent,'_bom_windows',{}).values()),None) if parent else None

    def _grab(self, widget, title):
        if widget is None or not widget.isVisible(): return None
        pix=widget.grab()
        if pix.isNull(): return None
        label=QLabel(title);label.setAlignment(Qt.AlignCenter);label.setStyleSheet('font-weight:bold;padding:4px;')
        image=QLabel();image.setPixmap(pix.scaled(920,420,Qt.KeepAspectRatio,Qt.SmoothTransformation));image.setAlignment(Qt.AlignCenter)
        box=QFrame();l=QVBoxLayout(box);l.addWidget(label);l.addWidget(image);box.setFrameStyle(QFrame.StyledPanel|QFrame.Sunken);return box

    def _section(self,title,text,image):
        box=QFrame();l=QVBoxLayout(box);h=QLabel(title);h.setStyleSheet('font-size:16px;font-weight:bold;');l.addWidget(h)
        body=QLabel(text);body.setWordWrap(True);body.setTextInteractionFlags(Qt.TextSelectableByMouse);l.addWidget(body)
        if image:l.addWidget(image)
        box.setFrameStyle(QFrame.StyledPanel|QFrame.Sunken);return box

    def _scroll(self, widget):
        area=QScrollArea();area.setWidgetResizable(True);area.setWidget(widget);return area
