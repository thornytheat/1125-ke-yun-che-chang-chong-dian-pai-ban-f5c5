# 客运车场充电排班 · 验证索引

AI/ML / 传统ML · 公交回场电量回归、峰段容量与充电分派

## 功能模块

| 模块 | 业务职责 | 计算规则 | 核心位置 | 独立测试 |
|---|---|---|---|---|
| M1 | 车次归集 | 按车场与车次消除重复快照，隔离同修订冲突 | `src/depotload/terminal_arrivals/normalization.py` `src/depotload/terminal_arrivals/contracts.py` `src/depotload/terminal_arrivals/service.py` | `tests/test_terminal_arrivals.py` |
| M2 | 能耗校正 | 按完结与入账时点隔离训练和留出班次，再生净电量与冷凝辅助负载 | `src/depotload/traction_history/chronology.py` `src/depotload/traction_history/contracts.py` `src/depotload/traction_history/service.py` | `tests/test_traction_history.py` |
| M3 | 电量回归 | 按时间窗拟合岭回归并冻结缩放，留出残差上界配合工况拒放 | `src/depotload/range_regression/fitting.py` `src/depotload/range_regression/contracts.py` `src/depotload/range_regression/service.py` | `tests/test_range_regression.py` |
| M4 | 插枪窗口 | 半开维护窗与无障碍车位过滤，按馈线实际功率生成 15 分钟槽 | `src/depotload/plug_windows/occupancy.py` `src/depotload/plug_windows/contracts.py` `src/depotload/plug_windows/service.py` | `tests/test_plug_windows.py` |
| M5 | 峰段分派 | 车次优先级、双枪互斥和馈线共享功率，无法补足整班电量时回退试排 | `src/depotload/depot_allocation/priority.py` `src/depotload/depot_allocation/contracts.py` `src/depotload/depot_allocation/service.py` | `tests/test_depot_allocation.py` |
| M6 | 交班验算 | 独立功率与交班电量守恒验算，变更依赖后证据签名失效 | `src/depotload/dispatch_recheck/reconciliation.py` `src/depotload/dispatch_recheck/contracts.py` `src/depotload/dispatch_recheck/service.py` | `tests/test_dispatch_recheck.py` |

## 边界案例

| 陷阱 | 触发 | 错误做法 | 实现 | 位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-19 | 残障优先与紧急车次冲突 | 随输入顺序纳入 | 显式优先键 | `src/depotload/depot_allocation/priority.py` | `tests/test_depot_allocation.py::test_deterministic_priority_and_no_double_charge` |
| TRAP-21 | 枪账同发车台账不一致 | 只核对一个方向 | 发车及调度流水交叉确认 | `src/depotload/dispatch_recheck/reconciliation.py` | `tests/test_dispatch_recheck.py::test_checks_both_identities` |
| TRAP-23 | 相邻枪位开放分钟 | 端点双重占用 | 半开区间 | `src/depotload/plug_windows/occupancy.py` | `tests/test_plug_windows.py::test_boundary_windows_do_not_overlap` |
| TRAP-24 | 配额以分计量 | 重复浮点舍入 | 需求取整保护、电量守恒 | `src/depotload/depot_allocation/priority.py` | `tests/test_depot_allocation.py::test_cent_rounding_conserves_energy` |
| TRAP-25 | 同车次修订时间重叠 | 任意选择最后一份 | 冲突隔离，修订证据排序 | `src/depotload/terminal_arrivals/normalization.py` | `tests/test_terminal_arrivals.py::test_same_revision_conflicts` |
| TRAP-32 | 大基数列与常数列 | 平方均值相减 | 中心平方和与尺度地板 | `src/depotload/traction_history/chronology.py` | `tests/test_traction_history.py::test_variance_centered` |
| TRAP-42 | 入账时间迟于训练截止 | 全量拟合特征 | 双时钟切窗，统计量仅训练折 | `src/depotload/traction_history/chronology.py` | `tests/test_traction_history.py::test_late_booking_and_temporal_split` |
| TRAP-43 | 留出记录无正例 | 准确率掩盖不可用召回 | 缺正例召回为空 | `src/depotload/dispatch_recheck/reconciliation.py` | `tests/test_dispatch_recheck.py::test_empty_positive_reference` |
| TRAP-44 | 留出校准无法确认分布外线路 | 直接套用历史上界 | 保序残差秩与训练距离拒放 | `src/depotload/range_regression/fitting.py` | `tests/test_range_regression.py::test_outside_manually_held` |
| TRAP-53 | 不同长度路线到达同一批 | 使用批内均值归一化 | 冻结训练尺度逐条推断 | `src/depotload/range_regression/fitting.py` | `tests/test_range_regression.py::test_batch_invariance` |
| TRAP-54 | 上游负荷参数修改 | 沿用上次排班验算 | 对配置与证据内容签名 | `src/depotload/dispatch_recheck/reconciliation.py` | `tests/test_dispatch_recheck.py::test_checks_source_config_changes` |
