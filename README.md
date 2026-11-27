# 客运车场充电排班

面向公交站务的本地工作台。内置业务样例覆盖公交回场电量回归、峰段容量与充电分派。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18204/` 查看待分派车次。左侧六个入口可展开运行证据。调整「分配容量」，点击「重排车次」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 车次归集 `terminal_arrivals`
- 能耗校正 `traction_history`
- 电量回归 `range_regression`
- 插枪窗口 `plug_windows`
- 峰段分派 `depot_allocation`
- 交班验算 `dispatch_recheck`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/dispatch_recheck` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m depotload.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
