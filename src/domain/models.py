"""领域模型：物料、SKU、BOM和项目数据结构。输入输出均为dataclass。编辑时间：2026-09-24。"""
from dataclasses import dataclass, field
from typing import Optional
@dataclass
class Material:
    id: Optional[int]=None; base_code:str=''; version:str=''; name:str=''; description:str=''; unit:str='pcs'; manufacturer:str=''; mpn:str=''; mp_flag:str='M'; has_bom:bool=False; idle:bool=False
@dataclass
class BomItem:
    id:Optional[int]=None; parent_material_id:int=0; material_id:int=0; quantity:float=1; unit:str='pcs'; position:str=''; level_no:int=1; remark:str=''; alternates:list=field(default_factory=list)
