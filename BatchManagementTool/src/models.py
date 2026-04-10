"""
models.py

定义项目所需的核心数据类，用于将表格数据对象化，方便在代码中处理和传递。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class ProductionOrder:
    """代表一条生产计划 (来自 ZCPRS)"""
    order_number: str
    material: str
    work_center: str # 包装线
    planned_quantity: float
    uom: str # 单位 (CS/EA)
    start_datetime: datetime
    end_datetime: datetime
    mrp_element: str
    material_description: Optional[str] = None
    allow_gss12_reduced_moq: bool = False
    
    # 计算得出的属性
    shift: Optional[str] = None # N/D/M 班次
    msu_demand: Optional[float] = None
    wip_code: Optional[str] = None
    product_type: Optional[str] = None # Shampoo/Conditioner
    product_category: Optional[str] = None # 规范化后的类型 (shampoo/conditioner)
    suf: Optional[float] = None
    segment: Optional[str] = None
    
    # 匹配结果
    available_systems: Optional[List['MakingSystem']] = None

    # 分配结果
    assigned_system: Optional['MakingSystem'] = None
    batch_id: Optional[str] = None
    batch_note: Optional[str] = None
    batch_count: float = 0.0
    decision_explain: Optional[str] = None
    alerts: List[str] = field(default_factory=list)
    original_order_number: Optional[str] = None
    segment_index: int = 1
    segment_total: int = 1

@dataclass
class MakingSystem:
    """代表一个搅拌系统的能力 (来自 Making Capacity)"""
    system_id: str
    name: str
    supported_msu: List[float]
    capacity_tons: List[float]
    product_suitability: List[str]
    n_shift_limit: int
    d_shift_limit: int
    m_shift_limit: int
    shared_logic: Optional[str] = None # 备注逻辑
    total_limit: Optional[int] = None

@dataclass
class Batch:
    """代表一个成型的搅拌批次"""
    batch_id: str
    wip_code: str
    msu_size: float
    assigned_system: MakingSystem
    shift: str
    date: str
    orders: List[ProductionOrder] = field(default_factory=list)
    current_load: float = 0.0
    physical_batches: int = 1

    def get_order_numbers(self) -> List[str]:
        labels: List[str] = []
        for order in self.orders:
            base = order.original_order_number or order.order_number
            if order.segment_total > 1:
                labels.append(f"{base} (拆分 {order.segment_index}/{order.segment_total})")
            else:
                labels.append(str(base))
        return labels

    def remaining_capacity(self) -> float:
        return self.msu_size - self.current_load
