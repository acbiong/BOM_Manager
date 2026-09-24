"""需求追踪自动审计：检查规格书是否包含1~137连续追踪编号。"""
from pathlib import Path
import re,sys
p=Path(__file__).parents[1]/'docs/软件开发规格书.md'; text=p.read_text(encoding='utf-8')
ids=[]
for line in text.splitlines():
 m=re.match(r'^\|(\d+)\|',line)
 if m: ids.append(int(m.group(1)))
expected=list(range(1,138))
if ids!=expected: print('TRACE_FAIL',len(ids),ids[:3],ids[-3:]); sys.exit(1)
print('TRACE_OK 137/137')
