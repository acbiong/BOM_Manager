"""BOM管理系统帮助中心：快捷键、页面说明、操作指引、技巧和问答。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QScrollArea, QTextBrowser, QFrame)
from ui.interactive_windows import QDialog

class HelpDialog(QDialog):
    """独立帮助窗口；截图来自当前运行中的实际页面。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('帮助 - BOM管理系统')
        self.resize(1050, 760)
        self.setMinimumSize(760, 540)
        self._ensure_screenshot_sources()
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
        layout.addWidget(self._section('SKU清单窗口：项目总览与批量入口', '这里显示当前项目全部SKU及其历史版本。点击表头可排序，选择一行后双击打开BOM；Ctrl/Shift可多选，再右键对多个SKU执行浏览、编辑、导出或锁定。锁定列显示小锁，版本号加粗表示存在变更描述；底部同时显示“共计N个SKU，M个BOM”。', self._grab(self.parentWidget(), '实际截图：SKU清单窗口')))
        layout.addWidget(self._section('物料库窗口：公共物料资料', '物料库维护基础编码、版本号、名称、规格、单位、等级、制造商、MPN和M/P，并显示BOM状态、呆滞状态及各SKU用量。菜单按钮可执行导入、导出、查找、筛选；右键可编辑、复制、删除、反查、版本更新、编辑BOM和新增替代料。', self._grab(getattr(self.parentWidget(), '_materials', None), '实际截图：物料库窗口')))
        layout.addWidget(self._section('BOM编辑窗口：树状结构与属性', '左侧是递归BOM树，右侧是当前节点属性和替代料。根节点显示SKU或选中的公共物料；树节点左键切换右侧资料，右键按分组提供新增、复制剪切粘贴、替换、版本更新、替代料、颜色、反查和导出。保存前变更有颜色标识，保存后恢复默认。', self._grab(self._first_bom(), '实际截图：BOM编辑/浏览窗口')))
        layout.addWidget(self._section('导入、导出、对比和主题', '物料/BOM导入均支持Sheet选择、表头映射、必填项检查、进度条和结果明细；BOM对比支持两个SKU历史版本或外部Excel，并同步标记新增、删除、修改、换料和交换。右上角太阳/月亮按钮切换主题，窗口尺寸和路径自动记忆。', self._grab(self.parentWidget().menuBar() if self.parentWidget() else None, '实际截图：菜单和主题按钮')))
        return self._scroll(page)

    def _guide_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        steps = [
          ('步骤1：选择或恢复项目', '启动时若配置未指定项目，选择“项目代码 项目名称”；系统先检查文件存在、SQLite完整性、表结构和项目元数据，成功后才写入当前项目。数据库不存在时可指定新位置、切换历史项目或关闭项目。', self.parentWidget()),
          ('步骤2：新建物料', '打开物料库，按Ctrl+N或点击新建物料；填写必填的基础编码、版本号、名称、单位，规格、等级、制造商、MPN和M/P按实际情况填写。单位/M/P从下拉菜单选取，点击保存后窗口关闭且列表自动刷新。', getattr(self.parentWidget(), '_materials', None)),
          ('步骤3：导入物料', '点击导入物料，依次选择文件、Sheet和表头映射。需求表头分必填与可选，必填项带星号；每个需求字段只能映射一次。确认后查看进度，结果窗口分开显示成功、重复跳过和失败，并列出编码、名称、版本和详细原因。', getattr(self.parentWidget(), '_materials', None)),
          ('步骤4：新建SKU', '回到SKU清单按Ctrl+N；在可输入下拉框输入编码或名称，候选列表实时筛选。已有BOM结构或已经是SKU的候选会标记为不可用。回车可确认首个候选项，确认后SKU立即出现在清单。', self.parentWidget()),
          ('步骤5：打开并检查BOM', '双击SKU行或右键打开BOM。左侧树的根节点是SKU，逐层展开子BOM；点击任意节点，右侧显示最新物料资料。数量、位置、备注可编辑，编码、版本、名称等只读字段可复制。', self._first_bom() or self.parentWidget()),
          ('步骤6：新增、复制、替换和排序', '在目标节点右键选择新增同级/子级，物料选择框支持输入筛选和回车确认。复制/剪切会保留数量、位置、备注、替代料和颜色；粘贴前检查循环和重复。新增同级插入当前节点下方，同级物料可上移/下移。', self._first_bom() or self.parentWidget()),
          ('步骤7：保存和联动刷新', '保存前新增物料为绿色、删除物料为红色删除线、属性修改为黄棕色、其他BOM导入变更为深紫色；点击保存才写入数据库。共享子BOM变化会通知其他打开窗口，刷新会保留本窗口未保存缓存，确认后再保存。', self._first_bom() or self.parentWidget()),
          ('步骤8：导出和历史版本', 'BOM未保存时导出按钮禁用。保存后选择导出BOM或采购BOM；采购BOM按层级汇总用量。SKU右键复制BOM会生成新的历史版本，SKU编码不变但整棵BOM独立保存。', self.parentWidget()),
          ('步骤9：锁定与浏览', 'SKU右键锁定后再次打开进入BOM浏览模式，编辑菜单不可用。其他BOM联动触及锁定BOM时系统列出SKU、物料和父项信息；解除锁定后才能继续编辑。', self.parentWidget()),
          ('步骤10：查找和故障处理', '物料库/BOM按Ctrl+F查找编码、名称、规格、制造商和MPN，双击结果定位原表或树节点。遇到数据库损坏、路径失效或导入错误时，保留弹窗和版本信息，按提示重新选择数据库或修正映射。', self._first_bom() or getattr(self.parentWidget(), '_materials', None) or self.parentWidget())]
        for title,body,widget in steps:
            layout.addWidget(self._section(title,body,self._guide_image(title, widget)))
        return self._scroll(page)

    def _tips_page(self):
        page=QWidget();layout=QVBoxLayout(page)
        tips=[
         ('技巧1：先筛选再操作','在物料库先使用筛选和Ctrl+F缩小范围，再执行批量操作；SKU清单勾选“只显示最新BOM”可避免误操作旧历史版本。',self.parentWidget()),
         ('技巧2：用复制/剪切保持属性','BOM多选同级物料后复制或剪切，粘贴会保留数量、位置、备注、替代料和颜色；粘贴前看菜单项是否可用，可用性检查已经排除了重复和循环。',self._first_bom() or self.parentWidget()),
         ('技巧3：用颜色检查未保存差异','保存前先观察绿色新增、红色删除线、黄棕色修改和深紫色联动变更；右键设置颜色用于业务标记，但不会覆盖变更颜色。',self._first_bom() or self.parentWidget()),
         ('技巧4：共享物料先看影响范围','编辑公共子BOM前，先查看父级被哪些SKU及历史版本引用；系统提示父级升版时会列出受影响SKU，可逐项勾选同步。',self._first_bom() or self.parentWidget()),
         ('技巧5：导入映射连续复用','首次映射确认后系统记住列关系；下一次导入同类表格会自动恢复，找不到的旧列会回到未选择，确认前仍应检查必填项。',getattr(self.parentWidget(), '_materials', None) or self.parentWidget()),
         ('技巧6：主题和窗口布局','深色模式下根节点灰度对比最强；拖动分隔条调整BOM树和属性区，窗口尺寸、列宽、导入导出路径会被记忆。',self.parentWidget())]
        for title,body,widget in tips:layout.addWidget(self._section(title,body,self._tip_image(title, widget)))
        return self._scroll(page)

    def _qa(self):
        return '''<h2>常见问题</h2><h3>Q：启动后SKU清单为空怎么办？</h3><p>A：检查项目菜单中的当前项目；没有当前项目时选择历史项目。若数据库路径失效，选择“指定数据库”重新关联，系统会先做完整性和结构校验。</p>
        <h3>Q：为什么BOM保存按钮不可用？</h3><p>A：没有未保存修改时保存按钮会禁用；受到其他BOM联动更新时先点击刷新，确认缓存内容后再保存。</p>
        <h3>Q：为什么物料不能加入BOM？</h3><p>A：可能是同一父级已有相同物料、会形成循环引用、物料被锁定或物料存在不允许嵌套的BOM结构。请查看弹窗列出的具体原因。</p>
        <h3>Q：导入表格提示映射失败？</h3><p>A：必填表头必须各自映射一次，空表头列会忽略；检查目标表头是否选择了正确Sheet，并确认没有重复映射。</p>
        <h3>Q：如何恢复误删的BOM物料？</h3><p>A：保存前右键删除线物料，选择“取消删除”；已经保存的删除需要从物料库重新新增到对应父级。</p>
        <h3>Q：如何获得帮助？</h3><p>A：保留软件版本号、项目名称、操作步骤和弹窗内容；同时查看关于窗口中的Git提交信息，便于定位对应版本。</p>'''

    def _ensure_screenshot_sources(self):
        """打开真实页面作为截图来源；不创建虚构的静态示意图。"""
        parent=self.parentWidget()
        if parent is None:return
        try:
            if getattr(parent,'svc',None) is not None and parent.svc.db is not None:
                if getattr(parent,'_materials',None) is None:
                    parent.show_materials()
                if not getattr(parent,'_bom_windows',{}):
                    row=parent.svc.db.conn.execute('SELECT id FROM skus ORDER BY id LIMIT 1').fetchone()
                    if row:parent.open_bom_id(row['id'])
        except Exception:
            # 无项目或数据库不完整时，仍保留主窗口截图并显示文字说明。
            pass

    def _first_bom(self):
        parent=self.parentWidget()
        return next(iter(getattr(parent,'_bom_windows',{}).values()),None) if parent else None

    def _guide_image(self, title, fallback):
        """为步骤选择对应真实页面；对话框截图使用当前项目真实数据。"""
        parent=self.parentWidget(); service=getattr(parent,'svc',None)
        bom=self._first_bom()
        if bom is not None:
            if title.startswith('步骤6'):
                return self._grab(bom.tree,'本步骤实际截图：'+title)
            if title.startswith('步骤7'):
                return self._grab(bom.info_scroll,'本步骤实际截图：'+title)
            if title.startswith('步骤9'):
                return self._grab(bom.tree,'本步骤实际截图：'+title)
        try:
            from ui.main_window import MaterialDialog, NewSkuDialog, MaterialHeaderMappingDialog
            dialog=None
            if service is not None and service.db is not None:
                first=service.db.conn.execute('SELECT * FROM materials ORDER BY id LIMIT 1').fetchone()
                data=dict(first) if first else {}
                if title.startswith('步骤2'):
                    dialog=MaterialDialog(parent,data=data,readonly_keys={'base_code','version'})
                    dialog.setWindowTitle('实际截图：新建/编辑物料')
                elif title.startswith('步骤3'):
                    headers=['物料基础编码','物料版本号','物料名称','物料规格','单位','物料等级','M/P']
                    rows=[tuple((data.get(k) or '') for k in ('base_code','version','name','description','unit','grade','mp_flag'))]
                    dialog=MaterialHeaderMappingDialog('帮助中心示例.xlsx',headers,[],parent,preview_rows=rows)
                    dialog.setWindowTitle('实际截图：物料表头映射')
                elif title.startswith('步骤4'):
                    dialog=NewSkuDialog(service,parent);dialog.setWindowTitle('实际截图：新建SKU')
            if dialog is not None:
                dialog.resize(min(dialog.width(),1000),min(dialog.height(),650));dialog.show();QApplication.processEvents()
                image=self._grab(dialog,'本步骤实际截图：'+title);dialog.close();dialog.deleteLater();return image
            if title.startswith('步骤10') and getattr(parent,'_materials',None) is not None:
                from ui.material_search import MaterialSearchDialog
                dialog=MaterialSearchDialog(parent._materials);dialog.show();QApplication.processEvents();image=self._grab(dialog,'本步骤实际截图：'+title);dialog.close();dialog.deleteLater();return image
        except Exception:
            pass
        return self._grab(fallback,'本步骤实际截图：'+title)

    def _tip_image(self, title, fallback):
        target=self._first_bom()
        if target is not None:
            if title.startswith('技巧2') or title.startswith('技巧3'):
                return self._grab(target.tree,'实际截图：'+title)
            if title.startswith('技巧4'):
                return self._grab(target.info_scroll,'实际截图：'+title)
        if title.startswith('技巧1') and getattr(self.parentWidget(),'table',None) is not None:
            return self._grab(self.parentWidget().table,'实际截图：'+title)
        return self._grab(fallback,'实际截图：'+title)

    def _grab(self, widget, title):
        # 每个教程步骤必须有一张实际截图；目标窗口未打开时仅回退到主窗口。
        if widget is None or not widget.isVisible():
            widget=self.parentWidget()
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
