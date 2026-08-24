# flow_charts 变更记录

维护规则见 README.md 第 4 条:新增/修改/删除业务环节时在这里记一笔。格式:
`YYYY-MM-DD` + 改了什么 + 为什么(如果不是显而易见的话)。

## 2026-08-23

- 建立 flow_charts 体系:`README.md`(用途 + 维护规则)、`00_demo_overview.md`
  (Demo 1.1~1.13 业务流程总览)、`01_0608_food_query.md`(1.6~1.8 食物查询引擎,
  `[现有]`)、`01_09_write_path.md`(1.9 写入路径,`[1.9计划]`)。首批内容基于对
  `backend/app/`/`frontend/src/`/`tasks/STATUS.md`/`tasks/current.md`/
  `docs/product/SPEC.md` 的逐文件核实结果。
- 流程图配色改为按**泳道**上色(用户操作/Front end/后端HTTP入口/Backend
  Service/LLM/SQLite),不再按完成状态上色——完成状态已经用第三行的
  `[现有]`/`[计划]`/`[后续]` 文字标签表达,颜色腾出来表示"这一步落在哪一层"。
  "业务环节 → 代码"表格在"文件位置"前加"泳道"列,和流程图颜色对应
  (README.md 维护规则 8)。
- `01_09_write_path.md` 补上此前完全缺失的跨里程碑调用:`handle_new_message`
  内部实际调用的 1.8 `parse_diet_text`、1.7 `estimate_items` 现在在表格和
  流程图里都显式出现(标 `[现有]` + 所属里程碑号),不再让读者看不出这两个
  已有函数在 1.9 流程里的位置(README.md 维护规则 9)。
- `01_09_write_path.md` 流程图里 `chat_message`/`meal_entry` 圆柱形节点补上
  写入方向:`record_chat_message`/`confirm_meal_entry` 各自虚线绕回同一个
  圆柱节点,明确"读的今日已有行"和"这一步新写入的行"是同一张表,不是两份
  数据(此前只画了读,没画写,容易被误读成两份独立数据)。
- `01_09_write_path.md` 流程图里 `attribution_date`(`ATTR`)改成不再插在
  `handle_new_message → 读取今日数据` 主链路中间,而是从 `READ`/`REC`/`F`/
  `DELFUNC` 四个节点分别虚线"内部调用"指向它——此前的画法暗示归属日计算是
  `handle_new_message` 编排出的唯一一次步骤,但实际上它是被多个直接摸 SQLite
  的函数各自内部调用的共享工具函数(current.md 还写明 1.10 结转任务也要复用
  同一个函数),不是 1.9 这条链路专属的一次性步骤。
- 上一条的中间方案(虚线指回主图里的 `ATTR`)还是把一个"谁都能调"的共享工具
  硬塞进一条线性链路里,继续把它整个挪出"简化流程"主图,单独开一节"支线:
  归属日计算(共享工具)",用一张小图专门表示"`READ`/`REC`/`F`/`DELFUNC` 都会
  内部调它",主图和支线各自更干净,不用在主链路里为一个跨多处调用的工具函数
  找一个不存在的"正确位置"。
- `01_09_write_path.md` 流程图扩到和表格完全一一对应:补上此前遗漏的
  `list_today_chat_messages`(新增表格行)、`record_chat_message`、
  `handle_modify_correction`(虚线次要交互)、路由层四个 API 节点、
  `delete_todays_meal_entry` 删除支线;`今日chat_message`/`今日meal_entry`
  画成圆柱形数据节点表示"已有输入",不是这一步新产出的。`RecordTab.tsx`
  仍只保留表格行、不单独画节点(它是容器,不对应流程里的某个时间点),原因
  写在流程图正上方的说明里。
