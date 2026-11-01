"""Per-SKU-history ECNs, lossless legacy-note migration and export matrix."""
FIELDS=('ecn_number','ecn_name','ecn_content')


def parse_legacy(text):
    first,separator,content=(text or '').replace('\r\n','\n').replace('\r','\n').partition('\n')
    number=first.strip()
    if len(number)>=2 and (number[0],number[-1]) in (('[',']'),('【','】'),('［','］')):number=number[1:-1].strip()
    return number,'',content


def migrate(conn):
    columns={r[1] for r in conn.execute('PRAGMA table_info(skus)')}
    if set(FIELDS)<=columns:return
    # NULL means the default follows the history number; explicit blank input
    # stays blank, and copied BOMs start their own ECN rather than inheriting it.
    for field in FIELDS:
        if field not in columns:conn.execute('ALTER TABLE skus ADD COLUMN '+field+(' TEXT' if field=='ecn_number' else " TEXT NOT NULL DEFAULT ''"))
    for row in conn.execute('SELECT id,change_description FROM skus').fetchall():
        if (row['change_description'] or '').strip():
            conn.execute('UPDATE skus SET ecn_number=?,ecn_name=?,ecn_content=?,change_description=? WHERE id=?',(*parse_legacy(row['change_description']),'',row['id']))


def values(row):
    return (row['ecn_number'] if row['ecn_number'] is not None else '/' if row['mirror_version']==100 else '',row['ecn_name'],row['ecn_content'])


def update(service,sid,number,name,content,expected=None):
    from datetime import datetime
    from services.sku_lock import assert_sku_unlocked
    data=(str(number),str(name),str(content))
    if any('\n' in v or '\r' in v for v in data[:2]):raise ValueError('ECN编号和名称只能填写单行文本')
    with service.db.transaction():
        row=service.db.conn.execute('SELECT * FROM skus WHERE id=?',(sid,)).fetchone()
        if row is None:raise ValueError('SKU不存在')
        before=values(row)
        if expected is not None and tuple(expected)!=before:raise ValueError('ECN已被修改，请重新打开后编辑')
        if data==before:return
        assert_sku_unlocked(service,sid)
        stamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-4]
        service.db.conn.execute('UPDATE skus SET ecn_number=?,ecn_name=?,ecn_content=?,updated_at=? WHERE id=?',(*data,stamp,sid))
        if not row['scope_id']:service.db.conn.execute('UPDATE materials SET updated_at=? WHERE id=?',(stamp,row['material_id']))
        detail='\n'.join(label+'：'+old+' → '+new for label,old,new in zip(('ECN编号','ECN名称','ECN变更内容'),before,data) if old!=new)
        service.for_sku(sid).log('sku',sid,'ecn',detail)
        service.publish({'type':'sku_ecn_changed','id':sid})


def write_sheet(service,sheet,skus):
    from infrastructure.operation_progress import checkpoint
    sku_columns={}
    for sku in skus:sku_columns.setdefault(sku['material_id'],sku['base_code']+sku['version']+' '+sku['name'])
    sheet.append(['序号','ECN编号','ECN名称',*sku_columns.values()])
    entries={}
    for sku in skus:
        checkpoint();number,name,content=values(sku)
        if number in ('','/') and not name and not content:continue
        # Empty IDs are independent records, not one shared unnamed ECN.
        key=(number,name,None if number not in ('','/') else sku['id'])
        entry=entries.setdefault(key,{})
        entry.setdefault(sku['material_id'],[]).append((sku['mirror_version'],sku['id'],content))
    for index,((number,name,_),entry) in enumerate(entries.items(),1):
        cells=['\n\n'.join('【'+str(version)+'】\n'+content for version,_,content in sorted(entry.get(mid,[]))) for mid in sku_columns]
        sheet.append([index,number,name,*cells])
    # Codes/names/content are literal user text, including leading '='.
    for row in sheet:
        for cell in row:
            if isinstance(cell.value,str):cell.data_type='s'
    service.format_export_sheet(sheet,{'序号'},max_width=30)
