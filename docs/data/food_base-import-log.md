# food_base 数据快照锁定记录

记录本地导入的外部食物基础库(SPEC §4.4)每次锁定的具体版本，用于版本追溯和新旧对比。原始数据文件本身不进 git（`backend/data/` 整体在 `.gitignore` 中排除，原因见 SPEC §4.4.1 关于授权/许可证的说明），这里只记录版本坐标；完整校验信息（HTTP 状态、逐文件字节数核对结果）见对应本地路径下的 `MANIFEST.txt`。

## food_base_cn

| 锁定日期 | 来源仓库 | 版本目录 | commit SHA | 文件数 | 总字节数 | 记录数 | 本地路径 |
|---|---|---|---|---|---|---|---|
| 2026-08-17 | [Sanotsu/china-food-composition-data](https://github.com/Sanotsu/china-food-composition-data) | `json_data_vision_251206_Qwen2-5-VL-72B-Instruct` | `095034a96376d893582b412900fa8fdf792b4194` | 61 | 1233866 | 1657 | `backend/data/food_base/food_base_cn/json_data_vision_251206_Qwen2-5-VL-72B-Instruct/` |

以后每次重新锁定新版本，在表格里加一行，不覆盖旧行；对应地在 `backend/data/food_base/food_base_cn/` 下新建一个按新版本目录名命名的兄弟目录，同样不覆盖旧目录（详见 SPEC §4.4.1“导入必须固定到具体 commit”）。

## food_base_us

和 `food_base_cn` 同样的"锁定版本快照导入"模式，不是运行时 API 调用+缓存（选型依据见决策记录 0005）。
用**两个独立的数据集**，各自按自己的发布节奏单独锁定版本（不像 `food_base_cn` 只有一个来源）：

| 数据集 | 锁定日期 | 来源 | 发布日期 | 下载 URL | 本地路径 |
|---|---|---|---|---|---|
| Foundation Foods | 2026-08-20 | USDA FoodData Central 批量下载 | 2026-04-30 | `https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_json_2026-04-30.zip` | `backend/data/food_base/food_base_us/foundation_food_json_2026-04-30/` |
| Survey (FNDDS) | 2026-08-20 | USDA FoodData Central 批量下载 | 2024-10-31 | `https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_survey_food_json_2024-10-31.zip` | `backend/data/food_base/food_base_us/survey_food_json_2024-10-31/` |

两者都不需要 API key（公开静态文件下载）。**明确排除** `SR Legacy`（USDA 官方标注为已冻结的历史数据库，
最后一次发布是 2018-04，不再更新）和 `Branded Foods`（全是美国商超品牌预包装食品，解压后约 3.1G，不适合
中国用户的家常餐食场景，体量也远超需要）。完整校验信息（结构核实、能量字段实测分布、fdc_id 唯一性核对）
见各自目录下的 `MANIFEST.txt`。以后重新锁定某个数据集的新版本时，同样是新建一个按新发布日期命名的兄弟
目录，不覆盖旧目录——两个数据集各自独立更新，不要求同步重新锁定。
