"""BOM管理系统帮助中心：快捷键、页面说明、操作指引、技巧和问答。"""
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QScrollArea, QTextBrowser, QFrame, QPushButton, QListWidget, QSplitter)
from ui.interactive_windows import QDialog

class HelpDialog(QDialog):
    """独立帮助窗口；截图来自编译阶段的实际页面。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('帮助 - BOM管理系统')
        self.resize(1050, 760)
        self.setMinimumSize(760, 540)
        layout = QVBoxLayout(self)
        intro = QLabel('BOM管理系统帮助中心  ·  随软件内置的静态图文教程，无需打开示例项目')
        intro.setStyleSheet('font-size:16px;font-weight:bold;padding:6px 2px;')
        layout.addWidget(intro)
        tabs = QTabWidget(); layout.addWidget(tabs)
        tabs.addTab(self._text_page(self._shortcuts()), '快捷键')
        tabs.addTab(self._feature_page(), '页面与功能')
        tabs.addTab(self._guide_page(), '操作指引')
        tabs.addTab(self._tips_page(), '操作技巧')
        from ui.help_rules import RULES_HTML
        tabs.addTab(self._text_page(RULES_HTML), '规则与条件')
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
        <tr><td><b>Ctrl+Z / Ctrl+Y</b></td><td>撤销 / 恢复最近的BOM草稿操作</td><td>BOM编辑，输入框内同样生效</td></tr>
        <tr><td><b>Delete</b></td><td>删除当前选中的BOM物料，随后按回车确认</td><td>BOM编辑</td></tr>
        <tr><td><b>Ctrl/Shift + 鼠标点击</b></td><td>多选同级物料或SKU行</td><td>SKU清单、BOM树</td></tr>
        <tr><td><b>↑ / ↓</b></td><td>在筛选结果中连续选择上一项/下一项，跳过不可选物料，保留筛选文字</td><td>新建SKU、BOM新增/替换/版本更新/新增替代料</td></tr>
        <tr><td><b>Enter</b></td><td>确认首个筛选候选项或确认当前对话框</td><td>物料选择、查找、导入映射</td></tr></table>
        <h3>窗口操作</h3><p>所有主要交互窗口均可独立移动、切换和置顶。关闭有未保存内容的窗口时，请选择保存并退出、不保存退出或取消。</p>'''

    def _feature_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(self._section('SKU清单窗口：项目总览与批量入口', '这里显示当前项目全部SKU及其历史版本。“SKU”菜单包含新建SKU、SKU筛选、导出SKU清单；清单导出包含项目全部SKU历史版本，复用资料库表格格式并记忆导出目录。点击表头可排序，选择一行后双击打开BOM；Ctrl/Shift可多选，再右键对多个SKU执行浏览、编辑、导出或锁定。锁定列显示小锁，版本号加粗表示存在变更描述；底部同时显示“共计N个SKU，M个BOM”。', self._image_widget('sku_overview', '实际截图：SKU清单窗口')))
        layout.addWidget(self._section('物料库窗口：公共物料资料', '物料库维护基础编码、版本号、名称、规格、单位、等级、制造商、MPN和M/P，并显示BOM状态、呆滞状态及各SKU用量。菜单按钮可执行导入、导出、查找、筛选；右键可编辑、复制、删除、反查、版本更新、编辑BOM和新增替代料。', self._image_widget('material_library', '实际截图：物料库窗口')))
        layout.addWidget(self._section('BOM编辑窗口：树状结构与属性', '左侧是递归BOM树，右侧是当前节点属性和替代料。根节点显示SKU或选中的公共物料；树节点左键切换右侧资料，右键按分组提供新增、复制剪切粘贴、替换、版本更新、替代料、颜色、反查和导出。保存前变更有颜色标识，保存后恢复默认。', self._image_widget('bom_window', '实际截图：BOM编辑/浏览窗口')))
        layout.addWidget(self._section('导入、导出、对比和主题', '物料/BOM导入均支持Sheet选择、表头映射、必填项检查和结果明细。导入、导出、保存、打开/刷新清单及BOM对比等工作超过100毫秒时显示进度条；能确定数量时显示实际处理进度，未知总量或文件读写时显示忙碌状态。短操作不弹进度窗，等待用户选择/确认时暂停提示。修改日期和变更历史在界面及Excel中只显示整数秒，数据库保留高精度时间；BOM对比支持两个SKU历史版本或外部Excel，并同步标记新增、删除、修改、换料和交换。右上角太阳/月亮按钮切换主题，窗口尺寸和路径自动记忆。', self._image_widget('menu_theme', '实际截图：菜单和主题按钮')))
        return self._scroll(page)

    def _guide_page(self):
        from ui.help_guides import GUIDES
        page=QWidget();layout=QVBoxLayout(page)
        layout.addWidget(QLabel('先选择功能教程，再按步骤操作。红框为操作区域，红色箭头指向需填写或点击的位置；图片在编译时生成。'))
        self.guide_selector=QListWidget();self.guide_selector.setObjectName('helpGuideSelector');self.guide_selector.setMinimumWidth(230);self.guide_selector.setWordWrap(True);self.guide_selector.setTextElideMode(Qt.ElideNone)
        splitter=QSplitter(Qt.Horizontal)
        self.guide_view=QScrollArea();self.guide_view.setWidgetResizable(True)
        self._guide_positions={};self._guide_index=None
        for guide in GUIDES:self.guide_selector.addItem(guide['title']+'（'+str(len(guide['steps']))+'步）')
        self.guide_selector.currentRowChanged.connect(self._show_guide);self.guide_selector.setCurrentRow(0)
        splitter.addWidget(self.guide_selector);splitter.addWidget(self.guide_view);splitter.setStretchFactor(0,0);splitter.setStretchFactor(1,1);splitter.setSizes([270,760]);layout.addWidget(splitter,1)
        return page

    def _show_guide(self,index):
        from ui.help_guides import GUIDES
        if index<0:return
        if self._guide_index is not None:self._guide_positions[self._guide_index]=self.guide_view.verticalScrollBar().value()
        guide=GUIDES[index];body=QWidget();cards=QVBoxLayout(body)
        intro=QLabel('开始前：'+guide['before']);intro.setWordWrap(True);cards.addWidget(intro)
        for number,step in enumerate(guide['steps'],1):
            cards.addWidget(self._section('步骤'+str(number)+'：'+step['title'],step['detail'],self._image_widget(step['key'],'操作位置：'+step['title'])))
        cards.addStretch();self.guide_view.setWidget(body);self._guide_index=index
        self.guide_view.verticalScrollBar().setValue(self._guide_positions.get(index,0))

    def _tips_page(self):
        page=QWidget();layout=QVBoxLayout(page)
        tips=[
         ('技巧1：先筛选再操作','在物料库先使用筛选和Ctrl+F缩小范围，再执行批量操作；SKU清单勾选“只显示最新BOM”可避免误操作旧历史版本。',None),
         ('技巧2：用复制/剪切保持属性','BOM多选同级物料后复制或剪切，粘贴会保留数量、位置、备注、替代料和颜色；粘贴前看菜单项是否可用，可用性检查已经排除了重复和循环。',None),
         ('技巧3：用颜色检查未保存差异','保存前先观察绿色新增、红色删除线、黄棕色修改和深紫色联动变更；右键设置颜色用于业务标记，但不会覆盖变更颜色。',None),
         ('技巧4：共享物料先看影响范围','编辑公共子BOM前，先查看父级被哪些SKU及历史版本引用；系统提示父级升版时会列出受影响SKU，可逐项勾选同步。',None),
         ('技巧5：导入映射连续复用','首次映射确认后系统记住列关系；下一次导入同类表格会自动恢复，找不到的旧列会回到未选择，确认前仍应检查必填项。',None),
         ('技巧6：主题和窗口布局','深色模式下根节点灰度对比最强；拖动分隔条调整BOM树和属性区，窗口尺寸、列宽、导入导出路径会被记忆。',None)]
        for title,body,widget in tips:layout.addWidget(self._section(title,body,self._tip_image(title, widget)))
        return self._scroll(page)

    def _tip_image(self,title,widget=None):
        mapping={'技巧1':'tip01_filter','技巧2':'tip02_clipboard','技巧3':'tip03_colors','技巧4':'tip04_shared','技巧5':'tip05_mapping','技巧6':'tip06_theme'}
        key=next((value for label,value in mapping.items() if title.split('：',1)[0]==label),'sku_overview')
        return self._image_widget(key,'实际静态截图：'+title)

    def _image_widget(self,key,title):
        import sys
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))/'help_screenshots'
        path=root/(key+'.png')
        if not path.is_file():path=Path(__file__).resolve().parents[2]/'resources/help_screenshots'/(key+'.png')
        heading=QLabel(title);heading.setAlignment(Qt.AlignCenter);heading.setStyleSheet('font-weight:bold;padding:4px;')
        image=QLabel();image.setObjectName('help_image_'+key);image.setAlignment(Qt.AlignCenter);image.setMinimumHeight(260)
        pix=QPixmap(str(path)) if path.is_file() else QPixmap()
        if not pix.isNull():image.setPixmap(pix.scaled(min(pix.width(),1080),min(pix.height(),560),Qt.KeepAspectRatio,Qt.SmoothTransformation))
        else:image.setText('编译阶段静态截图缺失：'+key+'.png')
        box=QFrame();layout=QVBoxLayout(box);layout.addWidget(heading);layout.addWidget(image)
        if not pix.isNull():
            zoom=QPushButton('查看原图（可滚动）');zoom.clicked.connect(lambda checked=False,p=path,t=title:self._zoom_image(p,t));layout.addWidget(zoom)
        box.setFrameStyle(QFrame.StyledPanel|QFrame.Sunken);return box

    def _zoom_image(self,path,title):
        window=QDialog(self);window.setAttribute(Qt.WA_DeleteOnClose);window.setWindowTitle(title);window.resize(1100,780)
        layout=QVBoxLayout(window);area=QScrollArea();image=QLabel();image.setPixmap(QPixmap(str(path)));area.setWidget(image);layout.addWidget(area)
        window.show();window.raise_()

    def _section(self,title,text,image):
        box=QFrame();layout=QVBoxLayout(box);heading=QLabel(title);heading.setStyleSheet('font-size:16px;font-weight:bold;');layout.addWidget(heading)
        body=QLabel(text);body.setWordWrap(True);body.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(body)
        if image:layout.addWidget(image)
        box.setFrameStyle(QFrame.StyledPanel|QFrame.Sunken);return box

    def _scroll(self,widget):
        area=QScrollArea();area.setWidgetResizable(True);area.setWidget(widget);return area

    def _qa(self):
        return '''<h2>常见问题</h2><h3>Q：启动后SKU清单为空怎么办？</h3><p>A：检查项目菜单中的当前项目；没有当前项目时选择历史项目。若数据库路径失效，选择“指定数据库”重新关联，系统会先做完整性和结构校验。</p>
        <h3>Q：为什么BOM保存按钮不可用？</h3><p>A：没有未保存修改时保存按钮会禁用；受到其他BOM联动更新时先点击刷新，确认缓存内容后再保存。</p>
        <h3>Q：为什么物料不能加入BOM？</h3><p>A：可能是同一父级已有相同物料、会形成循环引用、物料被锁定或物料存在不允许嵌套的BOM结构。请查看弹窗列出的具体原因。</p>
        <h3>Q：导入表格提示映射失败？</h3><p>A：必填表头必须各自映射一次，空表头列会忽略；检查目标表头是否选择了正确Sheet，并确认没有重复映射。</p>
        <h3>Q：如何恢复误删的BOM物料？</h3><p>A：保存前右键删除线物料，选择“取消删除”；已经保存的删除需要从物料库重新新增到对应父级。</p>
        <h3>Q：如何获得帮助？</h3><p>A：保留软件版本号、项目名称、操作步骤和弹窗内容；同时查看关于窗口中的Git提交信息，便于定位对应版本。</p>'''
