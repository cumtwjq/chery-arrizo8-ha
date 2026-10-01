# 艾瑞泽8仪表板

升级集成后，设备里会出现「位置」实体，类型为 `device_tracker`。有效经纬度会显示在 HA 地图；服务器没有提供有效坐标时，实体显示「不可用」。这是车辆最近一次上报的位置，不代表秒级实时定位。

## 不依赖 HACS 的卡片

将安装包里的 `www/arrizo8/hero.png` 上传到 HA 的 `/config/www/arrizo8/`。在仪表板新增「手动」卡片，粘贴下面 YAML，再把 `REPLACE_...` 改成你设备里实际的实体 ID。实体 ID 可在「开发者工具 → 状态」搜索「艾瑞泽8」查看。

```yaml
type: vertical-stack
cards:
  - type: picture
    image: /local/arrizo8/hero.png
  - type: grid
    columns: 3
    square: false
    cards:
      - type: tile
        entity: sensor.REPLACE_ODOMETER
        name: 总里程
        icon: mdi:counter
      - type: tile
        entity: sensor.REPLACE_RANGE
        name: 剩余续航
        icon: mdi:map-marker-distance
      - type: tile
        entity: sensor.REPLACE_FUEL
        name: 剩余油量
        icon: mdi:gas-station
  - type: grid
    columns: 2
    square: false
    cards:
      - type: tile
        entity: sensor.REPLACE_LOCK
        name: 车锁状态
        icon: mdi:car-door-lock
      - type: tile
        entity: sensor.REPLACE_STATUS_TIME
        name: 车况时间
        icon: mdi:clock-outline
  - type: map
    title: 车辆位置
    aspect_ratio: "16:9"
    auto_fit: true
    entities:
      - device_tracker.REPLACE_LOCATION
```

0.3.0 起，总里程和剩余续航显示 `km`，车主确认剩余油量 `oilSurplus` 为百分比，胎压显示 `kPa`。图中车辆为示意插画。

## 想用更丰富的车辆卡片

社区的 [Vehicle status card](https://github.com/ngocjohn/vehicle-status-card) 支持车辆图片、状态指标、胎压和内嵌小地图。若 HA 已装 HACS，可搜索并安装 **Vehicle status card**，然后在卡片的图形编辑器中把车况传感器和本集成新增的「位置」实体对应起来。无需修改集成代码。它是可选界面组件，不参与车辆接口请求。

## 位置精度

车况接口返回 `lat`、`lon`。车主实测：22 款艾瑞泽8雅使用高德 GCJ‑02 坐标校准后，HA 地图与奇瑞 App 的位置对齐。集成现在固定使用这种校准方式，无需再选地图坐标系。HA 地图底图仍由 HA 提供；这里调整的是车辆坐标。不要发送精确经纬度或家庭住址。
