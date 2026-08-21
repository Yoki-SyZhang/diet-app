# feature_demo_02_food_base — 实现计划(Demo 1.4–1.5)

## Context

`feature_demo_01_scaffold`(1.1–1.3)已合入 main:后端骨架、5 张表的首条迁移(`food_base_cn`/`food_base_us` 表已建但都是空表)、前端 PWA 空壳。按 `tasks/STATUS.md` 的依赖顺序(01→02→03→...),下一步是 02:

- **1.4** `food_base_cn` 导入——把中国食物成分表 OCR 快照(已锁定 commit,本地已有原始 JSON)灌进 `food_base_cn` 表。
- **1.5** `food_base_us` 快照导入——USDA 官方批量下载(Foundation+Survey)锁定快照,和 1.4 对称的整表覆盖式导入 + 按 id+name+unit 取值的适配器,写入 `food_base_us` 表(选型依据见 ADR 0005)。

两步合并成一个分支 `feature_demo_02_food_base`,一个 PR。

**范围边界(明确排除)**:本 PR 只解决"把两个外部数据源的数据准备好、能被查到",**不做**:
- 四级查询链本身(逐级召回、单候选直采、多候选转 LLM 消歧)——那是 1.7。
- 单位归一 + 可食率应用到用户实际输入的克重 + null 传播到 `meal_entry` 计算——那是 1.6。`edible_pct` 这一步只负责把原始百分比数字存进库,不做任何乘法。
- 中文食物名→英文的翻译(USDA 查询前置步骤)——SPEC §4.4.2 说这一步复用 §8 的文本 LLM 调用,属于 1.7/1.9 范畴,不在本 PR。
- 两张表都不加 `user_id`(单用户系统铁律)。

依据:`docs/product/SPEC.md` §4.4(4.4.1 中国来源 / 4.4.2 USDA 来源)、§7.1/7.3/7.8、`docs/data/food_base-import-log.md`、`docs/decisions/0002-composed-dish-fallback.md`(USDA 实测发现:`foodNutrients` 含占位行如 `id=2045 name="Proximates"`、中文查询基本查不到)、已有的 `backend/app/models/food_base_cn.py`/`food_base_us.py`/迁移文件(表结构已定,本 PR 不新建迁移)、`.claude/rules/backend.md`(业务规则进共享服务层)。

**已用真实本地数据独立核实的事实**(不是猜测,已跑脚本验证 61 个文件、1657 条记录,并原样抓出下面几条真实记录):
- 61 个 `merged_*.json` 文件,共 **1657 条**记录,**0 个重复 `foodCode`**(当前快照内)。

  ```json
  // foodCode=192001,merged_植物油-植物油.json —— 星号脚注案例
  { "foodCode": "192001", "foodName": "菜籽油 [青油]", "edible": "100",
    "energyKCal": "899*", "energyKJ": "3761*",
    "protein": "Tr", "fat": "99.9", "CHO": "0", "dietaryFiber": "—", ... }

  // foodCode=052005,merged_菌藻类-藻类.json —— 未知垃圾值 + 破折号同现一条记录
  { "foodCode": "052005", "foodName": "海冻菜（干）[石花菜,冻菜]", "edible": "100",
    "energyKCal": "un", "protein": "5.4", "fat": "0.1", "CHO": "72.9",
    "dietaryFiber": "—", ... }

  // foodCode=192011,merged_植物油-植物油.json —— 整条记录级缺失(31 个字段,除 foodCode/foodName 全为 ""，连 remark 都是空)
  { "foodCode": "192011", "foodName": "麻子籽", "edible": "", "water": "",
    "energyKCal": "", "protein": "", "fat": "", "CHO": "", "dietaryFiber": "", "remark": "", ... }
  ```

- 5 个目标营养字段(`energyKCal`/`protein`/`fat`/`CHO`/`dietaryFiber`)里的脏值:`Tr`(痕量)、`—`(破折号)、空字符串是文档已知的三种;另外发现 **18 条 `energyKCal` 带尾部星号**(如上面 `192001`/`192006`,全部集中在"植物油"类),以及 **1 条无法识别的垃圾值 `"un"`**(上面的 `052005`,海冻菜类,同一条记录里 `dietaryFiber` 还是 `—`——证明脏值判断必须按字段独立进行,不能"一条记录里出现一个脏值就整条标记")。
- `foodCode=192011`(麻子籽)是唯一一条**记录级整体缺失**的记录——不只是我们要的 `edible`+5 个营养字段,是这条记录的全部 31 个字段(连 `remark`)都是空字符串。
- `edible` 字段:1655 条是干净数值,范围 **7.0–100.0**;剩下 2 条脏值分属两条不同记录——`192011`(麻子籽,即上面的全空记录,值为 `""`)和 `044501`(薤,值为 `—`,但这条记录的 `energyKCal`/`dietaryFiber` 等字段有正常数值,不满足全空排除条件,仍会插入,只是 `edible_pct` 为 `null`)。

**这些新发现的处理方式**(已定,写代码时直接照做,不用再讨论):
- 尾部星号(`"899*"`)= 中国食物成分表的标准脚注,表示"换算/计算值"而非"缺失"——**去掉星号后按数字解析**,不当脏值处理。
- `"un"` 这种无法识别的字符串——解析失败,归为 `null`,并单独计入校验报告的 `unrecognized_values` 类别(不是 `Tr`/`—`/空字符串这三种已知类型,方便你事后决定要不要回源数据修正)。
- 全空记录(`192011`,麻子籽)——**排除,不入库**(你已确认这条决策)。判定规则:`edible_pct` 和 5 项营养字段(`kcal_100g`/`carb_100g`/`protein_100g`/`fat_100g`/`fiber_100g`)**全部**为 `None` 时判定为"记录级整体缺失",过滤掉不插入,计入校验报告但不占插入行数。**最终入库行数 = 1656(1657 条解析出的记录 − 1 条全空记录)**。

---

## 目标目录结构(新增)

```
backend/
  app/
    services/
      __init__.py
      food_base_cn_import.py    # 纯逻辑:解析单条记录/整目录、脏值处理、去重、ValidationReport——不碰任何真实文件/DB
      food_base_us_import.py    # 纯逻辑:解析下载的 Foundation/Survey JSON、跳过 null 数组项、UsValidationReport、整表覆盖写入(insert,不是 upsert)——和上面结构对称
      usda_adapter.py           # 纯逻辑:原始 USDA 食物对象 → 5 项营养 dataclass,按 id+name+unit 匹配,共享一份能量优先级,不按数组位置取值
  scripts/
    __init__.py
    import_food_base_cn.py      # CLI:唯一能打开真实 dietapp.db 的入口(针对 food_base_cn),默认不传 --apply 只 dry-run、--apply --confirm-real-db 才真写
    import_food_base_us.py      # CLI:同上,针对 food_base_us,和 import_food_base_cn.py 结构对称

（不再需要:usda_client.py / food_base_us_cache.py / record_usda_fixtures.py / config.py 加 usda_api_key —
 见上面"1.5 方案变更说明",USDA 批量下载不需要 key,也没有运行时 API 调用了)

tests/backend/
  fixtures/
    food_base_cn/                       # 2-3 个手写小 JSON,覆盖 Tr/—/空/星号/"un"/edible!=100/一对故意重复的 foodCode
    usda/                                # 从已下载的真实 Foundation/Survey 文件里截取的几条真实记录(不是"录制 API 响应"了),覆盖:正常完整记录、
                                          # 无能量数据的记录(Foundation 74% 是这种)、某营养素 amount=0 的真实记录;
                                          # 另加 2-3 条明确标注"人工构造,非真实数据"的最小 dict:同一记录 id=1008+2047
                                          # 两个 kcal 候选(测优先级)、id=1008 但 name/unit 不对(测不能误命中)、
                                          # dataType 和期望值不符(测 data_type_mismatches)
  test_demo_02_food_base_cn_import.py                # 单元:脏值解析(含星号脚注返回数字、"0"不当缺失)、去重、全空记录处理、DataAnomalyError 防护,用手写 fixture,跑在 migrated_engine 临时库
  test_demo_02_food_base_cn_import_real_snapshot.py  # 用真实本地 61 文件目录跑,断言精确插入 1656 条 + 已知脏值分布(18 星号/1 个"un");默认 skip、DIETAPP_REQUIRE_SNAPSHOTS=1 时改为 fail,不挡没有本地快照的机器
  test_demo_02_import_cli.py                          # food_base_cn 的 run_import(config) 防护措施测试:dry-run 不连库、显式传入和默认值相同的真实库路径也必须被判定为真实库(不能只看 database_url 是不是空字符串)、空 source_dir 拒绝(EmptySourceError)、重复导入拒绝、replace 中途失败整体回滚、数据异常默认拒绝(DataAnomalyError)、report_path 非空时报告落盘
  test_demo_02_usda_adapter.py                        # 用真实截取+人工构造的 fixture 断言 id+name+unit 三重匹配(id 对但 name/unit 不对不能命中)、多个 kcal id 同时出现时按优先级取值不相加、缺失给 null、真实 0 值保留为 0
  test_demo_02_food_base_us_import.py                 # 单元:跳过 null 数组项、missing_nutrient_counts 统计、dataType 一致性校验、insert_food_base_us_records 对 migrated_engine 临时库精确插入预期行数,用小 fixture
  test_demo_02_food_base_us_import_real_snapshot.py   # 对 import_food_base_us_snapshot(不是分别调两次单文件函数)跑真实下载的 Foundation+Survey 文件,断言精确 363+5432=5795 条、0 处跨数据集 fdc_id 冲突;默认 skip、DIETAPP_REQUIRE_SNAPSHOTS=1 时改为 fail
  test_demo_02_us_import_cli.py                       # food_base_us 的 run_import(config) 防护措施测试:dry-run 不连库、真实库路径判定同 cn、空文件拒绝(EmptySourceError)、已有数据且未传 --replace 拒绝(AlreadyImportedError,和 cn 对称)、replace 中途失败整体回滚、dataType 异常默认拒绝可被 --allow-anomalies 放行、跨数据集 fdc_id 冲突永远硬失败(--allow-anomalies 也救不了,因为 fdc_id 是主键)、report_path 非空时报告落盘

docs/data/food_base-import-log.md   # 已改:加了 food_base_us 的版本锁定表,划掉旧的"USDA 不适用版本锁定"说明(见上面 1.5 段落)
```

`services/` 和 `scripts/` 是两个新目录,理由:`.claude/rules/backend.md` 要求"业务规则进共享服务",而"真正写真实库"必须和 pytest 会 import 的代码物理隔离——`services/` 下的函数全部是纯逻辑或"传入 session 由调用方负责生命周期",没有任何函数会自己打开 `backend/data/dietapp.db`;只有 `scripts/` 下的两个 CLI 文件会(两个数据源现在都是本地文件导入,不再有"真实网络请求"这个额外维度需要隔离)。

> **`models/` vs `services/` 的区别**:`models/` 只回答"表里一行长什么样"——`FoodBaseCn`/`FoodBaseUs` 类是纯字段声明(名字/类型/约束),给 SQLAlchemy 用来生成 SQL 和做 ORM 映射,本身不含任何"怎么把数据放进去"的逻辑,也不会被直接调用去做什么动作。`services/` 回答"怎么把一份原始数据变成合法的一行"——比如"OCR 出来的字符串脏成什么样该处理成 null"、"USDA 返回的 JSON 该按哪个字段取值"——是有输入输出、能被单测直接调用验证的函数。简单说:`models/food_base_cn.py` 定义"表结构",`services/food_base_cn_import.py` 定义"怎么把 61 个 JSON 文件变成这张表里的合法行"。

---

## 1.4 — `food_base_cn` 导入设计

### 脏值解析函数

```python
def coerce_nutrient_value(raw: str) -> tuple[float | None, str]:
    """status 六选一:'ok' | 'footnote_calculated'(去掉尾部 * 后解析成功)
    | 'dirty_empty' | 'dirty_trace'(Tr) | 'dirty_dash'(—) | 'dirty_unrecognized'(如 'un')

    返回值语义:
    - 'ok' / 'footnote_calculated' 两种 → 返回 (解析出的数字, status)。'footnote_calculated'
      不是脏值,是"去掉星号后能拿到真实数字"的合法数据,只是在 status 里标记"这个数字来自脚注
      换算,不是原始测量值",数字本身照常参与计算、照常入库。
    - 'dirty_empty' / 'dirty_trace' / 'dirty_dash' / 'dirty_unrecognized' 四种 → 返回 (None, status)。
      只有这四种才是真正没有可用数值。
    - 输入字符串是 "0" 这种合法的零值 → status='ok',返回 (0.0, 'ok'),不当缺失处理。"""
```

`parse_record(raw: dict, *, source_commit: str, source_file: str, report: ValidationReport) -> ParsedFoodRecord`:对 `edible`/`energyKCal`/`protein`/`fat`/`CHO`/`dietaryFiber` 六个字段分别调用上面的函数,`foodCode`→`food_code`、`foodName`→`food_name` 原样搬,每个非 `ok` 状态计入 `report`。

### 去重策略

`food_base_cn` 表已有 `UniqueConstraint(food_code, source_commit)`,同一 commit 内如果 OCR 出现重复编码,直接批量插入会报 `IntegrityError`。策略:**先解析出全部记录,按 `food_code` 去重(保留排序后第一次出现的那条,后面的丢弃并计入 `report.duplicate_food_codes`),再插入**。当前快照实测 0 重复,这条路径现在触发不到,但测试用手写 fixture 故意造一对重复来验证。

```python
def dedupe_by_food_code(records: list[ParsedFoodRecord], report: ValidationReport) -> list[ParsedFoodRecord]: ...
```

### 全空记录过滤

```python
def filter_fully_null_records(records: list[ParsedFoodRecord], report: ValidationReport) -> list[ParsedFoodRecord]:
    """排除 edible_pct 和 5 项营养字段全部为 None 的记录(如 192011/麻子籽这种整条
    OCR 不出任何数值的记录)。food_code/food_name 恒有值,不参与这个判断。
    排除的记录计入 report.fully_null_records,不进入插入列表。"""
```

`parse_food_base_cn_directory` 内部管线固定为:逐文件解析 → `dedupe_by_food_code` → `filter_fully_null_records` → 返回待插入列表 + report。当前快照下这一步会精确过滤掉 1 条(`192011`),**预期最终插入行数 = 1656**。

### 校验报告

```python
@dataclass
class ValidationReport:
    files_processed: int
    records_parsed: int
    dirty_value_counts: dict[str, Counter[str]]        # 按字段→状态→次数
    duplicate_food_codes: dict[str, list[str]]          # food_code → 出现的文件列表
    fully_null_records: list[tuple[str, str]]            # (food_code, food_name)——被 filter_fully_null_records 排除、不入库的记录
    unrecognized_values: list[tuple[str, str, str, str]] # (source_file, food_code, field, raw)
    edible_out_of_range: list[tuple[str, float]]          # 不在 (0,100] 的 edible_pct
    rows_inserted: int

    def to_markdown(self) -> str: ...  # 贴进 PR 描述/commit 用
```

**重复编码和越界可食率默认拒绝写库,不是插了再说**:`dedupe_by_food_code` 只处理"往插入列表里放哪些记录"
(去重保留第一条,丢弃的计入 `report.duplicate_food_codes`),`edible_out_of_range` 只是记录、不排除对应
记录。当前快照下这两项都是空的(0 重复、0 越界),但下次重新锁定新版本快照时不一定还是空的。`run_import`
真正写库前会检查这两个字段(见下面 `DataAnomalyError`):非空且 `allow_anomalies=False`(默认)时直接拒绝
执行、不写库,不能让"某个 food_code 悄悄挑了第一条""某条可食率超了 (0,100] 范围"在没人看过的情况下就
进了真实库。

落盘位置:`backend/data/food_base/food_base_cn/json_data_vision_251206_Qwen2-5-VL-72B-Instruct/import_report.txt`(和这个目录下已有的 `MANIFEST.txt` 放一起)。这两个文件的区别:
- **`MANIFEST.txt` 是已经存在的文件**,不是本 PR 要新建的——之前锁定这批数据快照时就生成了,内容是"这批数据是从哪下的、锁定到哪个 commit、下载日期、61 个文件/1657 条记录、逐文件字节数核对 GitHub API 一致"这些**下载溯源信息**,回答"这份原始数据从哪来、可不可信"。
- **`import_report.txt` 是本 PR 新建的**,由 1.4 的导入脚本生成,内容是"解析这份原始数据时踩到多少脏值、类型分布、排除了几条、最终插进库里多少行"这些**导入过程的校验信息**,回答"这份原始数据导入数据库时发生了什么"。
两者都放在同一个目录下(`docs/data/food_base-import-log.md` 里"这个版本锁定在哪个目录"记录的那个路径,当前就是 `json_data_vision_251206_Qwen2-5-VL-72B-Instruct` 这个目录名——以后重新锁定新版本会是另一个按新 commit 命名的兄弟目录),都不进 git(`backend/data/` 整体 gitignore,理由一致:这是数据快照相关的产物,不是代码)。CLI 执行时同时把 `import_report.txt` 的摘要打印到 stdout,方便贴进 PR 描述。

### 插入与幂等

```python
def parse_food_base_cn_directory(directory: Path, *, source_commit: str) -> tuple[list[ParsedFoodRecord], ValidationReport]: ...
def insert_food_base_cn_records(session: Session, records: list[ParsedFoodRecord], *, batch_size: int = 500) -> int:
    """只负责"给它记录就插"。每条插入的 created_at 显式写入 UTC 时间
    (datetime.now(timezone.utc).isoformat(),不用本地时间),和项目"时间戳一律 UTC-0 存储"的铁律一致——
    insert_food_base_us_records 的 created_at 写法与此相同。"""
```

`insert_food_base_cn_records` 只负责"给它记录就插",不管幂等——幂等逻辑在 CLI 层:默认如果表里已有任何行,直接拒绝执行并提示"已导入过,加 `--replace` 才会先清空再插入";`--replace` 删除 `food_base_cn` 表的**全部**行(不是只删当前 `source_commit` 的行),再插入本次解析出的全部记录。即使未来 `food_base_cn` 新增第二个来源目录,也是把所有当前锁定的来源一起重新解析清洗后整表覆盖写入,不是"新来源追加、旧来源不动"(维护模型见 ADR 0005)。`(food_code, source_commit)` 的唯一约束只防同一次导入内部的重复编码,不代表设计上要长期保留多个 `source_commit` 的行共存。

**`--replace` 的原子性**:删旧数据 + 插新数据必须包在**同一个显式事务**里(`session.begin()` ... 任何一步抛异常整体 `rollback()`,全部成功才 `commit()`),不能是"先 commit 删除、再单独 commit 插入"这种两段式——否则插入过程中途失败(比如某条记录违反约束)会留下"旧数据已经没了、新数据只插了一半"的中间态,这条不能出现。

### CLI(`backend/scripts/import_food_base_cn.py`)——拆成可单测的纯函数 + 一层瘦壳

为了让"dry-run 不连真实库""没有确认参数就拒绝""重复导入被拒绝""replace 失败会回滚"这些**防护措施本身**都能被单测覆盖(不是只测"营养值解析对不对"),CLI 内部逻辑拆成两层:

```python
@dataclass
class ImportConfig:
    source_dir: Path
    source_commit: str = "095034a96376d893582b412900fa8fdf792b4194"
    database_url: str = ""            # 空字符串代表用 settings.database_url(即真实文件)
    dry_run: bool = True
    confirm_real_db: bool = False
    replace: bool = False
    allow_anomalies: bool = False     # 见下面 DataAnomalyError
    report_path: Path | None = None   # None = 不落盘;main() 默认写到 source_dir/import_report.txt

class AlreadyImportedError(Exception): ...          # 表里已有任何行(不论来自哪个 source_commit)且未传 --replace
class ConfirmationRequiredError(Exception): ...       # 非 dry-run 且指向真实库但未传 --confirm-real-db
class DataAnomalyError(Exception): ...                # report.duplicate_food_codes 或 report.edible_out_of_range
                                                        # 非空且未传 --allow-anomalies
class EmptySourceError(Exception): ...                # 没有解析出任何可插入记录,永远硬失败(不受
                                                        # --allow-anomalies 影响),防止配合 --replace
                                                        # 清空整表后只插入 0 行

def run_import(config: ImportConfig) -> ValidationReport:
    """CLI 的全部业务逻辑在这里,不摸 argparse/sys.argv,单测直接构造不同的 ImportConfig 组合调用:
    - dry_run=True(默认): 只跑 parse_food_base_cn_directory,函数内部这条分支完全不 import/调用
      任何 db.py/create_engine/Session 相关代码——不是"打开了连接但不写",是压根不创建连接。报告照常
      生成、如实展示重复编码/越界可食率,不因为将来可能被拒绝就不统计;report_path 非空时把报告落盘。
    - dry_run=False 且没有解析出任何可插入记录:抛 EmptySourceError,不写库——这条检查在
      confirm_real_db 检查之前,和真实库判定无关,纯粹是"source_dir 配错了"的兜底。
    - dry_run=False 且**按实际 sqlite 文件路径解析比较**(不是只看 `database_url` 是不是空字符串——
      显式传入一个和默认值解析结果相同的真实路径也必须算"指向真实库",否则这道确认形同虚设)确认目标
      就是真实 dietapp.db,且 confirm_real_db=False:直接抛 ConfirmationRequiredError,同样不打开连接。
    - dry_run=False 且(report.duplicate_food_codes 或 report.edible_out_of_range 非空)且
      allow_anomalies=False:抛 DataAnomalyError,不写库。当前快照下这两项都是空的、不会触发,但下次
      重新锁定新版本快照如果出现重复编码/可食率越界,不能在没人看过报告的情况下悄悄写库——必须显式加
      `--allow-anomalies` 才会按"去重保留第一条、越界值原样插入"的既有规则继续执行。
    - dry_run=False 且表里已有任何行(不论是不是同一个 source_commit)且 replace=False:抛 AlreadyImportedError,
      避免"新旧不同版本的行同时留在表里"这种中间态被默认放行。
    - dry_run=False 且 replace=True:按上面"原子性"的要求,删+插在一个事务里,成功后 report_path 非空则落盘。
    """

def main(argv: list[str] | None = None) -> int:
    """argparse 把命令行参数解析成 ImportConfig,调用 run_import(),打印报告/异常信息。
    这一层只做参数解析和输出格式化,不含业务判断,单测不需要碰它,直接测 run_import。

    用 `--apply`(store_true,默认不传即 `False`)而不是 `--dry-run` 做开关:`ImportConfig.dry_run`
    默认已经是 `True`,`store_true` 只能把默认值掰成 `True`,没法用同名的 `--dry-run` 掰回 `False`,
    所以需要一个语义相反的标志:`args.dry_run = not args.apply`。`--confirm-real-db` 是独立的第二道
    确认,只在目标解析后就是真实 `dietapp.db` 时才需要;写真实库必须 `--apply --confirm-real-db`
    两个都传,`--apply` 指向非真实库路径(比如临时测试文件)时不需要 `--confirm-real-db`。"""
```

CLI 参数:`--source-dir`(默认取 `docs/data/food_base-import-log.md` 记录的本地路径)、`--source-commit`(默认见上面 `ImportConfig`)、`--database-url`(默认空,即真实文件)、`--apply`(`store_true`,默认不传;传了才把 `ImportConfig.dry_run` 置为 `False`,即"真的执行")、`--confirm-real-db`(目标是真实 `dietapp.db` 时,必须和 `--apply` 一起传)、`--replace`、`--allow-anomalies`(默认不传;报告里有重复编码或越界可食率时,不传就直接拒绝执行)、`--report-path`(默认不传;`main()` 里会补一个默认值 `source-dir/import_report.txt`,和这个目录下已有的 `MANIFEST.txt` 放一起,`run_import()` 本身不替它猜默认路径,只在 `report_path` 非 `None` 时落盘,避免单测跑 `run_import()` 时污染 fixture 目录)——除 `--apply` 需要取反映射、`--report-path` 需要 `main()` 补默认值,其余直接映射进 `ImportConfig` 的对应字段。`main()` 这层至少要有一个最小烟雾测试断言"不传 `--apply` 时 `ImportConfig.dry_run is True`、传了 `--apply` 时是 `False`",防止这类参数映射错误只能靠人工跑一遍才发现。

---

## 1.5 — `food_base_us` 快照导入设计

和 1.4 完全对称的锁定版本快照导入,不是实时 API 查询+缓存(选型依据见 ADR 0005)。已经**实际下载并用
脚本核实过真实文件**(不是照搬文档假设),两个数据集都已经在:

```
backend/data/food_base/food_base_us/
  foundation_food_json_2026-04-30/
    FoodData_Central_foundation_food_json_2026-04-30.json   # 已下载解压,6721650 字节
    MANIFEST.txt                                            # 已生成,记录来源+结构核实结果
  survey_food_json_2024-10-31/
    FoodData_Central_survey_food_json_2024-10-31.json       # 已下载解压,66294426 字节
    MANIFEST.txt
```

`docs/data/food_base-import-log.md` 已同步更新(加了 `food_base_us` 的版本锁定表,划掉了旧的"USDA 不适用
版本锁定"那句话)。**因为已经是真实数据,不再是待验证的假设**,下面这些是用脚本实际跑出来的结果(不是转述
USDA 文档):

- Foundation Foods:JSON 数组长度 395,其中 **32 项是字面 JSON `null`**(USDA 官方导出文件自己的数据质量
  问题,不是我们的 bug),真实食物记录 **363** 条,`fdcId` 互不重复。
- Survey (FNDDS):JSON 数组长度 5432,**没有 null 占位项**,`fdcId` 互不重复。
- 两个数据集的 `fdcId` **互不重叠**(已实测确认,0 交集)——两个文件的记录一起整表插入时不用担心撞键。
- **能量字段的关键发现,推翻了原计划的假设,也纠正了本文档更早一版的误判**:原计划认为"Foundation
  Foods 新口径优先用 2047/2048,1008 只是兼容兜底,要按 dataType 分别定优先级"——实测证明确实不需要按
  dataType 分流,但理由和本文档曾经写的不一样:**`id=2047`(Energy, Atwater General Factors)在
  Foundation 里出现 226 次、`id=2048`(Atwater Specific Factors)出现 199 次,不是"一次都没出现过"**
  (之前那句话是只检查了 `id=1008` 得出的错误结论,已用脚本重新遍历全部 `foodNutrients` 数组订正)。
  真实分布:95 条记录靠 `id=1008` 取到能量值,226 条记录**压根没有 `id=1008`、只能靠 `id=2047`**
  取值(`id=2048` 总是和 `id=2047` 同记录同时出现,按"1008→2047→2048 命中即停"的优先级永远轮不到它被
  选中,在当前数据下确实是纯防御性兜底,但 `2047` 不是),剩下 42 条三个 id 都没有、真正没有能量数据。
  Survey 5432 条里能量条目**只出现过 `id=1008`**,`2047`/`2048` 一次都没出现——"两个数据集共用一份
  优先级列表、不按 dataType 分流"这个设计结论不变,只是"2047/2048 全局都用不到"这个描述是错的:应该是
  "`2047` 在 Foundation 里高频被选中、在 Survey 里从不被选中;`2048` 目前两个数据集里都测不到会被
  选中的真实场景"。且已确认真实数据里 `id=1008` 与 `id=2047`/`2048` **从不在同一条记录里同时出现**
  (`has_1008_and_also_2047_or_2048 = 0`),所以"多个能量候选同时出现,按优先级只取一个不相加"这条
  行为本身在真实数据里永远测不到,下面测试计划里的人工构造 fixture 仍然是唯一能验证它的手段。
- Foundation 数据本身**相当稀疏**:363 条里按"1008→2047→2048 优先级取值后仍然没有任何能量值"的口径,
  **42 条**(约 12%)真正没有能量数据(不是之前误写的 268 条——268 是只统计 `id=1008` 缺失、没算上
  `2047` 兜底命中的错误数字);Protein/Fat/Carb/Fiber 四项覆盖率分别是 352/340/321/185(fiber 最低,
  约 51%,这四项统计没有受本次纠错影响,和之前一致)。Survey 数据几乎完整:5431/5432 条同时具备全部
  5 项。
- Protein(1003)/Total lipid (fat)(1004)/Carbohydrate, by difference(1005)/Fiber, total dietary
  (1079)四项 `unitName` 全部实测为 `"g"`,和原计划假设一致,不用改。
- **合法 `amount=0` 的真实记录很充足**(Foundation 40 处、Survey 1899 处)——这条不用像原计划那样担心
  "3 条真实 fixture 里凑巧没有天然 0 值,需要合成数据",直接从真实文件里挑一条现成的就行。
- 没有发现"营养条目存在但 `amount` 键本身缺失"的情况——这份数据里"缺失"的表现形式是"这个
  `(id,name,unit)` 组合压根不在 `foodNutrients` 数组里",不是"条目在但 amount 是 null"。匹配逻辑仍然要
  用 `amount is not None`(而不是真值判断)来防未来数据里出现这种情况,但当前这批真实数据没有这个坑。
- 两个批量下载 **都不需要 API key**(公开静态文件,`curl` 直接下载成功),不需要限流处理、认证异常分类、
  key 脱敏这类 HTTP client 才需要的复杂度,也不需要 `config.py` 加任何 USDA 相关配置项。

### 目录结构

```
backend/app/services/
  food_base_us_import.py   # 纯逻辑:解析下载的 Foundation/Survey JSON、跳过 null 数组项、调用 usda_adapter
                            # 做营养提取、ValidationReport、整表覆盖写入(insert)——和 food_base_cn_import.py 结构对称
  usda_adapter.py           # 纯提取逻辑(按 id+name+unit 匹配),直接吃下载文件里的食物对象,只有一种响应形状
backend/scripts/
  import_food_base_us.py    # CLI,和 import_food_base_cn.py 结构对称(ImportConfig/run_import/main)
```

单测的 fixture 直接从已下载的真实 Foundation/Survey 文件里截取几条记录即可,不需要额外的"录制 API 响应"步骤。

### 适配器(`services/usda_adapter.py`)

```python
# 能量 id 优先级用一份共享列表,不按 dataType 分流:已用真实下载的 363(Foundation)+5432(Survey)条
# 记录验证。Survey 里能量条目只出现 id=1008+unit=kcal;Foundation 里 226 条记录没有 id=1008、
# 靠 id=2047 取到能量值(不是防御性兜底,是这些记录唯一的能量来源),id=2048 目前两个数据集
# 都测不到会被选中的真实场景,是唯一真正的纯防御性兜底(见上文"已用真实本地数据独立核实的事实")。
ENERGY_KCAL_IDS = (1008, 2047, 2048)  # 依次尝试,命中第一个就停,绝不把多个能量候选相加
PROTEIN_ID, FAT_ID, CARB_ID, FIBER_ID = 1003, 1004, 1005, 1079  # 已用真实数据核实 unitName 均为 "g"

def normalize_usda_nutrition(raw_food: dict) -> NormalizedUsdaNutrition:
    """raw_food 是下载文件里数组的一个元素(已经过滤掉 null),形状固定是
    { fdcId, description, dataType, foodNutrients: [{nutrient: {id, name, unitName}, amount}, ...], ... }。
    按 ENERGY_KCAL_IDS/PROTEIN_ID/FAT_ID/CARB_ID/FIBER_ID 逐项用 id+name+unit 三重匹配提取。
    **匹配到的 amount 字段必须用 `is not None` 判断存在性,不能用真值判断(`if amount:` 会把合法的
    0 值误判成缺失)。**没匹配上(这个 (id,name,unit) 组合压根不在数组里)→ None,不猜测、不用近似
    字段顶替。"""

@dataclass(frozen=True)
class NormalizedUsdaNutrition:
    kcal_100g: float | None
    carb_100g: float | None
    protein_100g: float | None
    fat_100g: float | None
    fiber_100g: float | None
```

### 导入(`services/food_base_us_import.py`)

```python
@dataclass
class ParsedUsFoodRecord:
    fdc_id: int
    data_type: str
    description: str
    kcal_100g: float | None
    carb_100g: float | None
    protein_100g: float | None
    fat_100g: float | None
    fiber_100g: float | None

@dataclass
class UsValidationReport:
    files_processed: int
    array_entries_total: int              # 两个文件数组长度之和(含 null 占位项)
    null_array_entries_skipped: int       # Foundation 实测 32,Survey 实测 0
    records_parsed: int                   # 实测 363+5432=5795
    missing_nutrient_counts: dict[str, int]   # 每项目标营养素"这条食物压根没有这个条目"的记录数
    data_type_mismatches: list[int]         # dataType 字段和期望值不符的 fdc_id;预期空列表
    cross_dataset_fdc_id_collisions: list[int]  # 两个文件之间重复出现的 fdc_id;预期空列表
    rows_inserted: int

    def to_markdown(self) -> str: ...

def parse_us_food_base_file(path: Path, *, expected_data_type: str) -> tuple[list[ParsedUsFoodRecord], UsValidationReport]:
    """读取**一个**下载文件,跳过数组里的字面 JSON null,对每条真实食物对象调用
    usda_adapter.normalize_usda_nutrition 提取 5 项营养;同时校验每条记录的 dataType 字段是否等于
    expected_data_type,不等的 fdc_id 计入 report.data_type_mismatches(不因此丢弃这条记录,是否要
    因此拒绝整批导入由调用方决定)。这里返回的 report.cross_dataset_fdc_id_collisions 恒为空列表——
    单文件函数看不到另一个文件的 fdc_id,真正的跨数据集冲突检测在下面 import_food_base_us_snapshot 里做,
    不能只靠这个函数自己算,也不能假装它能算。files_processed 在这里恒为 1。"""

def import_food_base_us_snapshot(foundation_path: Path, survey_path: Path) -> tuple[list[ParsedUsFoodRecord], UsValidationReport]:
    """Foundation + Survey 两个文件的协调入口——CLI 只应该调用这一个函数,不要自己分别调两次
    parse_us_food_base_file 再手动拼报告:
    1. 分别对两个文件调用 parse_us_food_base_file(*, expected_data_type=对应真实 dataType 字面量)。
    2. 合并两份 report 成一份:files_processed=2,array_entries_total/null_array_entries_skipped/
       records_parsed 相加,missing_nutrient_counts 按字段相加,data_type_mismatches 拼接。
    3. 用两个文件解析出的 fdc_id 集合求交集,写入合并后 report 的 cross_dataset_fdc_id_collisions
      (已实测两个真实文件是 0 交集,这里是防御性检测,不代表预期会触发)。
    4. 返回拼接后的全部记录列表 + 合并后的 report,这一步不碰数据库。"""

def insert_food_base_us_records(session: Session, records: list[ParsedUsFoodRecord], *, batch_size: int = 500) -> int:
    """只负责"给它记录就插",和 insert_food_base_cn_records 同样的分工:不管幂等,不判断表里
    是否已有数据——这些判断在 CLI 层的 run_import 里做(拒绝重复导入 / --replace 整表清空重插,
    和 food_base_cn 完全对称)。每条插入的 created_at 显式写入 UTC 时间
    (datetime.now(timezone.utc).isoformat(),不用本地时区,和项目"时间戳一律 UTC-0 存储"的铁律一致,
    和 insert_food_base_cn_records 的 created_at 写法相同)。不用 fdc_id 做 get-or-create:表内容是
    当前锁定版本的整体重建结果,不是可以按主键增量合并的缓存(维护模型见 ADR 0005)。"""
```

### CLI(`backend/scripts/import_food_base_us.py`)——和 `import_food_base_cn.py` 对称

```python
class AlreadyImportedError(Exception): ...          # 表里已有行且未传 --replace(和 cn 对称)
class ConfirmationRequiredError(Exception): ...       # 非 dry-run 且指向真实库但未传 --confirm-real-db
class DataAnomalyError(Exception): ...                # report.data_type_mismatches 非空且未传
                                                        # --allow-anomalies;或 report.cross_dataset_fdc_id_collisions
                                                        # 非空(这一条永远硬失败,--allow-anomalies 救不了——
                                                        # fdc_id 是主键,插入两条同 fdc_id 记录必然真实撞唯一
                                                        # 约束,"放行"没有意义,只会把干净的 ValueError 级错误
                                                        # 换成更难看的 IntegrityError,必须先回去核对源文件)
class EmptySourceError(Exception): ...                # 两个文件没有解析出任何可插入记录,永远硬失败,
                                                        # 防止配合 --replace 清空整表后只插入 0 行

@dataclass
class UsImportConfig:
    foundation_json_path: Path   # 默认指向上面下载好的 Foundation 文件路径
    survey_json_path: Path       # 默认指向上面下载好的 Survey 文件路径
    database_url: str = ""       # 空字符串代表用 settings.database_url(即真实文件)
    dry_run: bool = True
    confirm_real_db: bool = False
    replace: bool = False        # False(默认):表里已有任何行就拒绝执行,抛 AlreadyImportedError,
                                  # 提示加 --replace;True:先 DELETE FROM food_base_us 全表,
                                  # 再插入本次解析出的全部记录,删+插在同一事务里(原子性要求和
                                  # food_base_cn 的 --replace 一样,任何一步异常整体 rollback)
    allow_anomalies: bool = False  # 见上面 DataAnomalyError
    report_path: Path | None = None  # None = 不落盘;main() 默认写到 food_base_us/import_report.txt

def run_import(config: UsImportConfig) -> UsValidationReport:
    """和 food_base_cn 的 run_import 同样的防护措施,现在两者语义完全对称。内部调用的是
    import_food_base_us_snapshot(两个文件的协调入口),不是直接调 parse_us_food_base_file:
    - dry_run=True(默认):只跑 import_food_base_us_snapshot,完全不建数据库连接。报告照常生成,
      report_path 非空时落盘。
    - dry_run=False 且没有解析出任何可插入记录:抛 EmptySourceError,不写库。
    - dry_run=False 且**按实际 sqlite 文件路径解析比较**(不是只看 database_url 是不是空字符串)
      确认目标就是真实库,且 confirm_real_db=False:抛 ConfirmationRequiredError。
    - dry_run=False 且 report.cross_dataset_fdc_id_collisions 非空:永远抛 DataAnomalyError,不受
      allow_anomalies 影响——见上面 DataAnomalyError 的说明。
    - dry_run=False 且 report.data_type_mismatches 非空且 allow_anomalies=False:抛 DataAnomalyError,
      不写库。当前两个真实文件下这两项都是空的,不会触发,但下次重新锁定新版本时如果出现 dataType
      不一致,不能在没人看过报告的情况下悄悄写库。
    - dry_run=False 且表里已有任何行且 replace=False:抛 AlreadyImportedError。
    - dry_run=False 且 replace=True:整表 DELETE + 全部记录 INSERT 包在同一显式事务里,
      任何一条记录插入失败整体 rollback,不会留下"旧数据已删、新数据只插了一半"的中间态。
      成功后 report_path 非空则落盘。"""

def main(argv: list[str] | None = None) -> int: ...
    # CLI 用 --apply(store_true,默认不传)映射到 UsImportConfig.dry_run = not args.apply,
    # 和 import_food_base_cn.py 同一套映射逻辑,理由见那边 main() 的说明。
```

CLI 参数:`--foundation-json`/`--survey-json`(默认见上面路径)、`--database-url`(默认空即真实文件)、
`--apply`(`store_true`,默认不传;传了才把 `UsImportConfig.dry_run` 置为 `False`,和
`import_food_base_cn.py` 同一套映射逻辑)、`--confirm-real-db`
(目标是真实 `dietapp.db` 时必须和 `--apply` 一起传)、`--replace`、`--allow-anomalies`(默认不传;
报告里有 dataType 不一致时,不传就直接拒绝执行——跨数据集 fdc_id 冲突这条永远硬失败,这个参数救不了)、
`--report-path`(默认不传;`main()` 补默认值 `food_base_us/import_report.txt`,和 cn 那边同一套"落盘
默认值只在 main() 里算、run_import() 本身只在 report_path 非 None 时落盘"的设计)。

> **为什么要用代码做 id+name+unit 匹配,而不是让 LLM 直接读 USDA 原始 JSON 取值**(这条结论不受本次
> 方案变更影响,依然成立):准确说法不是"LLM 碰真实数据不可信"(它读到的确实是真数据,不是编的),而是
> **这一步本身是纯粹的确定性字段提取任务,不需要语义判断,交给代码能做到 100% 稳定且零成本**:
> 1. `foodNutrients` 数组里混有占位行(ADR 0002 实测发现的真实案例:`id=2045 name="Proximates"`,没有
>    `amount` 字段),紧挨着真实的 `id=1008 name="Energy"`——这种"看起来像但其实不是"的条目,代码按固定
>    规则(id+name+unit 三者都对上才算数)能保证每次都精确避开,LLM 去读同一份 JSON 未必每次都能稳定
>    避开(不是说谎,是这类相似条目本身容易读串)。
> 2. 缺失值的处理方式不一样:代码要么精确匹配上、要么返回 `None`,没有中间态;LLM 被问"这个食物的能量
>    是多少",遇到该字段确实缺失时,存在"倾向给出一个看起来合理的答案而非直说没有"的已知行为模式——这正
>    是项目里反复强调"缺失用 null、不要猜一个像话的数"这条铁律要防的风险,只是这次防的对象从 OCR 脏值
>    换成了 USDA 数组里的占位行。
> 3. 数组按 key 取值代码瞬间完成零成本,绕一圈 LLM 调用做同一件事要多付延迟和 token 成本,而这本来就是
>    个已解决问题。
>
> 换句话说:这不是"营养数据"这个类别的专属规则,而是和四级链里去重、单位换算、可食率这些确定性步骤
> 同一个道理——**纯粹的确定性提取交给代码,LLM 只留给真正需要语义判断的步骤**(比如从候选列表里判断
> 哪一条对应用户说的"宫保鸡丁")。`usda_adapter.py` 的 `normalize_usda_nutrition` 做的就是这个确定性
> 提取;LLM 在四级查询链里的角色始终是"从一批已经算好的候选里挑哪个匹配用户说的食物",不碰候选本身的
> 数值怎么算出来。
>
> **`food_base_us` 是"导入"不是"缓存"**:和 `food_base_cn` 完全一样,是一次性导入的本地快照,不是
> 运行时按需缓存的结果。1.7 的四级查询链②③两级都是纯本地 SQLite 查询,没有任何一级需要在用户记饭菜的
> 当下打真实网络请求,符合 SPEC §7.6"外部源会失败/限流需要降级"这条本身就该尽量少依赖的原则。以后要
> 更新数据,做法和 `food_base_cn` 一样:重新下载新版本、建新的兄弟目录、重新导入。

---

## 测试计划

| 文件 | 覆盖点 |
|---|---|
| `test_demo_02_food_base_cn_import.py` | `coerce_nutrient_value` 各状态(含星号脚注返回真实数字、`un`/`Tr`/`—`/空 返回 `None`、字符串 `"0"` 返回 `0.0` 不当缺失)、`parse_record` 脏值不转 0、`dedupe_by_food_code`(手写 fixture 里故意放一对重复 foodCode)、`filter_fully_null_records` 排除全空记录且计入报告、`insert_food_base_cn_records` 对 `migrated_engine` 临时库、重复插入同 `source_commit` 触发 `IntegrityError` |
| `test_demo_02_food_base_cn_import_real_snapshot.py` | 对真实本地 61 文件目录跑 `parse_food_base_cn_directory` + 插入 `migrated_engine` 临时库,断言解析出 1657 条、过滤 1 条全空记录、**精确插入 1656 条**;另外断言已知的脏值分布本身,不只断行数——`report.dirty_value_counts["energyKCal"]["footnote_calculated"] == 18`(星号脚注)、`len(report.unrecognized_values) == 1`(唯一一条 `"un"`)。目录不存在时默认 `pytest.mark.skipif`,不挡没有本地快照的机器;但设了 `DIETAPP_REQUIRE_SNAPSHOTS=1` 环境变量时改成 `pytest.fail`,不允许跳过——1.4 的验收标准本身就是这份真实数据的精确记录数,不能出现"测试全绿但这条核心验收从没真正跑过"。本 PR 最终验收(向你汇报 done 之前)必须在设了这个环境变量的前提下跑一遍,贴命令+输出 |
| `test_demo_02_import_cli.py` | 针对 `food_base_cn` 的 `run_import(config)` 这层纯函数,不碰 argparse:①`dry_run=True` 时 monkeypatch 掉 `create_engine`(断它没被调用过)来证明真的没开数据库连接;②`dry_run=False` + 指向"真实库"路径 + `confirm_real_db=False` → 断言抛 `ConfirmationRequiredError` 且没有任何行被写入;②b **显式传入 `settings.database_url` 本身**(不是留空)+ `confirm_real_db=False` → 同样断言抛 `ConfirmationRequiredError` 且 `create_engine` 未被调用——防止"只判断 `database_url` 是不是空字符串"这种实现被显式传入的真实路径绕过;③表里已存在任意数据(不论是不是同一个 `source_commit`)+ `replace=False` → 断言抛 `AlreadyImportedError`;④`replace=True` 且插入过程中人为让某条记录触发异常(比如注入一条违反约束的记录) → 断言整个事务回滚,库里的**总行数**和执行前完全一致(不多不少,不是"旧的没了新的也没插完"的中间态);⑤用手写 fixture 故意造出重复 `food_code` 或越界 `edible_pct`,`allow_anomalies=False`(默认)→ 断言抛 `DataAnomalyError` 且没有任何行被写入;`allow_anomalies=True` → 断言按既有规则(去重保留第一条/越界值原样插入)正常写入;⑥`source_dir` 指向一个没有任何 `merged_*.json` 文件的空目录 + `replace=True` → 断言抛 `EmptySourceError`,且不影响已有数据(不会出现"清空整表后只插入 0 行") |
| `test_demo_02_usda_adapter.py` | 从已下载的真实 Foundation/Survey 文件里**截取几条真实记录**存成 `tests/backend/fixtures/usda/` 下的小 fixture(不再是"录制 API 响应",直接从真实下载文件里挑),覆盖:①正常完整记录(id+name+unit 匹配对);②Foundation 里常见的"没有任何 Energy 条目"的记录(断言 `kcal_100g=None`,不是报错也不是当 0);③某营养素 `amount` 真实等于 0 的记录(Foundation/Survey 都有现成的,直接挑一条,不用合成)——断言保留为 `0.0` 而不是被判成缺失;④单位过滤:1008(kcal)+1062(kJ)同时出现,只取 kcal 那个,不折算 kJ→kcal;⑤**必须**用一条明确标注"人工构造,非真实数据"的最小 dict,同一条记录里同时放 id=1008 和 id=2047 两个 kcal 候选(数值不同)——断言取 1008 的值、不取 2047、不相加。真实数据里两个 kcal id 从未同时出现,这条测不到真实数据不代表可以跳过,SPEC §4.4.2 明确要求"同一记录出现多个能量值时按单一优先级选择",这正是唯一能证明优先级本身生效(而不只是证明单位过滤生效)的用例;⑥再用一条人工构造 fixture 验证"id 对但 name 或 unit 不对不能命中"——例如 id=1008 但 `unitName` 是 `"kJ"`,或 id=1008 但 `name` 不是 `"Energy"`,断言这种条目不被当作匹配(找不到候选时最终 `kcal_100g=None`,不会因为 id 对了就直接采信) |
| `test_demo_02_food_base_us_import.py`(新增) | `parse_us_food_base_file` 跳过数组里的 `null` 占位项并计入 `null_array_entries_skipped`(用一个手写小 fixture,数组里故意放 1 个 `null` + 2-3 条真实记录);`missing_nutrient_counts` 统计正确;`insert_food_base_us_records` 对 `migrated_engine` 临时库精确插入预期行数,`created_at` 是合法 UTC 时间字符串 |
| `test_demo_02_food_base_us_import_real_snapshot.py`(新增) | 对真实下载的 Foundation(363 条)+ Survey(5432 条)文件跑 `import_food_base_us_snapshot`(不是分别调两次 `parse_us_food_base_file` 再自己拼)+ 插入 `migrated_engine` 临时库,断言:总解析记录数精确等于 **5795**、`null_array_entries_skipped` 精确等于 **32**(全部来自 Foundation)、`data_type_mismatches` 和 `cross_dataset_fdc_id_collisions` 都是空列表。文件不存在时默认 `pytest.mark.skipif`,设了 `DIETAPP_REQUIRE_SNAPSHOTS=1` 时改成 `pytest.fail`(和 cn 那条同样的策略,理由一致),本 PR 最终验收时必须这样跑一遍 |
| `test_demo_02_us_import_cli.py`(新增) | 针对 `food_base_us` 的 `run_import(config)`,和 cn 对称:①`dry_run=True` 时不建数据库连接;②`dry_run=False` + 真实库路径 + 未传 `confirm_real_db` → `ConfirmationRequiredError`;②b 显式传入 `settings.database_url` 本身同样不能绕过(和 cn 对称);③表里已存在任意数据 + `replace=False` → `AlreadyImportedError`;④`replace=True` 且插入过程中人为触发异常 → 断言整个事务回滚,表内行数和执行前一致;⑤用手写 fixture 故意造出 dataType 不一致(比如 Foundation 文件里塞一条 `dataType` 写成别的值的记录),`allow_anomalies=False`(默认)→ 断言抛 `DataAnomalyError` 且没有任何行被写入;`allow_anomalies=True` → 断言正常写入;⑥用另一对手写 fixture 故意造出跨数据集重复 `fdc_id` → 即使传了 `allow_anomalies=True` 也断言仍然抛 `DataAnomalyError`(fdc_id 是主键,这条异常永远不可放行);⑦两个下载文件都解析出 0 条记录 + `replace=True` → 断言抛 `EmptySourceError`,不影响已有数据 |

不新增 mock 依赖(不装 `respx`/`vcrpy`)——`httpx` 已是既有依赖,`httpx.MockTransport` 够用,符合"不为还没用到的需求提前抽象"。USDA 这边现在也用不上 `httpx.MockTransport` 了,直接读真实/截取的 JSON 文件即可,不需要 mock 网络请求。

---

## 执行顺序

1. `git checkout -b feature_demo_02_food_base`(从最新 main)。✅ 已完成。
2. 写 `tasks/current.md`(本计划内容,替换掉旧的 1.1-1.3 记录)。✅ 已完成。
3. 同步 `tasks/STATUS.md` 1.4 行的验收数字:"1657 条" → "解析 1657 条,排除 1 条`192011`麻子籽全字段缺失记录,插入 1656 条"(保留 1657 这个原始快照记录数,不能只把 1657 直接改成 1656,否则丢失可追溯性)。✅ 已完成。
4. 下载 USDA Foundation Foods + Survey(FNDDS)批量 JSON,放进 `backend/data/food_base/food_base_us/`,生成 `MANIFEST.txt`。✅ 已完成。
5. 更新 `docs/data/food_base-import-log.md` 加 `food_base_us` 版本锁定表。✅ 已完成。
6. 同步 `docs/product/SPEC.md` §1/§4.4.2/§7.9/§12.1/§12.2 + `docs/decisions/0002-composed-dish-fallback.md`。✅ 已完成。
7. 同步 `tasks/STATUS.md` 1.5 行的措辞和验收标准。✅ 已完成。
8. `FoodBaseUs.cached_at` 改名 `created_at`(对齐 `food_base_cn`,维护模型见 ADR 0005)。✅ 已完成:`backend/app/models/food_base_us.py` 和首条迁移 `50b75ce1aba2_create_demo_tables.py` 都已改成 `created_at`。**真实本地 `dietapp.db` 是改之前生成的,物理上还是旧的 `cached_at` 列**——这个不一致留到第 17 步现场处理(需要重建整个数据库文件,不是只删一张表,原因见第 17 步),不在这一步执行。
9. 写 `services/food_base_cn_import.py` + 手写 fixture + `test_demo_02_food_base_cn_import.py`,跑绿。
10. 写 `test_demo_02_food_base_cn_import_real_snapshot.py`,对真实 61 文件目录跑,确认解析 1657 条、过滤 1 条、精确插入 1656 条。
11. 写 `services/usda_adapter.py`(共享能量优先级)+ `services/food_base_us_import.py`(`insert_food_base_us_records`,不是 upsert)+ `test_demo_02_usda_adapter.py` + `test_demo_02_food_base_us_import.py`,用从真实下载文件截取的小 fixture,跑绿。
12. 写 `test_demo_02_food_base_us_import_real_snapshot.py`,对真实下载的 Foundation+Survey 文件跑,确认解析 5795 条(363+5432)、跳过 32 条 null 占位、0 处跨数据集 fdc_id 冲突。
13. 写 `scripts/import_food_base_cn.py`(`ImportConfig`/`run_import`/`main`,含 `--apply`/`--confirm-real-db`/`--allow-anomalies` 的 argparse 映射)+ `test_demo_02_import_cli.py`,覆盖 dry-run 不连库、未确认拒绝、表内已有数据拒绝(不论是不是同一 `source_commit`)、replace 失败整表回滚、数据异常默认拒绝(`DataAnomalyError`)这几条防护措施,再加一条 `main()` 参数映射的最小烟雾测试;先不加 `--apply` 跑一遍(默认 dry-run)把校验报告贴给你看,跑绿。**这一步第一次创建 `backend/scripts/`,必须同时把 `pyproject.toml` 的 mypy `files` 从 `["backend/app"]` 改成 `["backend/app", "backend/scripts"]`**——CLI 是唯一能碰真实库的入口,必须纳入类型检查,不是"视需要"的可选项(`backend/app/services` 已经在 `backend/app` 目录下,mypy 按目录递归检查,不需要单独列出)。
14. 写 `scripts/import_food_base_us.py`(`UsImportConfig`/`run_import`/`main`,和 `import_food_base_cn.py` 对称,同样有 `--apply`/`--confirm-real-db`/`--allow-anomalies`)+ `test_demo_02_us_import_cli.py`,覆盖 dry-run 不连库、未确认拒绝、表内已有数据拒绝、replace 失败整表回滚、数据异常默认拒绝、`main()` 参数映射烟雾测试,先不加 `--apply` 跑一遍把校验报告贴给你看,跑绿。
15. 全量跑 `pytest`(默认不带 `DIETAPP_REQUIRE_SNAPSHOTS`)+ `ruff check backend` + `mypy`(这时 `pyproject.toml` 已经在第 13 步改过,`backend/scripts` 必须干净通过),贴命令+输出。再单独跑一次 `$env:DIETAPP_REQUIRE_SNAPSHOTS = '1'; pytest`(Windows PowerShell 语法,不是 POSIX 的 `DIETAPP_REQUIRE_SNAPSHOTS=1 pytest` 内联写法——PowerShell 不支持这种前缀式临时环境变量赋值),确认两份真实快照测试真正执行(不是被跳过)且通过,同样贴命令+输出。**在这一步之前不碰真实 `dietapp.db`**。
16. 把第 13/14 步已经生成的两份 dry-run 校验报告(`food_base_cn` 的 `import_report.txt` + `food_base_us` 的等价报告)重新审查一遍,确认脏值/null 占位/去重/缺失营养素统计都符合预期,duplicate_food_codes/edible_out_of_range/data_type_mismatches/cross_dataset_fdc_id_collisions 都是空。
17. **停下来问你**:上面全量测试(含 `DIETAPP_REQUIRE_SNAPSHOTS=1`)和两份 dry-run 报告都确认没问题后,分两步执行真实写入(你已确认"这条分支里做,到点了再问我一次",这条约定同样适用于本次的字段改名和 `food_base_us` 真实导入)——
    ①**真实 `dietapp.db` 需要整个文件重建,不是只删 `food_base_us` 这一张表**:这个文件的 `alembic_version` 表已经记录当前版本是 `50b75ce1aba2`(等于 head),而这个版本对应的 schema 就是改名前的旧版(`food_base_us.cached_at`)。Alembic 的 `upgrade head` 只在"当前版本落后于 head"时才会执行 `upgrade()`,已经在 head 时重跑是空操作——手动 `DROP TABLE food_base_us` 之后再跑 `alembic upgrade head` 不会重新建这张表,因为 Alembic 不知道你手动动过表,它只看 `alembic_version` 那一个字段。正确做法是**备份或删除整个 `backend/data/dietapp.db` 文件**,让这个数据库从空白状态重新走一遍 `alembic upgrade head`(会把全部 5 张表按当前迁移定义重建)。**这个动作会连带清空 `meal_entry`/`daily_summary`/`chat_message` 等其它表当前的任何数据,不只是 `food_base_us`**——需要明确问清楚这一点,不能默认你只是想清掉一张空表。删除/重建前先确认这几张表目前确实没有需要保留的真实数据(按项目当前进度,1.6 及以后的写入功能都还没实现,预期为空,但需要你确认而不是我假设)。重建完用 `PRAGMA table_info(food_base_us)` 或等价方式确认列名只有 `created_at`、没有 `cached_at`,再进入下一步。
    ②确认后分别加 `--apply --confirm-real-db` 对 `food_base_cn`/`food_base_us` 执行真正导入(两个参数缺一不可:只传 `--apply` 不传 `--confirm-real-db` 会被 `ConfirmationRequiredError` 挡下)。
18. 执行后只做**只读核对**:`SELECT COUNT(*) FROM food_base_cn` = 1656,`SELECT COUNT(*) FROM food_base_us` = 5795,`PRAGMA table_info(food_base_us)` 确认列名是 `created_at` 不是 `cached_at`;把两份最终校验报告贴给你看。
19. 不自动 `git push` / 不自动开 PR——各自单独确认。

---

## 验证方式

- `conda activate vibe-coding && pytest`(根目录跑,覆盖新增的 7 个测试文件 + 已有 9 个)——**在第 17 步真实迁移/真实导入之前就要全绿**,不是导入之后才补跑。两份真实快照测试默认 skip,最终验收前必须额外用 `$env:DIETAPP_REQUIRE_SNAPSHOTS = '1'; pytest`(Windows PowerShell 写法)跑一遍并贴输出(见测试计划表),证明核心验收真的执行过、不是被跳过之后误判为通过。
- `ruff check backend && mypy`——同样在第 17 步之前跑完。
- 手动核对(第 17 步现场确认、执行后只读核对,不是默认发生的):**整个 `dietapp.db` 文件**重建后(不是只删 `food_base_us` 这一张表——原因见第 17 步的 Alembic 版本追踪说明)`PRAGMA table_info(food_base_us)` 确认列名是 `created_at`(不是旧的 `cached_at`);两次 `--apply --confirm-real-db` 真实导入执行完后,`SELECT COUNT(*) FROM food_base_cn` = 1656(1657 条 OCR 记录 − 1 条全空记录 `192011`);`SELECT COUNT(*) FROM food_base_us` = 5795(363 条 Foundation + 5432 条 Survey,已实测两者 `fdc_id` 无交集)。
- 校验报告(`import_report.txt` + stdout)贴给你看,确认脏值处理数量、星号脚注/`\"un\"` 归类、去重结果符合预期(`food_base_cn`)以及 null 占位跳过数量、缺失营养素统计(`food_base_us`)——这份审查按新顺序发生在第 16 步(真实写入之前),不是写入之后才第一次看。
