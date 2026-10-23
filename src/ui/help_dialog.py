"""BOM管理系统帮助中心：快捷键、页面说明、操作指引、技巧和问答。"""
from pathlib import Path
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
        layout = QVBoxLayout(self)
        intro = QLabel('BOM管理系统帮助中心  ·  随软件内置的静态图文教程，无需打开示例项目')
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
        layout.addWidget(self._section('SKU清单窗口：项目总览与批量入口', '这里显示当前项目全部SKU及其历史版本。点击表头可排序，选择一行后双击打开BOM；Ctrl/Shift可多选，再右键对多个SKU执行浏览、编辑、导出或锁定。锁定列显示小锁，版本号加粗表示存在变更描述；底部同时显示“共计N个SKU，M个BOM”。', self._image_widget('sku_overview', '实际截图：SKU清单窗口')))
        layout.addWidget(self._section('物料库窗口：公共物料资料', '物料库维护基础编码、版本号、名称、规格、单位、等级、制造商、MPN和M/P，并显示BOM状态、呆滞状态及各SKU用量。菜单按钮可执行导入、导出、查找、筛选；右键可编辑、复制、删除、反查、版本更新、编辑BOM和新增替代料。', self._image_widget('material_library', '实际截图：物料库窗口')))
        layout.addWidget(self._section('BOM编辑窗口：树状结构与属性', '左侧是递归BOM树，右侧是当前节点属性和替代料。根节点显示SKU或选中的公共物料；树节点左键切换右侧资料，右键按分组提供新增、复制剪切粘贴、替换、版本更新、替代料、颜色、反查和导出。保存前变更有颜色标识，保存后恢复默认。', self._image_widget('bom_window', '实际截图：BOM编辑/浏览窗口')))
        layout.addWidget(self._section('导入、导出、对比和主题', '物料/BOM导入均支持Sheet选择、表头映射、必填项检查、进度条和结果明细；BOM对比支持两个SKU历史版本或外部Excel，并同步标记新增、删除、修改、换料和交换。右上角太阳/月亮按钮切换主题，窗口尺寸和路径自动记忆。', self._image_widget('menu_theme', '实际截图：菜单和主题按钮')))
        return self._scroll(page)

    def _guide_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        steps = [
          ('步骤1：选择或恢复项目', '启动时若配置未指定项目，选择“项目代码 项目名称”；系统先检查文件存在、SQLite完整性、表结构和项目元数据，成功后才写入当前项目。数据库不存在时可指定新位置、切换历史项目或关闭项目。', None),
          ('步骤2：新建物料', '打开物料库，按Ctrl+N或点击新建物料；填写必填的基础编码、版本号、名称、单位，规格、等级、制造商、MPN和M/P按实际情况填写。单位/M/P从下拉菜单选取，点击保存后窗口关闭且列表自动刷新。', None),
          ('步骤3：导入物料', '点击导入物料，依次选择文件、Sheet和表头映射。需求表头分必填与可选，必填项带星号；每个需求字段只能映射一次。确认后查看进度，结果窗口分开显示成功、重复跳过和失败，并列出编码、名称、版本和详细原因。', None),
          ('步骤4：新建SKU', '回到SKU清单按Ctrl+N；在可输入下拉框输入编码或名称，候选列表实时筛选。已有BOM结构或已经是SKU的候选会标记为不可用。回车可确认首个候选项，确认后SKU立即出现在清单。', None),
          ('步骤5：打开并检查BOM', '双击SKU行或右键打开BOM。左侧树的根节点是SKU，逐层展开子BOM；点击任意节点，右侧显示最新物料资料。数量、位置、备注可编辑，编码、版本、名称等只读字段可复制。', None),
          ('步骤6：新增、复制、替换和排序', '在目标节点右键选择新增同级/子级，物料选择框支持输入筛选和回车确认。复制/剪切会保留数量、位置、备注、替代料和颜色；粘贴前检查循环和重复。新增同级插入当前节点下方，同级物料可上移/下移。', None),
          ('步骤7：保存和联动刷新', '保存前新增物料为绿色、删除物料为红色删除线、属性修改为黄棕色、其他BOM导入变更为深紫色；点击保存才写入数据库。共享子BOM变化会通知其他打开窗口，刷新会保留本窗口未保存缓存，确认后再保存。', None),
          ('步骤8：导出和历史版本', 'BOM未保存时导出按钮禁用。保存后选择导出BOM或采购BOM；采购BOM按层级汇总用量。SKU右键复制BOM会生成新的历史版本，SKU编码不变但整棵BOM独立保存。', None),
          ('步骤9：锁定与浏览', 'SKU右键锁定后再次打开进入BOM浏览模式，编辑菜单不可用。其他BOM联动触及锁定BOM时系统列出SKU、物料和父项信息；解除锁定后才能继续编辑。', None),
          ('步骤10：查找和故障处理', '物料库/BOM按Ctrl+F查找编码、名称、规格、制造商和MPN，双击结果定位原表或树节点。遇到数据库损坏、路径失效或导入错误时，保留弹窗和版本信息，按提示重新选择数据库或修正映射。', None)]
        for title,body,widget in steps:
            layout.addWidget(self._section(title,body,self._guide_image(title, widget)))
        return self._scroll(page)

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

    def _guide_image(self,title,widget=None):
        mapping={'步骤1':'step01_project','步骤2':'step02_material','步骤3':'step03_mapping','步骤4':'step04_sku','步骤5':'step05_bom_tree','步骤6':'step06_bom_edit','步骤7':'step07_bom_info','步骤8':'step08_export','步骤9':'step09_bom_lock','步骤10':'step10_search'}
        key=next((value for label,value in mapping.items() if title.split('：',1)[0]==label),'sku_overview')
        return self._image_widget(key,'本步骤静态截图：'+title)

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
        image=QLabel();image.setAlignment(Qt.AlignCenter);image.setMinimumHeight(260)
        pix=QPixmap(str(path)) if path.is_file() else QPixmap()
        if not pix.isNull():image.setPixmap(pix.scaled(1080,560,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        else:image.setText('编译阶段静态截图缺失：'+key+'.png')
        box=QFrame();layout=QVBoxLayout(box);layout.addWidget(heading);layout.addWidget(image);box.setFrameStyle(QFrame.StyledPanel|QFrame.Sunken);return box

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
